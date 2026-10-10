# 第 9 阶段保存聊天。第 10 阶段接上分析图。第 13 阶段加上频率、额度和压缩。
# 缺密钥就关掉连接。这一版没有匿名免费试用。

# 超时和后台写库。
import asyncio
# 第一帧是文本，要自己解析。
import json
# 失败日志。
import logging
# 超时秒数。
import os

# 连接。
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# 写进上下文的消息。
from langchain_core.messages import AIMessage, HumanMessage

# 会话。
from api.db import get_or_create_session, get_session, get_session_messages, save_message
# 密钥。
from api.dependencies import resolve_ws_keys, verify_ws_identity
# 额度。聊天整段不占 llm_slot，只在用操作员密钥时扣每天次数。
from api.llm_concurrency import LLMBudgetExceeded, check_and_charge_budget
# 压缩。
from api.memory import build_context_from_session, compress_history, estimate_tokens_incremental
# 每分钟 10 条。
from api.rate_limit import check_rate_limit, client_ip
# 股票代码。
from api.validators import TICKER_RE
# 模型。
from agents.llm_factory import create_llm_pair
# 超时类型。
from agents.graph.analyst_graph import LLMTimeoutError, create_sec_qa_agent
# 清单。
from agents.model_registry import get_default_model, get_model, get_token_threshold

# 日志。
logger = logging.getLogger(__name__)
# 路由。
router = APIRouter()
# 等第一帧的时间。
WS_AUTH_TIMEOUT_SECONDS = float(os.getenv("WS_AUTH_TIMEOUT_SECONDS", "30"))
# 第一帧最大字节。
WS_AUTH_MAX_BYTES = int(os.getenv("WS_AUTH_MAX_BYTES", "16384"))
# 空闲多久关掉。
WS_IDLE_TIMEOUT_SECONDS = float(os.getenv("WS_IDLE_TIMEOUT_SECONDS", "300"))
# 一条问题最长。
MAX_QUERY_LENGTH = 4000


# 发送失败就当对方已经走了。
async def _safe_send(websocket: WebSocket, data: dict) -> bool:
    # 发送。
    try:
        # JSON。
        await websocket.send_json(data)
        # 成功。
        return True
    # 断开。
    except (WebSocketDisconnect, RuntimeError):
        # 失败。
        return False


