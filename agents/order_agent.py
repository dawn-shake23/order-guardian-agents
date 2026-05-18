from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics
from infrastructure.resilience import CircuitBreaker, RateLimiter
from typing import Dict, Any, Optional


class OrderAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        meta = AgentMeta(
            agent_type="order",
            allowed_tools=["order_query", "memory_read_write", "vector_search", "struct_search"],
            required_fields=["order_id"]
        )
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
        self.mock_db = mock_db
        self.mock_rag = mock_rag

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_context.get("order_id", "")
        session_id = input_context.get("session_id", "")

        order_data = self.mock_db.get("orders", order_id)
        if not order_data:
            order_data = {"order_id": order_id, "status": "unknown", "amount": 0,
                          "error": "订单不存在", "error_code": "E1001"}

        result = self.call_tool("vector_search", {
            "query": "订单异常处理规则", "biz_domain": "order", "top_k": 2,
        })
        rag_results = result.data.get("search_result", []) if result.success else []

        self.memory_hub.struct_redis.set(
            f"order_data:{session_id}", order_data, expire=3600
        )

        return {
            "order_info": order_data,
            "rule_ref": rag_results,
            "data_source": "mock_db",
            "suggestion": self._generate_suggestion(order_data)
        }

    def _generate_suggestion(self, order_data: Dict) -> str:
        status = order_data.get("status", "")
        if status == "pending_payment":
            return "订单待支付，需核查支付状态"
        elif status == "timeout":
            return "订单超时，建议关闭或重新支付"
        elif status == "paid":
            return "订单已支付，状态正常"
        return "订单状态需进一步确认"

    def _fallback(self, agent_input) -> Optional[Dict]:
        return type('AgentOutput', (), {
            'success': True, 'data': {
                'order_info': {'order_id': agent_input.order_id, 'status': 'unknown'},
                'suggestion': '降级：无法查询订单详情', 'fallback_used': True
            }, 'error': None, 'error_code': None, 'duration_ms': 0,
            'retried': False, 'fallback_used': True
        })()
