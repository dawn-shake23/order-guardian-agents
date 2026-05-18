import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
from models.llm_client import LLMClient, ModelType
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter


class IntentUnderstanding(BaseModel):
    raw_query: str
    rewritten_query: str = "订单异常诊断"
    intent_type: str = "order_query"
    constraints: List[str] = Field(default_factory=list)
    sensitive_flags: List[str] = Field(default_factory=list)


class GlobalAnalysis(BaseModel):
    order_state_analysis: str = "待分析"
    risk_prejudgment: str = "待评估"
    abnormal_level: str = "low"
    complexity: str = "low"
    data_dependencies: List[str] = Field(default_factory=list)


class DataRequirement(BaseModel):
    order_data: List[str] = Field(default_factory=lambda: ["order_id", "status", "amount"])
    payment_data: List[str] = Field(default_factory=lambda: ["payment_id", "status", "error_code"])
    risk_data: List[str] = Field(default_factory=lambda: ["risk_level", "score"])
    reconciliation_data: List[str] = Field(default_factory=lambda: ["diff_amount", "status"])


class KnowledgeRetrievalDemand(BaseModel):
    retrieval_queries: List[str] = Field(default_factory=list)
    retrieval_scenes: List[str] = Field(default_factory=list)
    knowledge_type: List[str] = Field(default_factory=lambda: ["rule", "process"])


class PlanStep(BaseModel):
    step_id: int = Field(ge=1)
    expert_type: str
    goal: str
    data_used: List[str] = Field(default_factory=list)
    retrieval_used: bool = True
    validation_criteria: Dict[str, Any] = Field(default_factory=dict)
    expected_output: str = ""
    depends_on: List[int] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    session_id: str
    order_id: str
    intent: IntentUnderstanding
    global_analysis: GlobalAnalysis
    data_requirements: DataRequirement
    knowledge_demand: KnowledgeRetrievalDemand
    steps: List[PlanStep]
    final_goal: str = "完成订单异常诊断"
    success_criteria: Dict[str, Any] = Field(default_factory=dict)


PLAN_AGENT_META = AgentMeta(
    agent_type="plan",
    version="2.0.0",
    timeout_seconds=30,
    required_fields=["order_id", "abnormal_detail"],
    acl_scopes=["plan:create", "plan:rewrite", "plan:analyze"]
)


class PlanAgent(BaseWorkerAgent):
    CACHE_TTL = 10

    def __init__(self, memory_hub: MemoryHub,
                 llm_client: Optional[LLMClient] = None,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        super().__init__(PLAN_AGENT_META, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.llm = llm_client or LLMClient(model_type=ModelType.QWEN_14B)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        abnormal_detail = input_context.get("abnormal_detail", "")

        cached = self._get_cached_plan(order_id)
        if cached:
            return cached

        plan = self._build_plan(
            session_id=input_context.get("session_id", f"sess_{int(time.time())}"),
            order_id=order_id,
            abnormal_detail=abnormal_detail
        )

        self._cache_plan(order_id, plan)
        return plan

    def _get_cached_plan(self, order_id: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(order_id)
        if entry and time.time() - entry["cached_at"] < self.CACHE_TTL:
            return entry["plan"]
        return None

    def _cache_plan(self, order_id: str, plan: Dict[str, Any]):
        self._cache[order_id] = {"plan": plan, "cached_at": time.time()}

    def _build_plan(self, session_id: str, order_id: str, abnormal_detail: str) -> Dict[str, Any]:
        intent = IntentUnderstanding(
            raw_query=abnormal_detail or "订单异常",
            rewritten_query=f"诊断订单{order_id}异常原因并给出解决方案",
            intent_type="order_query",
            constraints=["必须查询订单状态", "必须检查支付状态", "必须评估风险等级"],
            sensitive_flags=[]
        )

        level = "low"
        if "高风险" in abnormal_detail or "风控" in abnormal_detail:
            level = "high"
        elif "超时" in abnormal_detail or "异常" in abnormal_detail:
            level = "medium"

        global_analysis = GlobalAnalysis(
            order_state_analysis=f"订单{order_id}存在异常，需全链路诊断",
            risk_prejudgment=f"预估风险等级：{level}",
            abnormal_level=level,
            complexity="medium" if level != "low" else "low",
            data_dependencies=["订单数据", "支付数据", "风控数据", "对账数据"]
        )

        steps = [
            PlanStep(step_id=1, expert_type="order", goal="查询订单详情与状态",
                     data_used=["order_id", "status", "amount"], retrieval_used=True,
                     validation_criteria={"must_have": ["order_id", "status"]},
                     expected_output="订单详情+状态", depends_on=[]),
            PlanStep(step_id=2, expert_type="payment", goal="查询支付状态与渠道信息",
                     data_used=["payment_id", "status", "error_code"], retrieval_used=True,
                     validation_criteria={"must_have": ["payment_status"]},
                     expected_output="支付状态+错误码", depends_on=[1]),
            PlanStep(step_id=3, expert_type="risk", goal="评估风险等级与命中规则",
                     data_used=["risk_level", "score", "hit_rules"], retrieval_used=True,
                     validation_criteria={"must_have": ["risk_level"]},
                     expected_output="风险等级+命中规则", depends_on=[1]),
            PlanStep(step_id=4, expert_type="reconciliation", goal="对账核查金额与状态一致性",
                     data_used=["diff_amount", "diff_type", "status"], retrieval_used=True,
                     validation_criteria={"must_have": ["reconcile_result"]},
                     expected_output="对账结果+差异详情", depends_on=[1, 2]),
            PlanStep(step_id=5, expert_type="operation", goal="综合诊断并给出运营建议",
                     data_used=["suggestion", "priority", "action_plan"], retrieval_used=True,
                     validation_criteria={"must_have": ["operation_suggestion"]},
                     expected_output="运营建议+优先级+行动方案", depends_on=[1, 2, 3, 4]),
        ]

        plan = ExecutionPlan(
            session_id=session_id,
            order_id=order_id,
            intent=intent,
            global_analysis=global_analysis,
            data_requirements=DataRequirement(),
            knowledge_demand=KnowledgeRetrievalDemand(
                retrieval_queries=["订单异常处理规则", "支付超时处理", "风控策略"],
                retrieval_scenes=["步骤1-5均需向量检索"],
                knowledge_type=["rule", "process", "case"]
            ),
            steps=steps,
            final_goal=f"完成订单{order_id}异常诊断并给出解决方案",
            success_criteria={"all_steps_completed": True, "root_cause_identified": True}
        )

        return plan.model_dump()
