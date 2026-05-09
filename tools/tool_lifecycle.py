from typing import Dict, Any
from Memory.memory_hub import MemoryHub
from .tool_registry import tool_registry

class ToolLifeCycleManager:
    _instance = None
    
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        self.tools_initialized = False
    
    @classmethod
    def global_init(cls, memory_hub: MemoryHub) -> 'ToolLifeCycleManager':
        """
        全局初始化工具生命周期管理器
        """
        if cls._instance is None:
            cls._instance = cls(memory_hub)
            cls._instance._initialize_tools()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ToolLifeCycleManager':
        """
        获取工具生命周期管理器实例
        """
        if cls._instance is None:
            raise RuntimeError("ToolLifeCycleManager not initialized")
        return cls._instance
    
    def _initialize_tools(self):
        """
        初始化所有工具
        """
        # 这里应该注册所有工具
        # 示例：tool_registry.register_tool("tool_name", ToolClass())
        self.tools_initialized = True
    
    def get_tool(self, tool_name: str) -> Any:
        """
        获取工具实例
        """
        return tool_registry.get_tool(tool_name)
    
    def shutdown(self):
        """
        关闭所有工具
        """
        # 这里应该清理所有工具资源
        pass