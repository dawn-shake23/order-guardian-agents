from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
from models.llm_client import LLMClient, ModelType


# ==========================================================
# 意图理解（Intent Understanding）
# 任务重写（Task Rewriting）
# 全局分析（Global Analysis）
# 订单数据需求（Data Requirements）
# 业务手册向量检索需求（Knowledge Retrieval Requirements）
# 结构化步骤（Steps）
# 校验点（Validation Points）
# 区分 “订单数据” vs “向量知识” 两类数据源
# 全链路 Pydantic 强校验
# ==========================================================

# -----------------------------------------------------------------------------
# 1. 意图理解（Intent Understanding）
# -----------------------------------------------------------------------------
class IntentUnderstanding(BaseModel):
    raw_query: str
    rewritten_query: str = Field(description="任务重写：模糊用户输入 → 精确可执行语义")
    intent_type: str = Field(description="order_query / payment_check / risk_judge / reconcile / operation")
    constraints: List[str]
    sensitive_flags: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 2. 全局分析（Global Analysis）
# -----------------------------------------------------------------------------
class GlobalAnalysis(BaseModel):
    order_state_analysis: str
    risk_prejudgment: str
    abnormal_level: str = Field(pattern=r"low|medium|high")
    complexity: str = Field(pattern=r"low|medium|high")
    data_dependencies: List[str]


# -----------------------------------------------------------------------------
# 3. 数据需求（订单体系）
# -----------------------------------------------------------------------------
class DataRequirement(BaseModel):
    order_data: List[str]
    payment_data: List[str]
    risk_data: List[str]
    reconciliation_data: List[str]


# -----------------------------------------------------------------------------
# 4. 知识检索需求（业务手册向量库）
# -----------------------------------------------------------------------------
class KnowledgeRetrievalDemand(BaseModel):
    retrieval_queries: List[str]
    retrieval_scenes: List[str] = Field(description="哪些步骤需要向量检索")
    knowledge_type: List[str] = Field(description="rule / process / case / policy")


# -----------------------------------------------------------------------------
# 5. 规划步骤（Claude Code 核心 Step 结构）
# -----------------------------------------------------------------------------
class PlanStep(BaseModel):
    step_id: int = Field(ge=1)
    expert_type: str
    goal: str
    data_used: List[str] = Field(description="该步骤需要哪些订单数据")
    retrieval_used: bool = Field(description="该步骤是否需要查业务手册向量")
    validation_criteria: Dict[str, Any]
    expected_output: str
    depends_on: List[int] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 6. 完整规划（Claude Code 标准 Plan）
# -----------------------------------------------------------------------------
class ExecutionPlan(BaseModel):
    # 基础信息
    session_id: str
    order_id: str

    # Claude Code 核心：意图理解
    intent: IntentUnderstanding

    # Claude Code 核心：全局分析
    global_analysis: GlobalAnalysis

    # 数据需求（订单体系）
    data_requirements: DataRequirement

    # 知识需求（向量手册体系）
    knowledge_demand: KnowledgeRetrievalDemand

    # 步骤
    steps: List[PlanStep] = Field(min_items=1)

    # 最终目标
    final_goal: str
    success_criteria: Dict[str, Any]


# -----------------------------------------------------------------------------
# Plan Agent 元数据
# -----------------------------------------------------------------------------
PLAN_AGENT_META = AgentMeta(
    agent_type="plan",
    version="1.0.0",
    timeout_seconds=30,
    required_fields=["order_id", "abnormal_detail"],
    acl_scopes=["plan:create", "plan:rewrite", "plan:analyze"]
)


# -----------------------------------------------------------------------------
# 真正实现 Claude Code 标准 PlanAgent
# -----------------------------------------------------------------------------
class PlanAgent(BaseWorkerAgent):
    def __init__(self, llm_client: Optional[LLMClient] = None):
        super().__init__(PLAN_AGENT_META)
        # Plan 使用强模型：Qwen14B / Llama3 8B
        self.llm = llm_client or LLMClient(model_type=ModelType.QWEN_14B)

        # 固定提示词（结构化输出，不依赖模型能力）
        self.prompt = """
你是 Claude Code 风格的 Plan 规划器。
你的任务是：
1. 理解用户意图
2. 重写任务（rewriting）
3. 对订单异常做全局分析
4. 明确需要哪些订单数据
5. 明确需要哪些业务手册向量知识
6. 生成可执行、可调度、强校验的步骤列表

输出必须完全符合 ExecutionPlan 结构，不允许额外文本。
"""

    def execute(self, agent_input: AgentInput) -> Dict[str, Any]:
        """
        执行 Claude Code 标准规划：
        意图理解 → 重写 → 全局分析 → 数据需求 → 知识需求 → 步骤
        """
        params = agent_input.params
        order_id = agent_input.order_id
        abnormal_detail = params.get("abnormal_detail", "")

        # 调用强模型生成结构化 Plan
        raw_result = self.llm.generate(
            prompt=self.prompt + f"\n输入：{abnormal_detail}",
            output_schema=ExecutionPlan
        )

        # Pydantic 强校验（无论模型输出多乱，都要通过）
        plan = ExecutionPlan(**raw_result["data"])

        # 返回严格校验通过的规划
        return plan.model_dump()