from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
from .plan_agent import ExecutionPlan
from Model.llm_client import LLMClient, ModelType

# -----------------------------------------------------------------------------
# 最终会诊报告（强校验，全局唯一出口）
# -----------------------------------------------------------------------------
class FinalConsultReport(BaseModel):
    session_id: str
    order_id: str
    plan_success: bool
    abnormal_root_cause: str
    solution: str
    risk_level: str
    expert_steps: List[Dict[str, Any]]
    final_summary: str

# -----------------------------------------------------------------------------
# Coordinator 元数据 & 权限定义
# -----------------------------------------------------------------------------
COORDINATOR_META = AgentMeta(
    agent_type="coordinator",
    version="1.0.0",
    timeout_seconds=45,
    required_fields=["execution_plan"],
    acl_scopes=["plan:read", "step:schedule", "result:aggregate", "decision:make"]
)

# -----------------------------------------------------------------------------
# Coordinator 核心：只做调度、决策、汇总
# 权限/Prompt/隔离/工具 全部交给 MCP
# -----------------------------------------------------------------------------
class Coordinator(BaseWorkerAgent):
    def __init__(self, llm_client: Optional[LLMClient] = None):
        super().__init__(COORDINATOR_META)
        self.llm = llm_client or LLMClient(model_type=ModelType.QWEN_14B)

    def execute(self, agent_input: AgentInput) -> Dict[str, Any]:
        # 1. 解析并强校验 Plan
        plan = ExecutionPlan(**agent_input.params["execution_plan"])

        # 2. 构建全局上下文
        global_context = {
            "session_id": agent_input.session_id,
            "order_id": agent_input.order_id,
            "intent": plan.intent.model_dump(),
            "global_analysis": plan.global_analysis.model_dump()
        }

        # 3. 按步骤分发（MCP 负责权限、Prompt、上下文、工具）
        step_results = []
        for step in plan.steps:
            step_results.append({
                "step_id": step.step_id,
                "expert_type": step.expert_type,
                "goal": step.goal,
                "status": "pending"
            })

        # 4. 强模型生成最终决策
        final_report = self._make_final_decision(global_context, step_results, plan)

        return final_report.model_dump()

    def _make_final_decision(self, context: Dict, steps: List[Dict], plan: ExecutionPlan) -> FinalConsultReport:
        prompt = f"""
会话：{context['session_id']}
订单：{context['order_id']}
意图：{plan.intent.rewritten_query}
全局分析：{plan.global_analysis.order_state_analysis}
专家步骤结果：{steps}

请输出根因、方案、风险等级、最终总结。
"""
        raw = self.llm.generate(prompt, output_schema=FinalConsultReport)
        return FinalConsultReport(**raw["data"])