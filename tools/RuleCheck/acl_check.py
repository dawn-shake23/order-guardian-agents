from typing import Dict, Any, Optional
from Tools.BaseTool import BaseTool, ToolMeta
from MCP.acl.acl_matrix import AGENT_ACL

class AgentAclCheckTool(BaseTool):
    def __init__(self):
        meta = ToolMeta(
            tool_name="agent_acl_check",
            tool_description="Agent权限校验，校验工具/字段/操作访问权限",
            input_schema={
                "agent_type": "str",
                "check_type": "tool/field",
                "target": "str"
            },
            output_schema={
                "has_permission": "bool"
            },
            allowed_agent_types=["coordinator", "mcp"],
            need_sandbox=False
        )
        super().__init__(meta)

    def _on_initialize(self) -> None:
        pass

    def _pre_check_logic(self, agent_type: str, params: Dict[str, Any]) -> bool:
        return all(k in params for k in ["agent_type", "check_type", "target"])

    def _execute_logic(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any]) -> Dict[str, Any]:
        target_agent = params["agent_type"]
        check_type = params["check_type"]
        target = params["target"]
        if target_agent not in AGENT_ACL:
            return {"has_permission": False}
        if check_type == "tool":
            return {"has_permission": target in AGENT_ACL[target_agent]["tools"]}
        elif check_type == "field":
            return {"has_permission": target in AGENT_ACL[target_agent]["fields"]}
        return {"has_permission": False}