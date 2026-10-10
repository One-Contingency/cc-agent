# 第 10 阶段。有 Tavily 密钥才创建网页研究工具。

# 工具包装。
from langchain_core.tools import Tool


# 搜这家公司的新闻。失败时返回说明，不让整个分析中断。
def _news(ticker: str, api_key: str) -> str:
    # 导入放在函数里，没装包时其它工具仍能用。
    try:
        # Tavily 的搜索工具。
        from langchain_tavily import TavilySearch
        # 最多三条。
        search = TavilySearch(max_results=3, tavily_api_key=api_key)
        # 查询词带上股票代码。
        result = search.invoke(f"{ticker} latest company news")
        # 转成文本。
        return f"{ticker} 新闻：{result}"
    # 密钥或网络失败。
    except Exception as exc:
        # 给模型看的失败原因，不含密钥。
        return f"{ticker} 新闻暂时不可用：{type(exc).__name__}"


# 没有密钥时返回空列表，规划器会被告知研究不可用。
def create_research_tools(ticker: str, tavily_api_key: str | None) -> list[Tool]:
    # 没密钥。
    if not tavily_api_key:
        # 不创建。
        return []
    # 一个工具。
    return [
        # 新闻。
        Tool.from_function(
            # 名字。
            name="get_company_news",
            # 说明。
            description="搜索这家公司最近的新闻。",
            # 实现。
            func=lambda query="": _news(ticker, tavily_api_key),
        )
    ]
