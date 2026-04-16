from MCP.acl.acl_matrix import AGENT_ACL

class ToolACL:
    @staticmethod
    def allowed_tools(expert_type: str) -> list:
        return AGENT_ACL[expert_type]["tools"]