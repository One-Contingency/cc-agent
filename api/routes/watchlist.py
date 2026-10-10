# 第 12 阶段。自选最多 10 只。早报 15 分钟缓存，新闻在模型之后填入。
# 第 13 阶段给早报加每小时 5 次，并用 llm_slot 包住生成。

# 线程和超时。
import asyncio
# 提醒列表存成 JSON。
import json
# 日志。
import logging
# 超时。
import os

# 路由。
from fastapi import APIRouter, Depends, HTTPException, Query, Request

# 自选和早报。
from api.db import (
    add_to_watchlist,
    get_briefing_history,
    get_recent_briefings,
    get_watchlist,
    get_watchlist_enriched,
    remove_from_watchlist,
    save_briefing,
)
# 用户。
from api.dependencies import ApiKeys, get_api_keys
# 股票代码。
from api.validators import TICKER_RE
# 补名称。
from api.enrichment import enrich_company
# 名额和额度。
from api.llm_concurrency import LLMBudgetExceeded, LLMConcurrencyExceeded, check_and_charge_budget, llm_slot
# 频率。
from api.rate_limit import check_rest_rate_limit, client_ip, rate_limit_key
# 模型。
from agents.llm_factory import ThinkingConfig, create_llm
# 清单。
from agents.model_registry import get_default_model, get_model

# 日志。
logger = logging.getLogger(__name__)
# 前缀 /watchlist。
router = APIRouter(prefix="/watchlist", tags=["watchlist"])
# 整份早报最长 120 秒。
BRIEFING_TIMEOUT_SECONDS = float(os.getenv("BRIEFING_TIMEOUT_SECONDS", "120"))


# 列表。
@router.get("")
async def list_watchlist(keys: ApiKeys = Depends(get_api_keys)):
    # 用户。
    user_id = keys.require_user_id()
    # 带名称。
    rows = await get_watchlist_enriched(user_id)
    # 返回。
    return {"tickers": rows}


# 添加。满 10 只或重复都是 409。
@router.post("")
async def add_ticker(data: dict, keys: ApiKeys = Depends(get_api_keys)):
    # 用户。
    user_id = keys.require_user_id()
    # 代码。
    ticker = str(data.get("ticker") or "").strip().upper()
    # 空或不合法。
    if not ticker or not TICKER_RE.match(ticker):
        # 422。
        raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    # 插入。
    added = await add_to_watchlist(ticker, user_id)
    # 失败。
    if not added:
        # 409。
        raise HTTPException(status_code=409, detail="Ticker already in watchlist or watchlist full (max 10)")
    # 补名称。失败不影响添加。
    try:
        # 补。
        await enrich_company(ticker)
    # 失败。
    except Exception:
        # 忽略。
        pass
    # 成功。
    return {"success": True, "ticker": ticker}


# 移除。
@router.delete("/{ticker}")
async def remove_ticker(ticker: str, keys: ApiKeys = Depends(get_api_keys)):
    # 用户。
    user_id = keys.require_user_id()
    # 删除。
    removed = await remove_from_watchlist(ticker, user_id)
    # 本来就没有。
    if not removed:
        # 404。
        raise HTTPException(status_code=404, detail="Ticker not in watchlist")
    # 成功。
    return {"success": True}


