# 第 10 阶段。路由之后，简单问题走一个工具，复杂问题先拆步再并行调用。
# depends_on 不参与调度。对账只比较同一份申报上的 event_type。
# 工具模型思考关闭，总结模型可以打开。聊天不要在整段 stream 外再套 llm_slot。

# 并行调用工具。
import asyncio
# 工具结果可能是 JSON。
import json
# 单次模型调用的最长时间。
import os
# 计划类型。
from typing import Any

# 拆正文。
from agents.llm_utils import extract_text, parse_llm_response
# 规划。
from agents.planner import QueryPlan, create_planner
# 提示词。
from agents.prompts import SEC_AGENT_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT
# 早报工具。第 12 阶段的包已经存在。
from agents.tools.briefing_tools import create_briefing_tools
# 大盘。
from agents.tools.market_tools import create_market_tools
# 新闻。没有密钥就是空列表。
from agents.tools.research_tools import create_research_tools
# 财报。第 11 阶段的下载器已经存在。
from agents.tools.sec_tools import create_sec_tools
# 行情。
from agents.tools.stock_tools import create_stock_tools

# 模型调用超时，默认 120 秒。
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))


# 超时异常。聊天把它变成一条错误事件。
class LLMTimeoutError(RuntimeError):
    # 用父类的文字即可。
    pass


# 带超时的等待。
async def _wait(coro, label: str):
    # 计时。
    try:
        # 等到结果或超时。
        return await asyncio.wait_for(coro, timeout=LLM_TIMEOUT_SECONDS)
    # 超时。
    except asyncio.TimeoutError as exc:
        # 换成业务异常。
        raise LLMTimeoutError(f"{label} timed out") from exc


# 取出最后一条用户问题。
def _latest_query(messages: list) -> str:
    # 从后往前。
    for message in reversed(messages):
        # 用户消息。
        if getattr(message, "type", "") == "human":
            # 正文。
            return str(message.content)
    # 没有。
    return ""


# 组装这只股票能用的工具。
def _create_tools(ticker: str, llm, tavily_api_key: str | None, user_id: str | None) -> list:
    # 行情、大盘、财报、早报，研究是可选的。
    tools = []
    # 行情。
    tools.extend(create_stock_tools(ticker))
    # 大盘。
    tools.extend(create_market_tools())
    # 财报。
    tools.extend(create_sec_tools(ticker, llm))
    # 早报。
    tools.extend(create_briefing_tools(ticker, user_id))
    # 研究。
    tools.extend(create_research_tools(ticker, tavily_api_key))
    # 全部。
    return tools


# 按名字索引。
def _by_name(tools: list) -> dict[str, Any]:
    # 名字到工具。
    return {tool.name: tool for tool in tools}


# 调用工具。规划器传来的文字被忽略，统一传空字符串。
async def _call_tool(tool, label: str) -> str:
    # 带超时。
    result = await _wait(tool.ainvoke(""), label)
    # 有些工具返回消息对象。
    if hasattr(result, "content"):
        # 取正文。
        return str(result.content)
    # 普通字符串。
    return str(result)


# 从工具文本里取出申报编号和事件类型。不是 JSON 就没有。
def _filing_fields(text: str) -> dict:
    # 解析。
    try:
        # 对象。
        data = json.loads(text)
    # 不是 JSON。
    except (json.JSONDecodeError, TypeError):
        # 空。
        return {}
    # 必须是字典。
    if not isinstance(data, dict):
        # 空。
        return {}
    # 两个对账字段。
    return {"filing_ref": data.get("filing_ref") or "", "event_type": data.get("event_type") or "", "text": data.get("text") or text}


# 同一份申报上出现不同 event_type 才算冲突。
def _conflicts(rows: list[dict]) -> list[str]:
    # 按申报编号分组。
    groups: dict[str, set[str]] = {}
    # 逐条。
    for row in rows:
        # 编号。
        ref = row.get("filing_ref") or ""
        # 类型。
        event_type = row.get("event_type") or ""
        # 缺一不可。
        if not ref or not event_type:
            # 行情结果不参与。
            continue
        # 放进集合。
        groups.setdefault(ref, set()).add(event_type)
    # 句子。
    notes = []
    # 每份文件。
    for ref, types in groups.items():
        # 不止一种事件。
        if len(types) > 1:
            # 记下来。
            notes.append(f"{ref} 上同时有 {', '.join(sorted(types))}")
    # 返回。
    return notes


