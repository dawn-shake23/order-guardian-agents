from typing import Dict, Set
from memory.memory_hub import MemoryHub

class MemoryACL:
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        # 内存访问控制：agent_type -> (memory_key_pattern, access_type)
        self.memory_access: Dict[str, Set[tuple]] = {
            "order": {
                ("order:*", "read"),
                ("order:*", "write")
            },
            "payment": {
                ("payment:*", "read"),
                ("payment:*", "write")
            },
            "risk": {
                ("order:*", "read"),
                ("payment:*", "read"),
                ("risk:*", "read"),
                ("risk:*", "write")
            },
            "reconciliation": {
                ("order:*", "read"),
                ("payment:*", "read"),
                ("reconciliation:*", "read"),
                ("reconciliation:*", "write")
            },
            "operation": {
                ("order:*", "read"),
                ("payment:*", "read"),
                ("risk:*", "read"),
                ("reconciliation:*", "read"),
                ("operation:*", "read"),
                ("operation:*", "write")
            }
        }
    
    def check_access(self, agent_type: str, memory_key: str, access_type: str) -> bool:
        """
        检查Agent是否有权限访问指定的Memory
        """
        agent_access = self.memory_access.get(agent_type, set())
        
        for pattern, allowed_access in agent_access:
            if allowed_access == access_type and self._match_pattern(memory_key, pattern):
                return True
        
        return False
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """
        检查key是否匹配pattern
        """
        # 简单的通配符匹配
        import fnmatch
        return fnmatch.fnmatch(key, pattern)