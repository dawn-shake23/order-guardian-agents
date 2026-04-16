from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from typing import Dict, Any

class PaymentAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub):
        meta = AgentMeta(
            agent_type="payment",
            allowed_tools=["memory_read_write", "vector_search", "struct_search"]
        )
        super().__init__(meta, memory_hub)

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        search_result = self.call_tool(
            "vector_search",
            {"query": "支付掉单处理", "biz_domain": "payment", "top_k": 3}
        )
        return {
            "payment_status": "pending",
            "rule_guide": search_result.data,
            "action": "检查渠道回调"
        }