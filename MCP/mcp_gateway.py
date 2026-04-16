from typing import Dict, Any, Optional
from memory.memory_hub import MemoryHub
from MCP.acl.acl_matrix import ACLMatrix
from MCP.prompt_manager.prompts import PromptManager
from MCP.context_manager.slicer import ContextSlicer
from MCP.memory_manager.memory_acl import MemoryACL
from MCP.tool_guard.tool_acl import ToolACL
from MCP.validator.step_validator import StepValidator

class MCPGateway:
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        self.acl_matrix = ACLMatrix()
        self.prompt_manager = PromptManager()
        self.context_slicer = ContextSlicer()
        self.memory_acl = MemoryACL(memory_hub)
        self.tool_acl = ToolACL()
        self.validator = StepValidator()
    
    def check_agent_permission(self, agent_type: str, action: str) -> bool:
        """
        检查Agent权限
        """
        return self.acl_matrix.check_permission(agent_type, action)
    
    def get_prompt(self, agent_type: str, task_type: str) -> str:
        """
        获取Agent提示词
        """
        return self.prompt_manager.get_prompt(agent_type, task_type)
    
    def slice_context(self, agent_type: str, full_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        上下文切片，只返回Agent有权访问的内容
        """
        return self.context_slicer.slice(agent_type, full_context)
    
    def check_memory_access(self, agent_type: str, memory_key: str, access_type: str) -> bool:
        """
        检查Memory访问权限
        """
        return self.memory_acl.check_access(agent_type, memory_key, access_type)
    
    def check_tool_access(self, agent_type: str, tool_name: str) -> bool:
        """
        检查工具访问权限
        """
        return self.tool_acl.check_access(agent_type, tool_name)
    
    def validate_step(self, step: Dict[str, Any]) -> bool:
        """
        验证步骤是否合法
        """
        return self.validator.validate(step)
    
    def get_memory(self, agent_type: str, memory_key: str) -> Optional[Any]:
        """
        获取Memory内容
        """
        if self.check_memory_access(agent_type, memory_key, "read"):
            return self.memory_hub.struct().get(memory_key)
        return None
    
    def set_memory(self, agent_type: str, memory_key: str, value: Any) -> bool:
        """
        设置Memory内容
        """
        if self.check_memory_access(agent_type, memory_key, "write"):
            self.memory_hub.struct().set(memory_key, value)
            return True
        return False