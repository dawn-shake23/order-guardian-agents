from typing import Dict, Any, Optional
from tools.BaseTool.base_tool import BaseTool, ToolResult

class SandboxReadWriteTool(BaseTool):
    def __init__(self):
        super().__init__()

    def _run(self, params: Dict[str, Any], sandbox: Optional[Any] = None) -> Dict[str, Any]:
        action = params.get("action", "read")
        key = params.get("key", "")
        if action == "read":
            return {"operate_result": True, "data": {key: "模拟沙盒数据"}}
        elif action == "write":
            return {"operate_result": True}
        return {"operate_result": False}
