from typing import Dict, Type, Optional
from Tools.BaseTool import BaseTool
from Memory.memory_hub import MemoryHub

class ToolRegistry:
    _instance = None
    _tool_map: Dict[str, Type[BaseTool]] = {}
    _tool_instances: Dict[str, BaseTool] = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    # 注册工具类
    def register_tool(self, tool_name: str, tool_cls: Type[BaseTool]) -> None:
        self._tool_map[tool_name] = tool_cls

    # 初始化工具实例
    def init_tool_instance(self, tool_name: str, memory_hub: Optional[MemoryHub] = None) -> BaseTool:
        if tool_name not in self._tool_map:
            raise ValueError(f"工具{tool_name}未注册")
        if tool_name in self._tool_instances:
            return self._tool_instances[tool_name]
        # 带依赖初始化
        if memory_hub and tool_name in ["memory_read_write", "vector_search"]:
            instance = self._tool_map[tool_name](memory_hub)
        else:
            instance = self._tool_map[tool_name]()
        instance.initialize()
        self._tool_instances[tool_name] = instance
        return instance

    # 获取工具实例
    def get_tool(self, tool_name: str) -> BaseTool:
        if tool_name not in self._tool_instances:
            raise RuntimeError(f"工具{tool_name}未初始化")
        return self._tool_instances[tool_name]

    # 销毁所有工具
    def destroy_all(self) -> None:
        for instance in self._tool_instances.values():
            instance.destroy()
        self._tool_instances.clear()

# 全局工具注册中心
tool_registry = ToolRegistry()