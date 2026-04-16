from typing import Dict, Any

class ContextMemory:
    def __init__(self):
        self.global_context: Dict[str, Any] = {}
        self.sliced_context: Dict[str, Dict[str, Any]] = {}

    def set_global(self, ctx: Dict[str, Any]):
        self.global_context = ctx

    def get_global(self):
        return self.global_context.copy()

    def set_sliced(self, agent_type: str, ctx: Dict[str, Any]):
        self.sliced_context[agent_type] = ctx

    def get_sliced(self, agent_type: str):
        return self.sliced_context.get(agent_type, {})