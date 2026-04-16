from .base_worker import BaseAgent, AgentMeta
from memory.memory_hub import MemoryHub
from typing import Dict, Any

class RiskAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub):
        meta = AgentMeta(
            agent_type="risk",
            allowed_tools=["memory_read_write", "vector_search", "agent_acl_check"]
        )
        super().__init__(meta, memory_hub)

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        acl_result = self.call_tool(
            "agent_acl_check",
            {"agent_type": "payment", "check_type": "field", "target": "risk_score"}
        )
        search_result = self.call_tool(
            "vector_search",
            {"query": "交易风险判定", "biz_domain": "risk", "top_k": 3}
        )
        return {
            "risk_level": "low",
            "acl_check": acl_result.data,
            "suggestion": "无异常风险"
        }