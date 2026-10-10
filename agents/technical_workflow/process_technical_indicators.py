# 第 10 阶段。用收盘价算 RSI 和 MACD，不调用模型。


# 给一只股票算指标。数据由调用方传入。
class TechnicalIndicators:
    # 记住代码，方便结果里带上它。
    def __init__(self, ticker: str):
        # 股票代码。
        self.ticker = ticker

    # 返回 rsi 和 macd 两个字典。
    def calculate_all_indicators(self, frame) -> dict:
        # 没有收盘价就给空结果。
        if frame is None or getattr(frame, "empty", True) or "Close" not in frame.columns:
            # 调用方自己判断空。
            return {"rsi": {}, "macd": {}}
        # 收盘价序列。
        close = frame["Close"].dropna()
        # 数据太短，滚动窗口算不出来。
        if len(close) < 26:
            # 只返回最后价格。
            return {"rsi": {}, "macd": {}, "last_close": round(float(close.iloc[-1]), 2)}
        # 涨跌。
        delta = close.diff()
        # 平均上涨。
        gain = delta.clip(lower=0).rolling(14).mean()
        # 平均下跌。
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        # 相对强弱。分母为 0 时用一个很小的数。
        rs = gain / loss.replace(0, 1e-9)
        # RSI。
        rsi_value = float((100 - (100 / (1 + rs))).iloc[-1])
        # 12 日和 26 日指数均线。
        ema12 = close.ewm(span=12, adjust=False).mean()
        # 慢线。
        ema26 = close.ewm(span=26, adjust=False).mean()
        # MACD 线。
        macd_line = ema12 - ema26
        # 信号线。
        signal = macd_line.ewm(span=9, adjust=False).mean()
        # 两个指标加最后收盘价。
        return {
            # RSI 取最后一天。
            "rsi": {"value": round(rsi_value, 2)},
            # MACD 和信号线。
            "macd": {"macd": round(float(macd_line.iloc[-1]), 4), "signal": round(float(signal.iloc[-1]), 4)},
            # 最后收盘价，早报要用。
            "last_close": round(float(close.iloc[-1]), 2),
        }
