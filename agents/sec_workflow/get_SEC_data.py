# 第 11 阶段。按股票取最新 10-K 的风险原文。身份在进程启动时设置一次。

# 截断长度，避免把整份年报塞进模型。
_MAX_CHARS = 12000


# 一只股票的下载器。
class SECDataRetrieval:
    # 记住代码。
    def __init__(self, ticker: str):
        # 股票。
        self.ticker = ticker.upper()

    # 返回申报编号和风险原文。失败时 text 为空，error 有原因。
    def latest_risk_text(self) -> dict:
        # 导入放在方法里。身份已经在启动时设过，这里不再设。
        try:
            # SEC 客户端。
            from edgar import Company
        # 没装包。
        except Exception as exc:
            # 失败结构。
            return {"accession": "", "text": "", "error": f"edgartools 不可用：{type(exc).__name__}"}
        # 下载。
        try:
            # 按代码找公司。
            company = Company(self.ticker)
            # 只要 10-K。
            filings = company.get_filings(form="10-K")
            # 最新一份。
            filing = filings.latest()
            # 没有。
            if filing is None:
                # 空。
                return {"accession": "", "text": "", "error": "没有 10-K。"}
            # 申报编号。
            accession = getattr(filing, "accession_no", "") or ""
            # 风险原文。
            text = self._risk_section(filing)
            # 截断。
            return {"accession": accession, "form": "10-K", "text": text[:_MAX_CHARS], "error": ""}
        # 网络或解析失败。
        except Exception as exc:
            # 失败结构。
            return {"accession": "", "text": "", "error": f"SEC 下载失败：{type(exc).__name__}"}

    # 优先拿 Item 1A，拿不到就用全文前一段。
    def _risk_section(self, filing) -> str:
        # 结构化对象。
        try:
            # 10-K 对象。
            parsed = filing.obj()
            # 风险因素属性。
            risk = getattr(parsed, "risk_factors", None)
            # 有文字。
            if risk:
                # 转成字符串。
                return str(risk)
        # 解析失败就退回全文。
        except Exception:
            # 继续下面的全文。
            pass
        # 全文。
        try:
            # 纯文本。
            return str(filing.text())
        # 连全文都没有。
        except Exception:
            # 空。
            return ""
