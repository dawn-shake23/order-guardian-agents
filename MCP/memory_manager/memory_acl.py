class MemoryACL:
    @staticmethod
    def can_read(expert_type: str) -> bool:
        return expert_type in ["order", "payment", "risk", "reconciliation"]

    @staticmethod
    def can_write(expert_type: str) -> bool:
        return expert_type in ["coordinator", "risk", "reconciliation"]