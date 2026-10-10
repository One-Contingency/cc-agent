# 第 10 阶段。大盘工具，不绑定某一只股票。

# 工具包装。
from langchain_core.tools import Tool

# 指数也用同一套下载。
from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval


# 指数和波动率的最新收盘。
def _overview() -> str:
    # 四个代码。
    names = {"标普500": "^GSPC", "纳斯达克": "^IXIC", "道琼斯": "^DJI", "VIX": "^VIX"}
    # 文本。
    lines = ["大盘："]
    # 逐个。
    for label, symbol in names.items():
        # 单个失败不影响其它。
        try:
            # 最近几天。
            frame = YahooFinanceDataRetrieval(symbol).get_historical_prices(period="5d", interval="1d")
            # 没有两根就无法算涨跌。
            if frame is None or len(frame) < 2:
                # 记一句。
                lines.append(f"{label}：没有数据")
                # 下一个。
                continue
            # 最新。
            last = float(frame["Close"].iloc[-1])
            # 前一根。
            prev = float(frame["Close"].iloc[-2])
            # 涨跌幅。
            change = (last - prev) / prev * 100
            # 一行。
            lines.append(f"{label} {last:.2f} ({change:+.2f}%)")
        # 网络失败。
        except Exception:
            # 记一句。
            lines.append(f"{label}：没有数据")
    # 拼起来。
    return "\n".join(lines)


# 国债收益率和美元。
def _macro() -> str:
    # 三个代码。
    names = {"十年期国债": "^TNX", "VIX": "^VIX", "美元指数": "DX-Y.NYB"}
    # 文本。
    lines = ["宏观："]
    # 逐个。
    for label, symbol in names.items():
        # 单个失败不影响其它。
        try:
            # 一个月。
            frame = YahooFinanceDataRetrieval(symbol).get_historical_prices(period="1mo", interval="1d")
            # 空。
            if frame is None or frame.empty:
                # 记一句。
                lines.append(f"{label}：没有数据")
                # 下一个。
                continue
            # 最新。
            lines.append(f"{label} {float(frame['Close'].iloc[-1]):.2f}")
        # 网络失败。
        except Exception:
            # 记一句。
            lines.append(f"{label}：没有数据")
    # 拼起来。
    return "\n".join(lines)


# 两个大盘工具。
def create_market_tools() -> list[Tool]:
    # 列表。
    return [
        # 指数。
        Tool.from_function(
            # 名字。
            name="get_market_overview",
            # 说明。
            description="标普、纳斯达克、道琼斯和 VIX 的最新水平。",
            # 实现。
            func=lambda query="": _overview(),
        ),
        # 宏观。
        Tool.from_function(
            # 名字。
            name="get_macro_indicators",
            # 说明。
            description="国债收益率、VIX 和美元指数。",
            # 实现。
            func=lambda query="": _macro(),
        ),
    ]
