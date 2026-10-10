# 第 10 阶段。行情工具。调用时忽略模型传来的参数，股票在创建时已经绑死。

# 工具包装。
from langchain_core.tools import Tool

# 行情。
from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval
# 指标。
from agents.technical_workflow.process_technical_indicators import TechnicalIndicators
# 形态。
from agents.technical_workflow.pattern_recognition import PatternRecognitionEngine


# 最近几个交易日的价格。
def _price_history(ticker: str) -> str:
    # 拉一个月，只展示最后 10 天。
    frame = YahooFinanceDataRetrieval(ticker).get_historical_prices(period="1mo", interval="1d")
    # 没有数据。
    if frame is None or frame.empty:
        # 告诉模型。
        return f"{ticker} 没有价格数据。"
    # 最后 10 行。
    tail = frame.tail(10)
    # 文本行。
    lines = [f"{ticker} 最近价格："]
    # 逐日。
    for index, row in tail.iterrows():
        # 日期只取到天。
        day = str(index)[:10]
        # 收盘价。
        lines.append(f"{day} 收盘 {float(row['Close']):.2f}")
    # 拼成一段。
    return "\n".join(lines)


# RSI 和 MACD。
def _technical(ticker: str) -> str:
    # 一年日线。
    frame = YahooFinanceDataRetrieval(ticker).get_historical_prices(period="1y", interval="1d")
    # 计算。
    result = TechnicalIndicators(ticker).calculate_all_indicators(frame)
    # 文本。
    return f"{ticker} 技术指标：{result}"


# 现价和估值。
def _info(ticker: str) -> str:
    # 公司资料。
    info = YahooFinanceDataRetrieval(ticker).get_company_profile()
    # 挑页面和回答会用到的字段。
    picked = {
        # 名称。
        "name": info.get("shortName"),
        # 现价。
        "price": info.get("regularMarketPrice"),
        # 市值。
        "market_cap": info.get("marketCap"),
        # 市盈率。
        "pe": info.get("trailingPE"),
        # 行业。
        "sector": info.get("sector"),
    }
    # 文本。
    return f"{ticker} 公司资料：{picked}"


# 粗形态。
def _patterns(ticker: str) -> str:
    # 一年日线。
    frame = YahooFinanceDataRetrieval(ticker).get_historical_prices(period="1y", interval="1d")
    # 判断。
    found = PatternRecognitionEngine().detect_all_patterns(frame)
    # 文本。
    return f"{ticker} 形态：{found}"


# 绑到一只股票上的四个工具。
def create_stock_tools(ticker: str) -> list[Tool]:
    # 列表。
    return [
        # 价格。
        Tool.from_function(
            # 名字必须和提示词里的一致。
            name="get_stock_price_history",
            # 给规划器看的说明。
            description="最近交易日的收盘价。",
            # 忽略传入文字。
            func=lambda query="": _price_history(ticker),
        ),
        # 指标。
        Tool.from_function(
            # 名字。
            name="get_technical_analysis",
            # 说明。
            description="RSI 和 MACD。",
            # 实现。
            func=lambda query="": _technical(ticker),
        ),
        # 资料。
        Tool.from_function(
            # 名字。
            name="get_stock_info",
            # 说明。
            description="现价、市值和市盈率。",
            # 实现。
            func=lambda query="": _info(ticker),
        ),
        # 形态。
        Tool.from_function(
            # 名字。
            name="get_pattern_detection",
            # 说明。
            description="最近价格靠近区间高点或低点。",
            # 实现。
            func=lambda query="": _patterns(ticker),
        ),
    ]
