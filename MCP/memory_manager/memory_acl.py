class MemoryACL:
    """
    MCP 负责 Memory 访问策略，不操作存储
    Memory 层自己负责存储
    """
    @staticmethod
    def can_read_global(agent_type: str) -> bool:
        return agent_type in [
            "coordinator", "order", "payment", "risk", "reconciliation"
        ]

    @staticmethod
    def can_write_global(agent_type: str) -> bool:
        return agent_type in ["coordinator", "plan", "risk", "reconciliation"]

    @staticmethod
    def can_access_step_memory(agent_type: str) -> bool:
        return agent_type != "operation"