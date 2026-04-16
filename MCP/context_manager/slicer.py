from MCP.acl.acl_matrix import AGENT_ACL

class ContextSlicer:
    @staticmethod
    def slice_by_acl(agent_type: str, global_ctx: dict, allowed_fields: list) -> dict:
        return {k: v for k, v in global_ctx.items() if k in allowed_fields}