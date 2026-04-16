from typing import Dict, Any, Optional
from pydantic import BaseModel

class SandboxMeta(BaseModel):
    session_id: str
    step_id: int
    agent_type: str
    created_at: float

class IsolatedAgentSandbox:
    def __init__(self, meta: SandboxMeta):
        self.meta = meta
        self.data: Dict[str, Any] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """
        从沙箱中获取数据
        """
        return self.data.get(key)
    
    def set(self, key: str, value: Any) -> bool:
        """
        向沙箱中设置数据
        """
        self.data[key] = value
        return True
    
    def delete(self, key: str) -> bool:
        """
        从沙箱中删除数据
        """
        if key in self.data:
            del self.data[key]
            return True
        return False
    
    def clear(self):
        """
        清空沙箱数据
        """
        self.data.clear()