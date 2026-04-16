from typing import Dict, Any

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Any] = {}
    
    def register_tool(self, tool_name: str, tool_instance: Any):
        """
        注册工具
        """
        self.tools[tool_name] = tool_instance
    
    def get_tool(self, tool_name: str) -> Any:
        """
        获取工具实例
        """
        return self.tools.get(tool_name)
    
    def list_tools(self) -> list:
        """
        列出所有注册的工具
        """
        return list(self.tools.keys())

# 全局工具注册表实例
tool_registry = ToolRegistry()