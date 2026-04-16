class MemoryIsolation:
    @staticmethod
    def check_agent_access(agent_type: str, allowed_agent_types: list[str]) -> bool:
        return agent_type in allowed_agent_types

    @staticmethod
    def filter_fields_by_acl(data: dict, allowed_fields: list[str]) -> dict:
        return {k: v for k, v in data.items() if k in allowed_fields}