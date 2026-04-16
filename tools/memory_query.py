from typing import Dict, Any
from tools.BaseTool.base_tool import BaseTool, ToolResult
from memory.memory_hub import MemoryHub

class MemoryQueryTool(BaseTool):
    def __init__(self, memory_hub: MemoryHub):
        super().__init__()
        self.memory_hub = memory_hub
    
    def _run(self, params: Dict[str, Any], sandbox: Any = None) -> Dict[str, Any]:
        """
        执行内存查询
        """
        key = params.get("key")
        if not key:
            raise ValueError("Missing key parameter")
        
        value = self.memory_hub.struct().get(key)
        return {"key": key, "value": value}