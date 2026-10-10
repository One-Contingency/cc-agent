# 第 10 阶段。从雅虎拉行情和公司资料。

# 雅虎财经。
import yfinance as yf


# 绑一只股票或一个指数。
class YahooFinanceDataRetrieval:
    # 记住代码，并建雅虎对象。
    def __init__(self, ticker: str):
        # 调用方传入的代码。
        self.ticker = ticker
        # 真正去下载的对象。
        self._ticker = yf.Ticker(ticker)

    # 一段日线或其它周期。
    def get_historical_prices(self, period: str = "1y", interval: str = "1d"):
        # 交给雅虎。没有数据时可能是空表。
        return self._ticker.history(period=period, interval=interval)

    # 公司资料字典。失败时返回空字典。
    def get_company_profile(self) -> dict:
        # info 可能抛错或是 None。
        try:
            # 读资料。
            info = self._ticker.info or {}
        except Exception:
            # 网络失败就当没有。
            info = {}
        # 交给概览。
        return info

    # 现价和前收。资料里没有现价时，用最近一根日线。
    def get_live_price(self) -> dict:
        # 复用公司资料。
        info = self.get_company_profile()
        # 最新价。有的代码只给 currentPrice。
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        # 前收。
        previous = info.get("previousClose")
        # 资料里没有现价。
        if price is None:
            # 最近几天的日线。
            frame = self.get_historical_prices(period="5d", interval="1d")
            # 有收盘价。
            if frame is not None and not getattr(frame, "empty", True):
                # 最后一根。
                price = float(frame["Close"].iloc[-1])
                # 前收也没有时用倒数第二根。
                if previous is None and len(frame) > 1:
                    # 前一根收盘。
                    previous = float(frame["Close"].iloc[-2])
        # 两个价格。
        return {"price": price, "previous_close": previous}
