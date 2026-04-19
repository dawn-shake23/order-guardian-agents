from typing import Dict, Any
from memory.memory_hub import MemoryHub
from tools.tool_registry import tool_registry
from tools.DataCarry.memory_rw import MemoryReadWriteTool
from tools.DataCarry.sandbox_rw import SandboxReadWriteTool
from tools.DataCarry.struct_search import StructSearchTool
from tools.DeepSearch.vector_search import VectorSearchTool
from tools.RuleCheck.acl_check import AgentAclCheckTool

class ToolLifeCycleManager:
    _instance = None
    
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        self.tools_initialized = False
    
    @classmethod
    def global_init(cls, memory_hub: MemoryHub) -> 'ToolLifeCycleManager':
        if cls._instance is None:
            cls._instance = cls(memory_hub)
            cls._instance._initialize_tools()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ToolLifeCycleManager':
        if cls._instance is None:
            raise RuntimeError("ToolLifeCycleManager not initialized")
        return cls._instance
    
    def _initialize_tools(self):
        tool_registry.register_tool("memory_read_write", MemoryReadWriteTool(self.memory_hub))
        tool_registry.register_tool("vector_search", VectorSearchTool(self.memory_hub))
        tool_registry.register_tool("struct_search", StructSearchTool(self.memory_hub))
        tool_registry.register_tool("agent_acl_check", AgentAclCheckTool())
        tool_registry.register_tool("sandbox_read_write", SandboxReadWriteTool())
        self.tools_initialized = True
    
    def get_tool(self, tool_name: str) -> Any:
        return tool_registry.get_tool(tool_name)
    
    def shutdown(self):
        pass
