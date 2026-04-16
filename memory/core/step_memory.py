from typing import Dict, Any
from Memory.base_memory import BaseMemory

class StepMemory(BaseMemory):
    def __init__(self):
        self._step_data: Dict[int, Dict[str, Any]] = {}

    def get(self, step_id: int) -> Dict[str, Any]:
        return self._step_data.get(step_id, {})

    def set(self, step_id: int, data: Dict[str, Any]) -> None:
        self._step_data[step_id] = data

    def delete(self, step_id: int) -> None:
        self._step_data.pop(step_id, None)

    def clear(self) -> None:
        self._step_data.clear()