# 聊天连接。
@router.websocket("/ws/chat/{ticker}")
async def chat(websocket: WebSocket, ticker: str):
    # 接受。
    await websocket.accept()
    # 代码不合法。
    if not TICKER_RE.match(ticker.upper()):
        # 错误。
        await websocket.send_json({"type": "error", "message": "股票代码不合法。"})
        # 关掉。
        await websocket.close()
        # 结束。
        return
    # 统一大写。
    ticker = ticker.upper()
    # 整段连接。
    try:
        # 等第一帧。
        try:
            # 文本，方便先看长度。
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_SECONDS)
        # 太慢。
        except asyncio.TimeoutError:
            # 关掉。
            await websocket.close(code=1008)
            # 结束。
            return
        # 太大。
        if len(raw_auth) > WS_AUTH_MAX_BYTES:
            # 关掉。
            await websocket.close(code=1008)
            # 结束。
            return
        # 解析。
        try:
            # JSON。
            auth_message = json.loads(raw_auth)
        # 不是 JSON。
        except (json.JSONDecodeError, ValueError):
            # 错误。
            await websocket.send_json({"type": "error", "message": "认证内容不是 JSON。"})
            # 关掉。
            await websocket.close(code=1008)
            # 结束。
            return
        # 必须是对象，并且 type 是 auth。
        if not isinstance(auth_message, dict) or auth_message.get("type") != "auth":
            # 错误。
            await websocket.send_json({"type": "error", "message": "第一条消息必须是认证。"})
            # 关掉。
            await websocket.close()
            # 结束。
            return
        # 解析密钥。
        keys = resolve_ws_keys(auth_message)
        # 核对登录。本地关闭时总是通过。
        ok, reason = verify_ws_identity(keys.user_id, auth_message)
        # 不通过。
        if not ok:
            # 错误。
            await websocket.send_json({"type": "error", "message": reason or "未登录。"})
            # 关掉。
            await websocket.close(code=1008)
            # 结束。
            return
        # 用户。匿名可以聊天，但不落库。
        user_id = keys.user_id
        # IP，用来限流。
        ip = client_ip(websocket)
        # 选模型。请求里有并且清单里存在就用它。
        requested = auth_message.get("model_id")
        # 不是合法编号。
        if not isinstance(requested, str) or get_model(requested) is None:
            # 丢掉。
            requested = None
        # 决定编号。
        model = get_model(requested or keys.model_id or "") or get_default_model()
        # 密钥。没有就拒绝，不走免费试用。
        api_key = keys.get_provider_key(model.provider)
        # 缺密钥。
        if not api_key:
            # 厂商名。
            provider = model.provider.replace("_", " ").title()
            # 错误。
            await websocket.send_json({"type": "error", "message": f"使用 {model.display_name} 需要 {provider} 密钥。请在设置里填写。"})
            # 关掉。
            await websocket.close()
            # 结束。
            return
        # 只有操作员密钥才扣每天 100 次。
        operator_paid = keys.is_operator_paid(model.provider)
        # 有用户才恢复会话。
        session_id = None
        # 历史消息。
        all_messages: list[dict] = []
        # 模型上下文。
        conversation_history: list = []
        # 登录用户。
        if user_id:
            # 指定了会话就用它，否则按股票找或新建。
            explicit = auth_message.get("session_id")
            # 指定。
            if isinstance(explicit, str) and explicit:
                # 用指定的。
                session_id = explicit
            # 没指定。
            else:
                # 查找或创建。
                session_id = await get_or_create_session(ticker, user_id, model=model.id)
            # 读会话。
            session = await get_session(session_id)
            # 必须是这只股票、这个用户。
            if session is None or session["ticker"].upper() != ticker or session.get("user_id") != user_id:
                # 错误。
                await websocket.send_json({"type": "error", "message": "会话不存在。"})
                # 关掉。
                await websocket.close()
                # 结束。
                return
            # 全部消息。
            all_messages = await get_session_messages(session_id)
            # 上下文。有摘要就用摘要加最近几条。
            conversation_history = build_context_from_session(session, all_messages)
        # 研究是否可用。
        research = "网页研究可用" if keys.tavily_api_key else "没有网页研究密钥"
        # 认证成功。
        await websocket.send_json({
            # 类型。
            "type": "auth_success",
            # 说明。
            "message": f"已连接 {ticker}，模型 {model.display_name}。{research}。",
            # 会话。匿名是 null。
            "session_id": session_id,
            # 有旧消息才恢复。
            "resumed": len(all_messages) > 0,
            # 模型。
            "model_id": model.id,
        })
        # 创建两个模型和分析器。
        try:
            # 工具模型关思考，总结模型按清单决定。
            llm, synthesizer = create_llm_pair(model.id, api_key)
            # 分析器。
            agent = create_sec_qa_agent(
                # 股票。
                ticker,
                # 工具模型。
                llm,
                # 研究密钥。
                tavily_api_key=keys.tavily_api_key,
                # 总结模型。
                synthesizer_llm=synthesizer,
                # 早报按用户隔离。
                user_id=user_id,
            )
        # 创建失败。
        except Exception:
            # 日志。
            logger.exception("agent init failed for %s", ticker)
            # 错误。
            await websocket.send_json({"type": "error", "message": "分析器没有启动。请检查密钥。"})
            # 关掉。
            await websocket.close()
            # 结束。
            return
        # 压缩阈值。
        token_threshold = get_token_threshold(model.id)
        # 累计字符和已计算条数。
        chars_so_far, messages_counted = 0, 0
        # 一问一答。
        while True:
            # 等下一条。
            try:
                # 空闲超时就离开。
                try:
                    # 下一条 JSON。
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=WS_IDLE_TIMEOUT_SECONDS)
                # 太久没说话。
                except asyncio.TimeoutError:
                    # 关掉。
                    await websocket.close(code=1001)
                    # 离开循环。
                    break
                # 只处理问题。
                if message.get("type") != "query":
                    # 其它类型忽略。
                    continue
                # 频率。
                if not check_rate_limit(ip):
                    # 错误。
                    await _safe_send(websocket, {"type": "error", "message": "发送太频繁，请稍后再试。"})
                    # 下一轮。
                    continue
                # 问题正文。
                user_query = message.get("message", "")
                # 必须是非空字符串。
                if not isinstance(user_query, str) or not user_query.strip():
                    # 错误。
                    await _safe_send(websocket, {"type": "error", "message": "问题不能为空。"})
                    # 下一轮。
                    continue
                # 太长。
                if len(user_query) > MAX_QUERY_LENGTH:
                    # 错误。
                    await _safe_send(websocket, {"type": "error", "message": f"问题最长 {MAX_QUERY_LENGTH} 字。"})
                    # 下一轮。
                    continue
                # 操作员付费才扣额度。用户自己的密钥不扣。
                if operator_paid:
                    # 扣。
                    try:
                        # 加一。
                        await check_and_charge_budget(user_id)
                    # 超了。
                    except LLMBudgetExceeded:
                        # 错误。
                        await _safe_send(websocket, {"type": "error", "message": "今天的模型次数已经用完。"})
                        # 下一轮。
                        continue
                # 落库用户问题。
                if session_id:
                    # 不等待。
                    asyncio.create_task(save_message(session_id, "user", user_query))
                # 放进上下文。
                conversation_history.append(HumanMessage(content=user_query))
                # 完整回答。
                full_response = ""
                # 流。
                try:
                    # 逐个事件。
                    async for event in agent.stream({"messages": conversation_history}):
                        # 发给页面。发送失败说明人走了。
                        if not await _safe_send(websocket, event):
                            # 结束连接处理。
                            return
                        # 完整回答单独记下来。
                        if event.get("type") == "response":
                            # 正文。
                            full_response = event.get("message") or ""
                # 模型太慢。
                except LLMTimeoutError:
                    # 错误。
                    await _safe_send(websocket, {"type": "error", "message": "模型超时，请缩短问题再试。"})
                # 其它错误不把内部细节给页面。
                except Exception:
                    # 日志。
                    logger.exception("query failed for %s", ticker)
                    # 错误。
                    await _safe_send(websocket, {"type": "error", "message": "这次分析失败，请再试一次。"})
                # 有回答就保存。
                if full_response:
                    # 放进上下文。
                    conversation_history.append(AIMessage(content=full_response))
                    # 落库。
                    if session_id:
                        # 不等待。
                        asyncio.create_task(save_message(session_id, "assistant", full_response))
                    # 估算长度。
                    _tokens, chars_so_far, messages_counted = estimate_tokens_incremental(
                        # 当前上下文。
                        conversation_history,
                        # 上次字符。
                        chars_so_far,
                        # 上次条数。
                        messages_counted,
                    )
                    # 超过大约四分之一上下文就压缩。
                    if _tokens > token_threshold:
                        # 压缩。数据库原文还在。
                        conversation_history = await compress_history(session_id, conversation_history, llm)
                        # 累计作废，下一轮重算。
                        chars_so_far, messages_counted = 0, 0
            # 对方关掉。
            except WebSocketDisconnect:
                # 离开。
                break
    # 对方在认证前就走了。
    except WebSocketDisconnect:
        # 正常结束。
        return
