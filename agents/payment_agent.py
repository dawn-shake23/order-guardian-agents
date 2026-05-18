from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter
from typing import Dict, Any, Optional


class PaymentAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        meta = AgentMeta(
            agent_type="payment",
            allowed_tools=["payment_query", "memory_read_write", "vector_search", "struct_search"],
            required_fields=["order_id"]
        )
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.mock_db = mock_db
        self.mock_rag = mock_rag

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        session_id = input_context.get("session_id", "")

        payments = self.mock_db.query("payments", {"order_id": order_id})
        if not payments:
            payments = [{"payment_id": "N/A", "status": "unknown", "error_code": "E2005", "msg": "无支付记录"}]

        primary_payment = payments[0] if payments else {}
        error_code = primary_payment.get("error_code", "")

        rag_results = []
        if error_code:
            result = self.call_tool("vector_search", {
                "query": f"{error_code}处理规则", "biz_domain": "payment", "top_k": 2,
            })
            rag_results = result.data.get("search_result", []) if result.success else []
        if not rag_results:
            result = self.call_tool("vector_search", {
                "query": "支付异常处理", "biz_domain": "payment", "top_k": 2,
            })
            rag_results = result.data.get("search_result", []) if result.success else []

        self.memory_hub.struct_redis.set(
            f"payment_data:{session_id}", primary_payment, expire=3600
        )

        return {
            "payment_status": primary_payment.get("status", "unknown"),
            "payment_info": primary_payment,
            "all_payments": payments,
            "error_code": error_code,
            "rule_guide": rag_results,
            "data_source": "mock_db",
            "action": self._determine_action(primary_payment)
        }

    def _determine_action(self, payment: Dict) -> str:
        status = payment.get("status", "")
        if status == "timeout":
            return "查询渠道确认支付状态，必要时补单"
        elif status == "failed":
            return "标记支付失败，通知用户更换支付方式"
        elif status == "reversed":
            return "确认退回原因，更新订单状态"
        elif status == "success":
            return "支付成功，确认回调"
        return "需进一步核查支付状态"

    def _fallback(self, agent_input):
        from .base_worker import AgentOutput
        return AgentOutput(
            success=True,
            data={"payment_status": "unknown", "action": "降级：无法查询支付详情", "fallback_used": True},
            fallback_used=True
        )
