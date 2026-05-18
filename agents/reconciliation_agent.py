from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter
from typing import Dict, Any, Optional


class ReconciliationAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        meta = AgentMeta(
            agent_type="reconciliation",
            allowed_tools=["reconciliation_query", "memory_read_write", "vector_search", "struct_search"],
            required_fields=["order_id"]
        )
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.mock_db = mock_db
        self.mock_rag = mock_rag

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        session_id = input_context.get("session_id", "")

        recon_data = self.mock_db.get("reconciliations", f"RECON_{order_id}")
        if not recon_data:
            recon_data = {"order_id": order_id, "diff_amount": 0, "diff_type": "none",
                          "status": "no_data", "order_status": "unknown", "payment_status": "unknown"}

        rag_results = self.mock_rag.search(
            query="对账不一致处理流程", biz_domain="reconciliation", top_k=2, doc_type="process"
        )

        diff_type = recon_data.get("diff_type", "none")
        if diff_type != "none":
            rule_results = self.mock_rag.search(
                query="E3004对账差异处理", biz_domain="reconciliation", top_k=2, doc_type="rule"
            )
            rag_results.extend(rule_results)

        self.memory_hub.struct_redis.set(
            f"recon_data:{session_id}", recon_data, expire=3600
        )

        return {
            "reconcile_result": recon_data.get("status", "unknown"),
            "diff_amount": recon_data.get("diff_amount", 0),
            "diff_type": diff_type,
            "recon_info": recon_data,
            "rule_ref": rag_results,
            "data_source": "mock_db",
            "suggestion": self._generate_suggestion(recon_data)
        }

    def _generate_suggestion(self, recon_data: Dict) -> str:
        status = recon_data.get("status", "")
        if status == "match":
            return "账实一致，无需处理"
        elif status == "mismatch_status":
            return "状态不一致，需核实支付状态并修正订单"
        elif "diff" in status:
            return "金额差异，需人工核实"
        return "对账结果需确认"

    def _fallback(self, agent_input):
        from .base_worker import AgentOutput
        return AgentOutput(
            success=True,
            data={"reconcile_result": "unknown", "suggestion": "降级：无法完成对账", "fallback_used": True},
            fallback_used=True
        )
