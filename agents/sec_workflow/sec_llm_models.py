# 第 11 阶段。用已经创建好的模型概括风险原文。

# 提示词。
from agents.prompts import RISK_SUMMARY_PROMPT
# 只要正文。
from agents.llm_utils import extract_text


# 返回中文摘要。
async def summarize_risks(llm, ticker: str, text: str) -> str:
    # 填模板。原文已经截断。
    prompt = RISK_SUMMARY_PROMPT.format(ticker=ticker, text=text)
    # 调用。思考开关由创建模型的人决定。工具路径是关的。
    response = await llm.ainvoke(prompt)
    # 正文。
    return extract_text(response)
