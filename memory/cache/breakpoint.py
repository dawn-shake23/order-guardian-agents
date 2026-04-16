from typing import Optional
from store.structured.redis_client import RedisMemoryClient

class BreakpointManager:
    def __init__(self, redis: RedisMemoryClient):
        self.redis = redis

    def save_breakpoint(self, session_id: str, step_id: int, state: dict) -> None:
        key = f"bp:{session_id}:{step_id}"
        self.redis.client.json().set(key, "$", state)
        self.redis.client.expire(key, 1800)

    def load_breakpoint(self, session_id: str, step_id: int) -> Optional[dict]:
        key = f"bp:{session_id}:{step_id}"
        return self.redis.client.json().get(key)