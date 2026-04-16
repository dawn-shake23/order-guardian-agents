from .base_agent import BaseAgent, AgentMeta
from Memory.memory_hub import MemoryHub
from typing import Dict, Any

class OperationAgent(BaseAgent):
    def __init__(self, memory_hub: MemoryHub):
        meta = AgentMeta(
            agent_type="operation",
            allowed_tools=["sandbox_read_write"]
        )
        super().__init__(meta, memory_hub)

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "operation_suggestion": "正常流转，无需人工介入",
            "priority": "low"
        }