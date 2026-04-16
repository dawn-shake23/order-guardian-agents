from MCP.acl.acl_matrix import AGENT_ACL

class ContextSlicer:
    @staticmethod
    def slice(expert_type: str, full_context: dict) -> dict:
        allowed = AGENT_ACL[expert_type]["fields"]
        return {k: v for k, v in full_context.items() if k in allowed}