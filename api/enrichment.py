# 第 11 阶段。第一次看到公司时，用雅虎补上名称和行业。不调用模型。

# 读写公司行。
from api.db import get_company, update_company


# 已经有名称就不再请求网络。
async def enrich_company(ticker: str) -> dict | None:
    # 读现有行。没被跟踪过就是 None。
    company = await get_company(ticker)
    # 没有行。
    if company is None:
        # 不创建。调用方要先 ensure_company。
        return None
    # 名称已经有了。
    if company.get("name"):
        # 直接返回缓存。
        return company
    # 拉雅虎。失败也不影响页面。
    try:
        # 延迟导入，避免这个小模块在导入时就拉行情库。
        from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval
        # 公司资料。
        info = YahooFinanceDataRetrieval(ticker).get_company_profile()
        # 短名优先。
        name = info.get("shortName") or info.get("longName")
        # 行业。
        sector = info.get("sector")
        # 至少有一个才写。
        if name or sector:
            # 更新。
            await update_company(ticker, name=name, sector=sector)
            # 返回值也带上。
            company["name"] = name
            # 行业。
            company["sector"] = sector
    # 网络失败。
    except Exception:
        # 保持空名称，下次再试。
        pass
    # 现有行。
    return company
