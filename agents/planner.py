# 第 10 阶段。把问题分成简单或复杂，复杂问题拆成步骤。

# 步骤上限可以来自环境变量。
import os
# 步骤列表的类型。
from typing import Literal

# 结构化输出的形状。
from pydantic import BaseModel, Field

# 分类和拆步用的提示词。
from agents.prompts import QUERY_CLASSIFIER_PROMPT, QUERY_PLANNER_SYSTEM_PROMPT, TOOL_CAPABILITIES

# 最多 15 步，避免一次问题拆出无限工具调用。
MAX_PLAN_STEPS = int(os.getenv("MAX_PLAN_STEPS", "15"))


# 计划里的一步。
class AnalysisStep(BaseModel):
    # 步号。
    id: int = Field(description="Step number")
    # 这一步做什么。
    action: str = Field(description="What to do", max_length=500)
    # 工具名，必须来自清单。
    tool: str = Field(description="Tool name", max_length=100)
    # 为什么需要这一步。
    rationale: str = Field(description="Why", max_length=500)
    # 依赖哪些步骤。图里并行执行时不看这个字段。
    depends_on: list[int] = Field(default_factory=list, max_length=20)


# 难度分类。
class QueryClassification(BaseModel):
    # 四档之一。
    complexity: Literal["simple", "moderate", "complex", "unclear"]
    # 一句理由。
    reasoning: str = Field(max_length=1000)
    # 估计要用几个工具。
    estimated_tools: int = Field(ge=0, le=20)


# 一整份计划。
class QueryPlan(BaseModel):
    # 难度原文。
    query_type: str = Field(max_length=50)
    # 要不要拆步。
    requires_planning: bool
    # 步骤。最多 MAX_PLAN_STEPS 个。
    steps: list[AnalysisStep] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)
    # 最后怎么合并。
    synthesis_approach: str = Field(default="", max_length=2000)


# 分类和拆步都用不开思考的模型。
class QueryPlanner:
    # 记住模型、股票，以及有没有网页研究。
    def __init__(self, llm, ticker: str, has_research_tools: bool = False):
        # 原始模型。
        self.llm = llm
        # 股票代码。
        self.ticker = ticker
        # 研究工具是否装上了。
        self.has_research_tools = has_research_tools
        # 拆步时强制填 QueryPlan。
        self.plan_llm = llm.with_structured_output(QueryPlan)
        # 分类时强制填 QueryClassification。
        self.classify_llm = llm.with_structured_output(QueryClassification)

    # 判断难度。
    def classify_query(self, query: str) -> QueryClassification:
        # 有没有研究工具，写进提示词。
        research_note = "研究工具可用。" if self.has_research_tools else "研究工具不可用。"
        # 填模板。
        prompt = QUERY_CLASSIFIER_PROMPT.format(
            # 股票。
            ticker=self.ticker,
            # 工具说明。
            tool_capabilities=TOOL_CAPABILITIES,
            # 研究是否可用。
            research_note=research_note,
            # 用户问题。
            query=query,
        )
        # 让模型填结构。
        return self.classify_llm.invoke(prompt)

    # 拆成步骤。
    def create_plan(self, query: str) -> QueryPlan:
        # 研究工具说明。
        research_note = "研究工具可用。" if self.has_research_tools else "只使用行情和财报工具。"
        # 填模板。
        prompt = QUERY_PLANNER_SYSTEM_PROMPT.format(
            # 股票。
            ticker=self.ticker,
            # 工具说明。
            tool_capabilities=TOOL_CAPABILITIES,
            # 研究是否可用。
            research_note=research_note,
            # 用户问题。
            query=query,
        )
        # 返回计划。
        return self.plan_llm.invoke(prompt)

    # simple 且只要一个工具时不拆。
    def should_plan(self, query: str) -> tuple[bool, QueryClassification]:
        # 先分类。
        classification = self.classify_query(query)
        # 不是简单问题，或者估计要一个以上的工具。
        should = classification.complexity != "simple" or classification.estimated_tools > 1
        # 图再用 complexity 决定走哪条边。
        return should, classification


# 工厂。分析图用这个创建规划器。
def create_planner(llm, ticker: str, has_research_tools: bool = False) -> QueryPlanner:
    # 返回实例。
    return QueryPlanner(llm, ticker, has_research_tools)
