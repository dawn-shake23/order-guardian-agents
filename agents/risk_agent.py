from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter
from typing import Dict, Any, Optional


class RiskAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        meta = AgentMeta(
            agent_type="risk",
            allowed_tools=["risk_query", "memory_read_write", "vector_search", "agent_acl_check"],
            required_fields=["order_id"]
        )
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.mock_db = mock_db
        self.mock_rag = mock_rag

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        session_id = input_context.get("session_id", "")

        risk_data = self.mock_db.get("risks", f"RISK_{order_id}")
        if not risk_data:
            risk_data = {"order_id": order_id, "risk_level": "low", "score": 10,
                         "hit_rules": [], "reason": "无风控记录，默认低风险"}

        rag_results = self.mock_rag.search(
            query="风控策略规则", biz_domain="risk", top_k=2, doc_type="policy"
        )

        if risk_data.get("risk_level") == "high":
            rule_results = self.mock_rag.search(
                query="E3001风控拦截处理", biz_domain="risk", top_k=2, doc_type="rule"
            )
            rag_results.extend(rule_results)

        self.memory_hub.struct_redis.set(
            f"risk_data:{session_id}", risk_data, expire=3600
        )

        return {
            "risk_level": risk_data.get("risk_level", "low"),
            "risk_score": risk_data.get("score", 0),
            "hit_rules": risk_data.get("hit_rules", []),
            "risk_info": risk_data,
            "rule_ref": rag_results,
            "data_source": "mock_db",
            "suggestion": self._generate_suggestion(risk_data)
        }

    def _generate_suggestion(self, risk_data: Dict) -> str:
        level = risk_data.get("risk_level", "low")
        if level == "high":
            return "高风险，建议人工审核并冻结订单"
        elif level == "medium":
            return "中风险，建议加强验证后放行"
        return "低风险，正常流转"

    def _fallback(self, agent_input):
        from .base_worker import AgentOutput
        return AgentOutput(
            success=True,
            data={"risk_level": "low", "suggestion": "降级：默认低风险", "fallback_used": True},
            fallback_used=True
        )
