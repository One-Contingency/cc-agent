# 第 12 阶段。早报。新闻和「上次以来」都在模型写完之后填进去，不让模型编。

# 结果对象。
from dataclasses import dataclass
# 观点只能是这四个词。
from typing import Literal

# 15 分钟缓存。
from cachetools import TTLCache
# 输出形状。
from pydantic import BaseModel, Field

# 提示词。
from agents.prompts import DAILY_BRIEFING_SYSTEM_PROMPT
# 大盘。
from agents.market_analysis.regime_detector import MarketRegimeDetector
# 行情。
from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval
# 指标。
from agents.technical_workflow.process_technical_indicators import TechnicalIndicators


# 一条新闻。模型不填，搜索之后再塞进来。
class NewsItem(BaseModel):
    # 标题。
    headline: str
    # 链接。
    url: str | None = None
    # 时间。
    published_at: str | None = None


# 一只股票。
class TickerBriefing(BaseModel):
    # 代码。
    ticker: str
    # 价格。
    price: float = 0
    # 涨跌幅。
    change_pct: float = 0
    # 一句话技术信号。
    technical_signal: str = ""
    # 新闻。模型应留空。
    news_items: list[NewsItem] = Field(default_factory=list)
    # 观点。
    outlook: Literal["bullish", "bearish", "neutral", "mixed"] = "neutral"


# 整份早报。
class DailyBriefingAnalysis(BaseModel):
    # 大盘状态。
    market_regime: str
    # 这意味着什么。
    market_positioning: str
    # 每只股票。
    tickers: list[TickerBriefing]
    # 提醒。
    alerts: list[str] = Field(default_factory=list)
    # 免责声明。
    disclaimer: str = "这是分析说明，不是投资建议。"
    # 和上一份的差别。模型应留空。
    since_last: list[str] = Field(default_factory=list)
    # 上一份是什么时候。
    since_last_label: str | None = None

    # 给页面的正文。
    def to_markdown(self) -> str:
        # 行。
        lines = [f"## 大盘\n{self.market_regime}", self.market_positioning]
        # 上次以来。
        if self.since_last:
            # 标题。
            lines.append("## 上次以来")
            # 每条。
            for item in self.since_last:
                # 列表。
                lines.append(f"- {item}")
        # 个股。
        for ticker in self.tickers:
            # 标题。
            lines.append(f"## {ticker.ticker} {ticker.outlook}")
            # 价格。
            lines.append(f"价格 {ticker.price}（{ticker.change_pct:+.2f}%）")
            # 信号。
            lines.append(ticker.technical_signal)
            # 新闻。
            for news in ticker.news_items:
                # 一条。
                lines.append(f"- {news.headline}")
        # 提醒。
        if self.alerts:
            # 标题。
            lines.append("## 提醒")
            # 每条。
            for alert in self.alerts:
                # 列表。
                lines.append(f"- {alert}")
        # 拼成一段。
        return "\n".join(lines)


# generate 的返回值。
@dataclass
class BriefingResult:
    # 结构化早报。
    analysis: DailyBriefingAnalysis
    # 思考。结构化输出通常没有，留空。
    thinking: str = ""