# 给用户看的材料。JSON 只留 text。
def _display(text: str) -> str:
    # 试着取出 text。
    fields = _filing_fields(text)
    # 有正文就用正文。
    if fields.get("text"):
        # 摘要。
        return str(fields["text"])
    # 原样。
    return text


# 流式分析。事件有 node、tool、thinking、token、response。
class PlanningAgent:
    # 记住股票、两个模型和工具。
    def __init__(self, ticker: str, llm, synthesizer_llm, tools: list, has_research: bool):
        # 股票。
        self.ticker = ticker
        # 分类、拆步和工具调用用这个，思考关闭。
        self.llm = llm
        # 总结可以用开着思考的那个。
        self.synthesizer_llm = synthesizer_llm
        # 名字索引。
        self.tools = _by_name(tools)
        # 规划器。
        self.planner = create_planner(llm, ticker, has_research)

    # 聊天调用的入口。
    async def stream(self, inputs: dict, config: dict | None = None):
        # config 留给调用方对齐原接口，这里不用。
        del config
        # 历史。
        messages = inputs.get("messages") or []
        # 最后一条问题。
        query = _latest_query(messages)
        # 开始分类。
        yield {"type": "node", "node": "router", "message": "正在判断问题难度"}
        # 分类。失败就当复杂，走拆步。
        try:
            # 分类结果。classify_query 直接返回难度对象。
            classification = await _wait(asyncio.to_thread(self.planner.classify_query, query), "router")
            # 难度。
            complexity = classification.complexity
        # 分类失败。
        except Exception:
            # 走拆步，避免一个坏分类挡住回答。
            complexity = "complex"
        # 简单问题：选一个工具，再总结。
        if complexity == "simple":
            # 简单路径。
            async for event in self._simple(query):
                # 往外送。
                yield event
            # 结束。
            return
        # 复杂路径。
        async for event in self._planned(query):
            # 往外送。
            yield event

    # 一个工具。按问题里的词选，选不到就用公司资料。
    async def _simple(self, query: str):
        # 节点。
        yield {"type": "node", "node": "react_agent", "message": "正在查询"}
        # 选工具。
        name = self._pick_simple_tool(query)
        # 工具对象。
        tool = self.tools.get(name)
        # 没有就改用公司资料。
        if tool is None:
            # 后备名字。
            name = "get_stock_info"
            # 后备工具。
            tool = self.tools.get(name)
        # 仍然没有。
        if tool is None:
            # 错误事件。
            yield {"type": "error", "message": "没有可用工具。"}
            # 结束。
            return
        # 工具事件。
        yield {"type": "tool", "node": "react_agent", "tool": name, "action": name, "step": 1, "total": 1}
        # 调用。
        text = await _call_tool(tool, name)
        # 总结。
        async for event in self._synthesize(query, [{"tool": name, "text": text}], []):
            # 往外送。
            yield event

    # 用问题里的词粗选一个工具。
    def _pick_simple_tool(self, query: str) -> str:
        # 小写，中英文都能碰到一部分。
        text = query.lower()
        # 风险。
        if "风险" in query or "risk" in text:
            # 财报。
            return "get_risk_factors_summary"
        # 新闻。
        if "新闻" in query or "news" in text:
            # 研究。没有这个工具时上面会退回公司资料。
            return "get_company_news"
        # 大盘。
        if "大盘" in query or "vix" in text or "宏观" in query:
            # 指数。
            return "get_market_overview"
        # 指标。
        if "rsi" in text or "macd" in text or "指标" in query:
            # 技术。
            return "get_technical_analysis"
        # 默认公司资料。
        return "get_stock_info"

    # 拆步、并行、对账、总结。
    async def _planned(self, query: str):
        # 节点。
        yield {"type": "node", "node": "planner", "message": "正在拆步骤"}
        # 计划。
        plan: QueryPlan = await _wait(asyncio.to_thread(self.planner.create_plan, query), "planner")
        # 没有步骤就退回简单路径。
        if not plan.steps:
            # 简单。
            async for event in self._simple(query):
                # 往外送。
                yield event
            # 结束。
            return
        # 只保留认识的工具。depends_on 不看。
        steps = [step for step in plan.steps if step.tool in self.tools]
        # 一个都不认识。
        if not steps:
            # 简单。
            async for event in self._simple(query):
                # 往外送。
                yield event
            # 结束。
            return
        # 并行调用。
        async def run(step):
            # 工具。
            tool = self.tools[step.tool]
            # 空字符串。
            text = await _call_tool(tool, step.tool)
            # 带上步骤。
            return step, text

        # 节点。
        yield {"type": "node", "node": "worker", "message": "正在并行执行"}
        # 一起等。
        done = await asyncio.gather(*(run(step) for step in steps))
        # 材料和对账行。
        materials = []
        # 对账用的结构。
        rows = []
        # 按完成顺序发工具事件。总步数用计划里的步数。
        total = len(steps)
        # 逐个。
        for index, (step, text) in enumerate(done, start=1):
            # 工具事件。
            yield {"type": "tool", "node": "worker", "tool": step.tool, "action": step.action, "step": index, "total": total}
            # 给人看的材料。
            materials.append({"tool": step.tool, "text": text})
            # 对账字段。
            fields = _filing_fields(text)
            # 放进行。
            rows.append(fields)
        # 对账。
        yield {"type": "node", "node": "reconciler", "message": "正在比对结果"}
        # 冲突句子。
        conflicts = _conflicts(rows)
        # 总结。
        async for event in self._synthesize(query, materials, conflicts):
            # 往外送。
            yield event

    # 总结。先发思考，再发 token，最后发完整回答。
    async def _synthesize(self, query: str, materials: list[dict], conflicts: list[str]):
        # 节点。
        yield {"type": "node", "node": "synthesizer", "message": "正在写回答"}
        # 材料文本。
        body = "\n".join(f"{item['tool']}: {_display(item['text'])}" for item in materials)
        # 冲突也放进材料。
        if conflicts:
            # 追加。
            body += "\n冲突：" + "；".join(conflicts)
        # 系统角色用股票名填一下。
        system = SEC_AGENT_SYSTEM_PROMPT.format(ticker=self.ticker)
        # 总结提示。
        prompt = system + "\n" + SYNTHESIS_SYSTEM_PROMPT.format(ticker=self.ticker, query=query, materials=body)
        # 调用总结模型。
        response = await _wait(self.synthesizer_llm.ainvoke(prompt), "synthesizer")
        # 拆开。
        parsed = parse_llm_response(response)
        # 有思考就单独一条。
        if parsed.thinking:
            # 思考事件。
            yield {"type": "thinking", "message": parsed.thinking}
        # 正文当一个 token 块。页面会拼上去。
        if parsed.text:
            # token。
            yield {"type": "token", "message": parsed.text}
        # 完整回答。聊天用这一条落库。
        yield {"type": "response", "message": extract_text(response)}


# 创建分析器。
def create_planning_agent(ticker: str, llm, tavily_api_key: str | None = None, synthesizer_llm=None, user_id: str | None = None, search_budget=None):
    # 免费试用的搜索计量这一版不用。参数留着，和聊天的调用对齐。
    del search_budget
    # 没单独传总结模型就用工具模型。
    summary_llm = synthesizer_llm or llm
    # 工具。
    tools = _create_tools(ticker, llm, tavily_api_key, user_id)
    # 实例。
    return PlanningAgent(ticker, llm, summary_llm, tools, bool(tavily_api_key))


# 聊天导入的就是这个名字。
def create_sec_qa_agent(ticker: str, llm, tavily_api_key: str | None = None, synthesizer_llm=None, user_id: str | None = None, search_budget=None):
    # 转给上面的工厂。
    return create_planning_agent(ticker, llm, tavily_api_key, synthesizer_llm, user_id, search_budget)
