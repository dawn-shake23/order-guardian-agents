from typing import Dict, Any, Optional
from tools.BaseTool.base_tool import BaseTool, ToolResult

AGENT_ACL = {
    "coordinator": {"tools": ["memory_read_write", "vector_search", "struct_search", "agent_acl_check"], "fields": ["*"]},
    "order": {"tools": ["memory_read_write", "vector_search", "struct_search"], "fields": ["order_id", "status", "amount"]},
    "payment": {"tools": ["memory_read_write", "vector_search", "struct_search"], "fields": ["payment_id", "status", "amount"]},
    "risk": {"tools": ["memory_read_write", "vector_search", "agent_acl_check"], "fields": ["risk_score", "risk_level"]},
    "reconciliation": {"tools": ["memory_read_write", "vector_search", "struct_search"], "fields": ["order_amount", "payment_amount"]},
    "operation": {"tools": ["sandbox_read_write"], "fields": ["suggestion", "priority"]},
}

class AgentAclCheckTool(BaseTool):
    def __init__(self):
        super().__init__()

    def _run(self, params: Dict[str, Any], sandbox: Optional[Any] = None) -> Dict[str, Any]:
        target_agent = params.get("agent_type", "")
        check_type = params.get("check_type", "tool")
        target = params.get("target", "")
        if target_agent not in AGENT_ACL:
            return {"has_permission": False}
        if check_type == "tool":
            return {"has_permission": target in AGENT_ACL[target_agent]["tools"]}
        elif check_type == "field":
            return {"has_permission": target in AGENT_ACL[target_agent]["fields"]}
        return {"has_permission": False}
