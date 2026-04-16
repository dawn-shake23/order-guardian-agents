from typing import Optional, Any
import json

class RedisMemoryClient:
    def __init__(self):
        # 实际项目中这里应该初始化真实的Redis客户端
        self.memory = {}
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取内存中的值
        """
        return self.memory.get(key)
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        设置内存中的值
        """
        self.memory[key] = value
        return True
    
    def delete(self, key: str) -> bool:
        """
        删除内存中的值
        """
        if key in self.memory:
            del self.memory[key]
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """
        检查key是否存在
        """
        return key in self.memory
    
    def expire(self, key: str, seconds: int) -> bool:
        """
        设置key的过期时间
        """
        # 实际项目中需要实现过期时间管理
        return True