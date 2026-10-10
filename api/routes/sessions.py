# 第 9 阶段。会话列表、消息和删除。会话必须同时属于这只股票和这个用户。

# 路由。
from fastapi import APIRouter, Depends, HTTPException, Query

# 数据库。
from api.db import (
    delete_session,
    get_session,
    get_session_by_ticker,
    get_session_messages,
    get_sessions_for_ticker,
    get_tickers,
)
# 用户编号。
from api.dependencies import ApiKeys, get_api_keys
# 股票代码。
from api.validators import TICKER_RE

# 没有前缀，路径就是 /tickers 和 /sessions。
router = APIRouter()


# 这个用户聊过的股票。
@router.get("/tickers")
async def list_tickers(limit: int = 50, keys: ApiKeys = Depends(get_api_keys)):
    # 没有用户不能看别人的历史。
    user_id = keys.require_user_id()
    # 查询。
    tickers = await get_tickers(user_id, limit)
    # 返回。
    return {"tickers": tickers}


# 某只股票下的会话。
@router.get("/sessions")
async def list_sessions(
    # 必须带股票。
    ticker: str = Query(...),
    # 条数。
    limit: int = 50,
    # 用户。
    keys: ApiKeys = Depends(get_api_keys),
):
    # 要求登录身份。本地是 UUID。
    user_id = keys.require_user_id()
    # 查询。
    sessions = await get_sessions_for_ticker(ticker, user_id, limit)
    # 返回。
    return {"sessions": sessions}


# 这只股票已有的那条会话。没有就是 null。
@router.get("/sessions/by-ticker/{ticker}")
async def get_session_for_ticker(ticker: str, keys: ApiKeys = Depends(get_api_keys)):
    # 代码不合法。
    if not TICKER_RE.match(ticker.upper()):
        # 400。
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")
    # 用户。
    user_id = keys.require_user_id()
    # 查询。
    session = await get_session_by_ticker(ticker.upper(), user_id)
    # 可能是 null。
    return {"session": session}


# 确认会话属于这只股票和这个用户。否则 404，避免拿别人的编号读历史。
async def _validate_session_ticker(session_id: str, ticker: str, user_id: str) -> dict:
    # 读会话。
    session = await get_session(session_id)
    # 三条对不上就当不存在。
    if session is None or session["ticker"].upper() != ticker.upper() or session.get("user_id") != user_id:
        # 不透露它是不是别人的。
        raise HTTPException(status_code=404, detail="Session not found")
    # 通过。
    return session


# 一条会话里的消息。
@router.get("/sessions/{session_id}/messages")
async def get_messages(
    # 路径里的会话。
    session_id: str,
    # 必须再带股票，防止只凭会话编号遍历。
    ticker: str = Query(...),
    # 用户。
    keys: ApiKeys = Depends(get_api_keys),
):
    # 用户。
    user_id = keys.require_user_id()
    # 核对归属。
    await _validate_session_ticker(session_id, ticker, user_id)
    # 消息。
    messages = await get_session_messages(session_id)
    # 返回。
    return {"messages": messages}


# 删除会话。
@router.delete("/sessions/{session_id}")
async def remove_session(
    # 会话。
    session_id: str,
    # 股票。
    ticker: str = Query(...),
    # 用户。
    keys: ApiKeys = Depends(get_api_keys),
):
    # 用户。
    user_id = keys.require_user_id()
    # 核对归属。
    await _validate_session_ticker(session_id, ticker, user_id)
    # 删除。
    deleted = await delete_session(session_id)
    # 没删到。
    if not deleted:
        # 404。
        raise HTTPException(status_code=404, detail="Session not found")
    # 成功。
    return {"success": True}
