from typing import Optional, Dict, Any
from Memory.storage.structured.redis_client import RedisMemoryClient

class BreakpointManager:
    def __init__(self, redis_client: RedisMemoryClient):
        self.redis = redis_client
        self.prefix = "breakpoint:"
    
    def set_breakpoint(self, session_id: str, step_id: int, data: Dict[str, Any]) -> bool:
        """
        设置断点
        """
        key = f"{self.prefix}{session_id}:{step_id}"
        return self.redis.set(key, data)
    
    def get_breakpoint(self, session_id: str, step_id: int) -> Optional[Dict[str, Any]]:
        """
        获取断点
        """
        key = f"{self.prefix}{session_id}:{step_id}"
        return self.redis.get(key)
    
    def delete_breakpoint(self, session_id: str, step_id: int) -> bool:
        """
        删除断点
        """
        key = f"{self.prefix}{session_id}:{step_id}"
        return self.redis.delete(key)
    
    def clear_breakpoints(self, session_id: str) -> bool:
        """
        清除会话的所有断点
        """
        # 实际项目中需要实现批量删除
        return True