# 生成和缓存。
class BriefingService:
    # 记住模型和可选的研究密钥。
    def __init__(self, llm, tavily_api_key: str | None = None):
        # 模型。
        self.llm = llm
        # 新闻密钥。
        self.tavily_api_key = tavily_api_key
        # 15 分钟。键是用户、模型和股票列表。
        self._cache: TTLCache = TTLCache(maxsize=128, ttl=15 * 60)

    # 同步生成。路由会把它丢到线程里，避免堵住事件循环。
    def generate(self, tickers: list[str], user_id: str, model_id: str, previous_briefing: dict | None = None) -> BriefingResult:
        # 缓存键。顺序不影响。
        cache_key = f"{user_id}:{model_id}:{','.join(sorted(tickers))}"
        # 命中。
        cached = self._cache.get(cache_key)
        # 有缓存。
        if cached is not None:
            # 直接返回。
            return cached
        # 行情材料。
        materials = self._materials(tickers)
        # 填提示词。
        prompt = DAILY_BRIEFING_SYSTEM_PROMPT.format(materials=materials)
        # 强制填结构。
        analysis = self.llm.with_structured_output(DailyBriefingAnalysis).invoke(prompt)
        # 模型可能编了新闻，这里清掉再填真实的。
        news = self._news(tickers)
        # 逐只覆盖。
        for item in analysis.tickers:
            # 真实新闻，没有就是空列表。
            item.news_items = news.get(item.ticker.upper(), [])
        # 和上一份比。模型填的 since_last 也丢掉。
        analysis.since_last = self._diff(analysis, previous_briefing)
        # 结果。
        result = BriefingResult(analysis=analysis, thinking="")
        # 放进缓存。
        self._cache[cache_key] = result
        # 返回。
        return result

    # 每只股票的价格和指标，加大盘状态。
    def _materials(self, tickers: list[str]) -> str:
        # 大盘。失败就写未知。
        try:
            # 检测。
            regime = MarketRegimeDetector().detect_regime()
        # 失败。
        except Exception:
            # 占位。
            regime = {"trend": "unknown", "volatility": "unknown", "phase": "unknown"}
        # 文本。
        lines = [f"大盘：{regime}"]
        # 每只股票。
        for ticker in tickers:
            # 单只失败不影响其它。
            try:
                # 下载器。
                source = YahooFinanceDataRetrieval(ticker)
                # 一年日线。
                frame = source.get_historical_prices(period="1y", interval="1d")
                # 指标。
                technical = TechnicalIndicators(ticker).calculate_all_indicators(frame)
                # 现价。
                live = source.get_live_price()
                # 一行材料。
                lines.append(f"{ticker} 现价 {live} 指标 {technical}")
            # 失败。
            except Exception as exc:
                # 记原因类型。
                lines.append(f"{ticker} 行情不可用：{type(exc).__name__}")
        # 拼起来给模型。
        return "\n".join(lines)

    # 有密钥才搜新闻。没有就全部空列表。
    def _news(self, tickers: list[str]) -> dict[str, list[NewsItem]]:
        # 结果。
        found: dict[str, list[NewsItem]] = {}
        # 没密钥。
        if not self.tavily_api_key:
            # 空。
            return found
        # 导入。
        try:
            # 搜索。
            from langchain_tavily import TavilySearch
        # 没装。
        except Exception:
            # 空。
            return found
        # 每只最多一条请求。
        for ticker in tickers:
            # 单只失败跳过。
            try:
                # 最多 3 条。
                search = TavilySearch(max_results=3, tavily_api_key=self.tavily_api_key)
                # 搜索。
                raw = search.invoke(f"{ticker} stock news")
                # 收成新闻对象。
                found[ticker.upper()] = self._parse_news(raw)
            # 失败。
            except Exception:
                # 这只没有新闻。
                found[ticker.upper()] = []
        # 全部。
        return found

    # Tavily 的返回形状不稳定，只取能看见标题的条目。
    def _parse_news(self, raw) -> list[NewsItem]:
        # 结果。
        items: list[NewsItem] = []
        # 可能是字典里的 results。
        rows = raw.get("results") if isinstance(raw, dict) else raw
        # 不是列表就没有。
        if not isinstance(rows, list):
            # 空。
            return items
        # 最多 3 条。
        for row in rows[:3]:
            # 不是字典就跳过。
            if not isinstance(row, dict):
                # 下一条。
                continue
            # 标题。
            headline = row.get("title") or row.get("content")
            # 没有标题。
            if not headline:
                # 跳过。
                continue
            # 一条真实新闻。
            items.append(NewsItem(headline=str(headline)[:300], url=row.get("url"), published_at=row.get("published_date")))
        # 返回。
        return items

    # 同一只股票观点变了，或价格变了，就写一句。
    def _diff(self, current: DailyBriefingAnalysis, previous: dict | None) -> list[str]:
        # 没有上一份。
        if not previous:
            # 空。
            return []
        # 上一份的原文。
        raw = previous.get("raw_json")
        # 没有结构。
        if not raw:
            # 空。
            return []
        # 解析。
        try:
            # 用同一套模型读。
            old = DailyBriefingAnalysis.model_validate_json(raw)
        # 旧数据对不上。
        except Exception:
            # 不比较。
            return []
        # 旧的按代码索引。
        old_by_ticker = {item.ticker.upper(): item for item in old.tickers}
        # 句子。
        notes: list[str] = []
        # 新的每一只。
        for item in current.tickers:
            # 旧的。
            before = old_by_ticker.get(item.ticker.upper())
            # 上次没有。
            if before is None:
                # 新加入。
                notes.append(f"{item.ticker} 是新加入的。")
                # 下一只。
                continue
            # 观点变了。
            if before.outlook != item.outlook:
                # 一句。
                notes.append(f"{item.ticker} 观点从 {before.outlook} 变成 {item.outlook}。")
            # 价格变了超过 1%。
            if before.price and abs(item.price - before.price) / before.price > 0.01:
                # 一句。
                notes.append(f"{item.ticker} 价格从 {before.price} 到 {item.price}。")
        # 返回。
        return notes
