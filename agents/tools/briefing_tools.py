# 第 10 阶段声明工具，第 12 阶段才真正查早报表。

# 工具包装。
from langchain_core.tools import Tool

# 历史。
from api.db import get_briefing_history, get_recent_briefings


# 这只股票最近的早报句子。
async def _history(ticker: str, user_id: str | None) -> str:
    # 没有用户就没有早报。
    if not user_id:
        # 说明。
        return f"{ticker} 没有用户，查不到早报。"
    # 查 7 天。
    rows = await get_briefing_history(ticker, user_id, days=7)
    # 空。
    if not rows:
        # 说明。
        return f"{ticker} 最近没有早报。"
    # 拼文本。
    lines = [f"{ticker} 早报历史："]
    # 逐条。
    for row in rows:
        # 一行。
        lines.append(f"{row.get('created_at')} {row.get('outlook')} 价格 {row.get('price')}")
    # 返回。
    return "\n".join(lines)


# 这个用户最新一份完整早报的市场判断。
async def _latest(user_id: str | None) -> str:
    # 没有用户。
    if not user_id:
        # 说明。
        return "没有用户，查不到早报。"
    # 只取一条。
    rows = await get_recent_briefings(user_id, limit=1)
    # 空。
    if not rows:
        # 说明。
        return "还没有早报。"
    # 第一条。
    row = rows[0]
    # 市场判断。
    return f"最近早报：{row.get('market_regime')}。{row.get('market_positioning')}"


# 两个早报工具。图里用 ainvoke，所以走协程，避免在正在运行的事件循环里再 asyncio.run。
def create_briefing_tools(ticker: str, user_id: str | None = None) -> list[Tool]:
    # 列表。
    return [
        # 个股历史。
        Tool.from_function(
            # 名字。
            name="get_briefing_history",
            # 说明。
            description="这只股票最近早报里的观点和价格。",
            # 同步占位。图不会走它。
            func=lambda query="": "请使用异步调用。",
            # 真正的实现。
            coroutine=lambda query="": _history(ticker, user_id),
        ),
        # 最新一份。
        Tool.from_function(
            # 名字。
            name="get_latest_briefing",
            # 说明。
            description="这个用户最近一份早报的市场判断。",
            # 同步占位。
            func=lambda query="": "请使用异步调用。",
            # 真正的实现。
            coroutine=lambda query="": _latest(user_id),
        ),
    ]
