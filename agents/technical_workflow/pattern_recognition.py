# 第 10 阶段。用最近几天的高低点做一个很粗的形态判断。


# 没有形态时返回空列表。
class PatternRecognitionEngine:
    # 看最后 20 根 K 线有没有明显的双顶或双底迹象。
    def detect_all_patterns(self, frame) -> list[dict]:
        # 数据不够就不判断。
        if frame is None or len(frame) < 20:
            # 空列表。
            return []
        # 最近 20 根的最高价和最低价。
        high = float(frame["High"].tail(20).max())
        # 最低。
        low = float(frame["Low"].tail(20).min())
        # 最后收盘价。
        last = float(frame["Close"].iloc[-1])
        # 靠近区间上沿，记成可能的顶部。
        if high != low and (last - low) / (high - low) > 0.85:
            # 一个看跌形态。
            return [{"type": "near_high", "direction": "bearish", "confidence": 0.4, "status": "recent"}]
        # 靠近区间下沿。
        if high != low and (last - low) / (high - low) < 0.15:
            # 一个看涨形态。
            return [{"type": "near_low", "direction": "bullish", "confidence": 0.4, "status": "recent"}]
        # 在中间，不报形态。
        return []
