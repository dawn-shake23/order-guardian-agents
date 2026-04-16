from .base_agent import BaseAgent, AgentMeta
from Memory.memory_hub import MemoryHub
from typing import Dict, Any

class ReconciliationAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub):
        meta = AgentMeta(
            agent_type="reconciliation",
            allowed_tools=["memory_read_write", "vector_search", "struct_search"]
        )
        super().__init__(meta, memory_hub)

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "reconcile_result": "match",
            "diff_amount": 0,
            "suggestion": "账实一致"
        }