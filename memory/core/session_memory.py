from typing import Dict, Any
from Memory.base_memory import BaseMemory

class SessionMemory(BaseMemory):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._memory: Dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._memory.get(key)

    def set(self, key: str, value: Any) -> None:
        self._memory[key] = value

    def delete(self, key: str) -> None:
        self._memory.pop(key, None)

    def clear(self) -> None:
        self._memory.clear()

    def dump(self) -> dict:
        return self._memory.copy()