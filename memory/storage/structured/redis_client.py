import redis
from typing import Optional, Dict, Any
from datetime import datetime
from models.struct_memory import SessionMemory, StepMemory

class RedisMemoryClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True, charset="utf-8")

    # 存储会话记忆（带TTL）
    def set_session_memory(self, memory: SessionMemory) -> None:
        key = f"session:{memory.session_id}"
        self.client.hset(key, mapping=memory.model_dump())
        self.client.expire(key, memory.ttl_seconds)

    # 获取会话记忆
    def get_session_memory(self, session_id: str) -> Optional[Dict[str, Any]]:
        key = f"session:{session_id}"
        return self.client.hgetall(key)

    # 存储断点数据
    def set_breakpoint(self, step_memory: StepMemory) -> None:
        key = f"breakpoint:{step_memory.session_id}:{step_memory.step_id}"
        self.client.json().set(key, "$", step_memory.model_dump())
        self.client.expire(key, step_memory.ttl_seconds)