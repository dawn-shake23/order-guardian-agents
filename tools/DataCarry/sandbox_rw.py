from typing import Dict, Any, Optional
from Tools.BaseTool import BaseTool, ToolMeta
from Memory.sandbox.isolation_sandbox import IsolatedAgentSandbox

class SandboxReadWriteTool(BaseTool):
    def __init__(self):
        meta = ToolMeta(
            tool_name="sandbox_read_write",
            tool_description="Agent沙盒隔离数据读写，严格权限隔离",
            input_schema={
                "action": "read/write",
                "key": "str",
                "value": "Optional[Any]"
            },
            output_schema={
                "data": "Optional[Any]",
                "operate_result": "bool"
            },
            allowed_agent_types=["order", "payment", "risk", "reconciliation", "operation"],
            need_sandbox=True
        )
        super().__init__(meta)

    def _on_initialize(self) -> None:
        pass

    def _pre_check_logic(self, agent_type: str, params: Dict[str, Any]) -> bool:
        return "action" in params and "key" in params

    def _execute_logic(self, agent_type: str, params: Dict[str, Any], sandbox: IsolatedAgentSandbox) -> Dict[str, Any]:
        action = params["action"]
        key = params["key"]
        if action == "read":
            data = sandbox.get_data(key, agent_type)
            return {"operate_result": True, "data": data}
        elif action == "write":
            sandbox.set_data(key, params["value"], agent_type)
            return {"operate_result": True}
        return {"operate_result": False}