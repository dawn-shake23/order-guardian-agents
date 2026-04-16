# MCP/memory_manager/mcp_memory_guard.py
from Memory.memory_hub import MemoryHub
from Memory.core.isolation import MemoryIsolation

class MCPMemoryGuard:
    def __init__(self, memory_hub: MemoryHub):
        self.hub = memory_hub

    def get_agent_sandbox(self, agent_type: str, session_id: str, step_id: int):
        sandbox = self.hub.create_sandbox(session_id, step_id, agent_type)
        if not MemoryIsolation.check_agent_access(agent_type, ["order", "payment", "risk", "reconciliation"]):
            raise PermissionError("agent not allowed to access sandbox")
        return sandbox

    def vector_search(self, agent_type: str, query: str, domain: str):
        # MCP 管控检索权限
        return self.hub.vector().search_by_domain(query, domain)