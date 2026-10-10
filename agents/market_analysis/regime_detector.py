# 第 12 阶段。用 SPY 和 VIX 判断大盘，不调用模型。

# 拉指数行情。
from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval


# 趋势、波动和阶段。
class MarketRegimeDetector:
    # 拉一年 SPY 和三个月 VIX，合成一个字典。
    def detect_regime(self) -> dict:
        # 标普 500 ETF。
        spy = YahooFinanceDataRetrieval("SPY").get_historical_prices(period="1y", interval="1d")
        # 波动率指数。
        vix = YahooFinanceDataRetrieval("^VIX").get_historical_prices(period="3mo", interval="1d")
        # 三项分开算。
        trend = self._trend(spy)
        # 波动。
        volatility = self._volatility(vix)
        # 阶段。
        phase = self._phase(spy)
        # 给概览和早报。
        return {"trend": trend, "volatility": volatility, "phase": phase, "recommendations": [f"{trend} / {volatility} / {phase}"]}

    # 50 日和 200 日均线的关系。
    def _trend(self, spy) -> str:
        # 不够 200 天就不知道。
        if spy is None or len(spy) < 200:
            # 数据不足。
            return "unknown"
        # 收盘价。
        close = spy["Close"]
        # 50 日。
        ma50 = float(close.rolling(50).mean().iloc[-1])
        # 200 日。
        ma200 = float(close.rolling(200).mean().iloc[-1])
        # 最新价。
        price = float(close.iloc[-1])
        # 多头。
        if ma50 > ma200 and price > ma50:
            # 上涨趋势。
            return "bull"
        # 空头。
        if ma50 < ma200 and price < ma50:
            # 下跌趋势。
            return "bear"
        # 两者之间。
        return "transitional"

    # 按 VIX 绝对值分档。
    def _volatility(self, vix) -> str:
        # 没有数据。
        if vix is None or vix.empty:
            # 不知道。
            return "unknown"
        # 最新 VIX。
        value = float(vix["Close"].iloc[-1])
        # 四档。
        if value < 15:
            # 很低。
            return "low"
        # 中等。
        if value < 20:
            # 平常。
            return "moderate"
        # 偏高。
        if value < 30:
            # 升高。
            return "elevated"
        # 很高。
        return "high"

    # 最近 50 天价格方向配合成交量。
    def _phase(self, spy) -> str:
        # 不够 50 天。
        if spy is None or len(spy) < 50:
            # 不知道。
            return "unknown"
        # 最近 50 根收盘价。
        close = spy["Close"].iloc[-50:]
        # 最近 50 根成交量。
        volume = spy["Volume"].iloc[-50:]
        # 价格是涨是跌。
        price_up = float(close.iloc[-1]) >= float(close.iloc[0])
        # 近 10 天均量是否高于 50 天均量。
        volume_up = float(volume.tail(10).mean()) >= float(volume.mean())
        # 四种组合。
        if price_up and volume_up:
            # 价涨量增。
            return "markup"
        # 价涨量缩。
        if price_up:
            # 派发。
            return "distribution"
        # 价跌量增。
        if volume_up:
            # 下跌。
            return "markdown"
        # 价跌量缩。
        return "accumulation"
