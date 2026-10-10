# 第 10 阶段声明名字，第 11 阶段接上 SEC 下载和摘要。

# 把工具结果收成文本，同时带上申报编号，方便后面比对冲突。
import json

# 工具包装。
from langchain_core.tools import Tool

# 摘要提示词。
from agents.prompts import RISK_SUMMARY_PROMPT
# 下载。
from agents.sec_workflow.get_SEC_data import SECDataRetrieval
# 摘要。
from agents.sec_workflow.sec_llm_models import summarize_risks


# 风险摘要。返回 JSON 字符串，里面有 filing_ref 和 event_type。
async def _risk(ticker: str, llm) -> str:
    # 下载。
    filing = SECDataRetrieval(ticker).latest_risk_text()
    # 没下载到。
    if not filing.get("text"):
        # 仍返回结构，方便调用方判断。
        return json.dumps({"filing_ref": "", "event_type": "risk", "text": filing.get("error") or "没有 10-K。"}, ensure_ascii=False)
    # 让模型概括。工具模型思考是关着的。
    text = await summarize_risks(llm, ticker, filing["text"])
    # 带上申报编号。对账时只看同一份文件上的 event_type。
    return json.dumps(
        {
            # 申报编号。
            "filing_ref": filing.get("accession") or "",
            # 这一步的事件类型。
            "event_type": "risk",
            # 摘要。
            "text": text,
        },
        # 中文不转义。
        ensure_ascii=False,
    )


# 财报工具。目前开放风险摘要，名字和提示词一致。
def create_sec_tools(ticker: str, llm) -> list[Tool]:
    # 列表。
    return [
        # 风险。
        Tool.from_function(
            # 名字。
            name="get_risk_factors_summary",
            # 说明。
            description="概括最新 10-K 的风险因素。",
            # 同步占位。
            func=lambda query="": "请使用异步调用。",
            # 异步实现。图会 ainvoke 空字符串。
            coroutine=lambda query="": _risk(ticker, llm),
        )
    ]
