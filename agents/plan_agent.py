from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
# 新增：模型调用统一封装（预留 Qwen 14B/Llama 3 8B 接入）
from Model.llm_client import LLMClient, ModelType

# -----------------------------------------------------------------------------
# 1. Plan Agent 专属 Schema（强校验：输出必须是这个结构，不依赖模型）
# 完全对齐 Claude Code：Plan 只输出步骤蓝图，不执行、不调度
# -----------------------------------------------------------------------------
class PlanStep(BaseModel):
    """单一步骤强校验（Pydantic 兜底，模型输出再乱也能校验）"""
    step_id: int = Field(ge=1, description="步骤ID，从1开始递增")
    expert_type: str = Field(description="对应子Agent类型：order/payment/risk/operation/reconciliation")
    task: str = Field(description="当前步骤具体任务")
    required_fields: list[str] = Field(description="当前步骤必须的输入字段")
    description: str = Field(description="步骤说明，明确执行目的")

    # 强校验：expert_type 必须是指定范围（防止模型输出乱码）
    @field_validator('expert_type')
    def expert_type_valid(cls, v):
        valid_types = ["order", "payment", "risk", "operation", "reconciliation"]
        if v not in valid_types:
            raise ValueError(f"expert_type 必须是 {valid_types} 中的一种")
        return v

class ExecutionPlan(BaseModel):
    """完整执行计划强校验（统一输出格式）"""
    session_id: str
    order_id: str
    task_subject: str = Field(description="异常任务主题，如：订单支付失败诊断")
    steps: list[PlanStep] = Field(min_items=1, description="至少1个执行步骤")
    final_goal: str = Field(description="最终会诊目标")

# -----------------------------------------------------------------------------
# 2. Plan Agent 元数据（风控/权限/超时/约束，不变）
# -----------------------------------------------------------------------------
PLAN_AGENT_META = AgentMeta(
    agent_type="plan",
    version="1.0.0",
    timeout_seconds=25,  # 强模型推理稍久，超时设为25s
    required_fields=["order_id", "abnormal_detail"],
    acl_scopes=["plan:create"]
)

# -----------------------------------------------------------------------------
# 3. PlanAgent 核心实现（适配强模型，预留切换口）
# 遵循 Claude Code 思想 + 你的要求：
# ✅ 用 Qwen 14B/Llama 3 8B 做规划（强模型决策）
# ✅ 无状态、无记忆，只输出结构化计划
# ✅ 全链路 Pydantic 校验，不依赖模型输出质量
# ✅ 预留模型切换口，不硬编码
# -----------------------------------------------------------------------------
class PlanAgent(BaseWorkerAgent):
    def __init__(self, llm_client: Optional[LLMClient] = None):
        super().__init__(meta=PLAN_AGENT_META)
        # 核心：Plan 用强模型（Qwen 14B / Llama 3 8B），预留切换
        self.llm_client = llm_client or LLMClient(model_type=ModelType.QWEN_14B)  # 默认Qwen 14B
        # 固定提示词（结构化输出引导，降低模型依赖）
        self.plan_prompt_template = """
        你是多Agent会诊系统的Plan规划师，负责生成结构化、可执行的异常订单会诊步骤。
        核心要求：
        1. 仅输出 ExecutionPlan 格式的结构化数据，不添加任何多余描述
        2. 步骤按「订单查询→支付核查→风控校验→对账分析→运营建议」的逻辑排序
        3. 每个步骤的 expert_type 必须是 order/payment/risk/operation/reconciliation 中的一种
        4. required_fields 必须是当前步骤执行的最小必要字段
        5. 结合异常详情，生成精准步骤，不冗余、不遗漏

        输入信息：
        session_id: {session_id}
        order_id: {order_id}
        异常详情: {abnormal_detail}
        """

    def execute(self, agent_input: AgentInput) -> Dict[str, Any]:
        """
        调用强模型（Qwen 14B/Llama 3 8B）生成结构化执行计划
        所有输出经过 Pydantic 校验，不依赖模型能力上限
        """
        # 1. 入参已由基类 Pydantic 强校验（兜底，模型不需要管校验）
        params = agent_input.params
        session_id = agent_input.session_id
        order_id = agent_input.order_id
        abnormal_detail = params.get("abnormal_detail")

        # 2. 强校验：必传字段二次兜底（防止模型忽略入参）
        if not abnormal_detail or len(abnormal_detail.strip()) == 0:
            raise ValueError("规划失败：缺少异常详情 abnormal_detail，无法生成步骤")

        # 3. 调用强模型生成计划（预留模型切换，只需改 model_type 即可）
        prompt = self.plan_prompt_template.format(
            session_id=session_id,
            order_id=order_id,
            abnormal_detail=abnormal_detail
        )
        # 模型调用：指定输出格式为 ExecutionPlan，强制结构化
        llm_response = self.llm_client.generate(
            prompt=prompt,
            output_schema=ExecutionPlan  # 关键：让模型输出符合Pydantic结构
        )

        # 4. Pydantic 强校验：无论模型输出多乱，都要校验通过才返回
        # 这里会自动校验所有字段（step_id范围、expert_type合法性等）
        execution_plan = ExecutionPlan(**llm_response["data"])

        # 5. 返回结构化数据（基类自动包装成标准 AgentOutput）
        return execution_plan.model_dump()