# 生成早报。
@router.get("/briefing")
async def get_briefing(request: Request, keys: ApiKeys = Depends(get_api_keys)):
    # 用户。
    user_id = keys.require_user_id()
    # 每小时 5 次。
    if not check_rest_rate_limit(rate_limit_key(user_id, client_ip(request)), "briefing", 5, 3600):
        # 429。
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    # 自选。
    rows = await get_watchlist(user_id)
    # 空。
    if not rows:
        # 400。
        raise HTTPException(status_code=400, detail="Watchlist is empty")
    # 模型。
    model = get_model(keys.model_id or "") or get_default_model()
    # 密钥。没有就 422。
    api_key = keys.require_provider_key(model.provider)
    # 操作员密钥才扣额度。
    if keys.is_operator_paid(model.provider):
        # 扣。
        try:
            # 加一。
            await check_and_charge_budget(user_id)
        # 超了。
        except LLMBudgetExceeded as exc:
            # 429。
            raise HTTPException(status_code=429, detail=str(exc)) from exc
    # 能思考就打开。早报不是工具调用。
    thinking = ThinkingConfig(enabled=True, level="medium") if model.thinking_capable else None
    # 模型。
    llm = create_llm(model.id, api_key, thinking=thinking)
    # 服务。缓存键含用户、模型和股票。
    from agents.briefing.briefing_service import BriefingService
    # 实例。
    service = BriefingService(llm, tavily_api_key=keys.tavily_api_key)
    # 代码。
    tickers = [row["ticker"] for row in rows]
    # 上一份，用来算 since_last。
    prior = await get_recent_briefings(user_id, limit=1)
    # 可能没有。
    previous = prior[0] if prior else None
    # 生成。
    try:
        # 占名额，并限制总时长。
        async with llm_slot():
            # 同步生成丢到线程。
            result = await asyncio.wait_for(
                # 线程。
                asyncio.to_thread(service.generate, tickers, user_id, model.id, previous),
                # 超时。
                timeout=BRIEFING_TIMEOUT_SECONDS,
            )
    # 超时。
    except asyncio.TimeoutError as exc:
        # 504。
        raise HTTPException(status_code=504, detail="Briefing generation timed out") from exc
    # 排队太久。
    except LLMConcurrencyExceeded as exc:
        # 503。
        raise HTTPException(status_code=503, detail="Server busy, retry shortly") from exc
    # 结构。
    analysis = result.analysis
    # 落库用的个股。补上 news_summary，表里没有新闻列表列。
    stored = []
    # 每只。
    for item in analysis.tickers:
        # 转字典。
        data = item.model_dump()
        # 第一条新闻的标题。
        first = item.news_items[0] if item.news_items else None
        # 摘要。
        data["news_summary"] = first.headline if first else ""
        # 链接。
        data["news_url"] = first.url if first else None
        # 放进列表。
        stored.append(data)
    # 写库失败也不让早报本身失败。
    try:
        # 保存。
        await save_briefing(
            # 全文。
            raw_json=analysis.model_dump_json(),
            # 大盘。
            market_regime=analysis.market_regime,
            # 含义。
            market_positioning=analysis.market_positioning,
            # 提醒。
            alerts_json=json.dumps(analysis.alerts, ensure_ascii=False),
            # 思考。
            thinking=result.thinking or None,
            # 个股。
            tickers=stored,
            # 用户。
            user_id=user_id,
        )
    # 失败。
    except Exception:
        # 记日志。
        logger.exception("save briefing failed")
    # 返回。
    return {
        # 正文。
        "briefing": analysis.to_markdown(),
        # 思考。
        "thinking": result.thinking,
        # 结构。
        "structured": analysis.model_dump(),
        # 代码。
        "tickers": tickers,
    }


# 这个用户的早报列表。
@router.get("/briefing/history")
async def briefing_history(keys: ApiKeys = Depends(get_api_keys)):
    # 用户。
    user_id = keys.require_user_id()
    # 最近 20 条。
    rows = await get_recent_briefings(user_id, limit=20)
    # 返回。
    return {"briefings": rows}


# 某只股票的早报历史。
@router.get("/briefing/history/{ticker}")
async def briefing_history_by_ticker(
    # 代码。
    ticker: str,
    # 天数。
    days: int = Query(30, ge=1, le=365),
    # 用户。
    keys: ApiKeys = Depends(get_api_keys),
):
    # 用户。
    user_id = keys.require_user_id()
    # 查询。
    history = await get_briefing_history(ticker, user_id, days=days)
    # 返回。
    return {"ticker": ticker.upper(), "history": history}
