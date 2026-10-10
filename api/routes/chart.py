# 第 5 阶段 · 顺序 2
# 写在 validators.py 之后、main.py 挂载路由之前。

# 把同步的雅虎财经调用放到线程里，避免堵住整个后端。
import asyncio

# 路由容器，以及参数不合法、没有数据时返回的错误。
from fastapi import APIRouter, HTTPException, Query
# 把字典包成 JSON 响应，顺便带上缓存头。
from fastapi.responses import JSONResponse
# 雅虎财经。history 取 K 线，download 一次取多只股票的收盘价。
import yfinance as yf

# 第 5 阶段写好的股票代码正则。
from api.validators import TICKER_RE

# 本文件的路由集合。main.py 会把它挂到应用上。
router = APIRouter()

# 页面上的周期名称，对应雅虎财经 history() 接受的 period。
_PERIODS = {
    # 近一周。雅虎用 5d 表示五个交易日。
    "1w": "5d",
    # 近一月。
    "1mo": "1mo",
    # 近三月。
    "3mo": "3mo",
    # 近六月。
    "6mo": "6mo",
    # 近一年。不传 period 时用这个。
    "1y": "1y",
}


# 同步拉取一只股票的日 K。给 to_thread 调用，自己不要写成 async。
def _fetch_candles(ticker: str, yahoo_period: str) -> list[dict]:
    # 按代码建立雅虎对象，并下载这段时间的日线。
    frame = yf.Ticker(ticker).history(period=yahoo_period, interval="1d")
    # 没有数据时返回空列表，调用方据此回 404。
    if frame is None or frame.empty:
        return []
    # 丢掉开高低收任一缺失的行，这种 K 线画不出来。
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    # 准备返回给前端的 K 线列表。
    candles = []
    # 每一行是一个交易日。
    for timestamp, row in frame.iterrows():
        # 成交量缺失时按 0。自己和自己不相等，说明这个值是 NaN。
        volume = 0 if row["Volume"] != row["Volume"] else int(row["Volume"])
        # 转成前端画图需要的六个字段。价格保留两位小数。
        candles.append({
            # 日期字符串，例如 2026-10-09。
            "time": timestamp.strftime("%Y-%m-%d"),
            # 开盘价。
            "open": round(float(row["Open"]), 2),
            # 最高价。
            "high": round(float(row["High"]), 2),
            # 最低价。
            "low": round(float(row["Low"]), 2),
            # 收盘价。
            "close": round(float(row["Close"]), 2),
            # 成交量。
            "volume": volume,
        })
    # 把整段 K 线交回去。
    return candles


# GET /stock/AAPL/chart?period=1y
@router.get("/stock/{ticker}/chart")
async def get_chart_data(
    # 路径里的股票代码，还没转成大写。
    ticker: str,
    # 查询参数。只允许 _PERIODS 里的五个值，默认一年。
    period: str = Query(default="1y"),
):
    # 不认识的周期直接拒绝，避免把任意字符串传给雅虎。
    if period not in _PERIODS:
        raise HTTPException(status_code=422, detail="Invalid period")
    # 校验前统一转成大写，正则只接受大写。
    ticker = ticker.upper()
    # 格式不对就返回 422。
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    # 雅虎的下载是同步的，放到线程里执行。
    candles = await asyncio.to_thread(_fetch_candles, ticker, _PERIODS[period])
    # 一只股票都没查到时返回 404。
    if not candles:
        raise HTTPException(status_code=404, detail=f"No data found for {ticker}")
    # 返回 K 线，并允许浏览器缓存 60 秒。
    return JSONResponse(
        # 正文只有 K 线数组。指标留到第 10 阶段再加。
        content={"candles": candles},
        # 一分钟内重复打开同一张图，浏览器可以先用缓存。
        headers={"Cache-Control": "public, max-age=60"},
    )


# 同步拉取多只股票最近几个交易日的收盘价。
def _fetch_quotes(tickers: list[str]) -> dict:
    # 一次请求下载这些股票近 5 个自然日的日线，用来计算涨跌。
    frame = yf.download(tickers, period="5d", interval="1d", progress=False, threads=False)
    # 每只股票的报价放这里。
    quotes: dict[str, dict] = {}
    # 完全没有数据时，返回空字典。
    if frame is None or frame.empty:
        return quotes
    # 逐只股票取最后两个收盘价。
    for ticker in tickers:
        try:
            # 只有一只股票时，收盘价列是普通列；多只时要再按代码取一列。
            closes = frame["Close"].dropna() if len(tickers) == 1 else frame["Close"][ticker].dropna()
            # 连一个收盘价都没有就跳过这只股票。
            if len(closes) < 1:
                continue
            # 最新收盘价。
            price = round(float(closes.iloc[-1]), 2)
            # 先放价格。有前一日收盘价时再补涨跌。
            quote = {"price": price}
            # 至少两天才能算涨跌额和涨跌幅。
            if len(closes) >= 2 and float(closes.iloc[-2]) != 0:
                # 前一日收盘价。
                previous = round(float(closes.iloc[-2]), 2)
                # 前收盘价。
                quote["previousClose"] = previous
                # 涨跌额。
                quote["change"] = round(price - previous, 2)
                # 涨跌幅，单位是百分比。
                quote["changePercent"] = round((price - previous) / previous * 100, 2)
            # 放进总结果，键是股票代码。
            quotes[ticker] = quote
        # 这只股票不在返回结果里时，跳过，不影响其他股票。
        except (KeyError, IndexError):
            continue
    # 把全部报价交回去。
    return quotes


# POST /stock/quotes，正文是 {"tickers": ["AAPL", "MSFT"]}。
@router.post("/stock/quotes")
async def get_batch_quotes(data: dict):
    # 取出代码列表。
    raw = data.get("tickers", [])
    # 必须是非空列表。
    if not isinstance(raw, list) or len(raw) == 0:
        raise HTTPException(status_code=422, detail="tickers must be a non-empty list")
    # 自选股上限是 10 只，这里一起限制。
    if len(raw) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 tickers per request")
    # 转成大写并去掉空白。不是字符串的项丢掉。
    tickers = [item.strip().upper() for item in raw if isinstance(item, str)]
    # 其中任何一个格式不对，整次请求拒绝。
    for ticker in tickers:
        if not TICKER_RE.match(ticker):
            raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    # 同样把同步下载放到线程里。
    quotes = await asyncio.to_thread(_fetch_quotes, tickers)
    # 返回报价，允许缓存 30 秒。
    return JSONResponse(
        # 键是股票代码，值是价格和涨跌。
        content={"quotes": quotes},
        # 半分钟内重复查询同一批股票，浏览器可以先用缓存。
        headers={"Cache-Control": "public, max-age=30"},
    )
