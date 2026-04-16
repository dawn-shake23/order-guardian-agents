from .base_agent import BaseAgent, AgentMeta
from Memory.memory_hub import MemoryHub
from typing import Dict, Any

class OrderAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub):
        meta = AgentMeta(
            agent_type="order",
            allowed_tools=["memory_read_write", "vector_search", "struct_search"]
        )
        super().__init__(meta, memory_hub)

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        # 1. 读取订单记忆
        mem_result = self.call_tool(
            "memory_read_write",
            {
                "action": "read",
                "session_id": input_context["session_id"]
            }
        )
        # 2. 检索订单域业务规则
        search_result = self.call_tool(
            "vector_search",
            {
                "query": input_context.get("query", "订单异常分析"),
                "biz_domain": "order",
                "top_k": 3
            }
        )
        return {
            "order_info": mem_result.data,
            "rule_ref": search_result.data,
            "suggestion": "订单状态正常，可继续流程"
        }