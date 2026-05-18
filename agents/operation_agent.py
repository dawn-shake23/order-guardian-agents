from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter
from typing import Dict, Any, Optional


class OperationAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        meta = AgentMeta(
            agent_type="operation",
            allowed_tools=["sandbox_read_write", "memory_read_write", "vector_search"],
            required_fields=["order_id"]
        )
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.mock_db = mock_db
        self.mock_rag = mock_rag

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        session_id = input_context.get("session_id", "")

        result = self.call_tool("vector_search", {
            "query": "运营SOP订单异常处理", "biz_domain": "operation", "top_k": 2,
        })
        rag_results = result.data.get("search_result", []) if result.success else []

        result = self.call_tool("vector_search", {
            "query": "支付掉单案例", "biz_domain": "payment", "top_k": 2,
        })
        case_results = result.data.get("search_result", []) if result.success else []

        order_data = self.memory_hub.struct_redis.get(f"order_data:{session_id}")
        payment_data = self.memory_hub.struct_redis.get(f"payment_data:{session_id}")
        risk_data = self.memory_hub.struct_redis.get(f"risk_data:{session_id}")

        operation_suggestion = self._generate_operation_suggestion(order_data, payment_data, risk_data)
        needs_manual = self._check_needs_manual(risk_data, payment_data)

        return {
            "operation_suggestion": operation_suggestion,
            "needs_manual_intervention": needs_manual,
            "priority": self._determine_priority(risk_data, payment_data),
            "sop_ref": rag_results,
            "case_ref": case_results,
            "data_source": "rag+memory",
            "action_plan": self._build_action_plan(order_data, payment_data, risk_data)
        }

    def _generate_operation_suggestion(self, order_data, payment_data, risk_data) -> str:
        risk_level = risk_data.get("risk_level", "low") if risk_data else "low"
        payment_status = payment_data.get("status", "unknown") if payment_data else "unknown"

        if risk_level == "high":
            return "高风险订单，需人工审核后处理"
        if payment_status == "timeout":
            return "支付超时，建议查询渠道并补单"
        if payment_status == "failed":
            return "支付失败，建议通知用户重新支付"
        if payment_status == "reversed":
            return "支付退回，建议更新订单并等待重新支付"
        return "正常流转，无需人工介入"

    def _check_needs_manual(self, risk_data, payment_data) -> bool:
        if risk_data and risk_data.get("risk_level") == "high":
            return True
        if payment_data and payment_data.get("status") in ("timeout", "reversed"):
            return True
        return False

    def _determine_priority(self, risk_data, payment_data) -> str:
        if risk_data and risk_data.get("risk_level") == "high":
            return "high"
        if payment_data and payment_data.get("status") in ("timeout", "failed"):
            return "medium"
        return "low"

    def _build_action_plan(self, order_data, payment_data, risk_data) -> list:
        plan = []
        if payment_data and payment_data.get("status") == "timeout":
            plan.append("1. 主动查询支付渠道确认扣款状态")
            plan.append("2. 已扣款则补单更新订单状态")
            plan.append("3. 未扣款则关闭订单通知用户")
        if risk_data and risk_data.get("risk_level") in ("high", "medium"):
            plan.append("4. 提交风控审核")
            plan.append("5. 审核通过后放行")
        if not plan:
            plan.append("1. 常规处理流程")
        return plan

    def _fallback(self, agent_input):
        from .base_worker import AgentOutput
        return AgentOutput(
            success=True,
            data={"operation_suggestion": "降级：常规处理", "priority": "low", "fallback_used": True},
            fallback_used=True
        )
