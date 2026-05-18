import json
import time
import os
import threading
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepState(BaseModel):
    step_id: int
    expert_type: str
    goal: str
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None


class SessionState(BaseModel):
    session_id: str
    order_id: str
    steps: List[StepState] = Field(default_factory=list)
    current_step: int = 0
    plan_success: Optional[bool] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    checkpoint_at: Optional[float] = None


class StatePersistence:
    def __init__(self, persist_dir: str = "./state_checkpoints"):
        self._states: Dict[str, SessionState] = {}
        self._persist_dir = persist_dir
        self._lock = threading.Lock()
        os.makedirs(persist_dir, exist_ok=True)

    def save(self, state: SessionState):
        state.updated_at = time.time()
        with self._lock:
            self._states[state.session_id] = state
        self._persist_to_file(state)

    def load(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            if session_id in self._states:
                return self._states[session_id]
        return self._load_from_file(session_id)

    def checkpoint(self, state: SessionState):
        state.checkpoint_at = time.time()
        self.save(state)

    def list_sessions(self) -> List[str]:
        return list(self._states.keys())

    def _persist_to_file(self, state: SessionState):
        try:
            path = os.path.join(self._persist_dir, f"{state.session_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_from_file(self, session_id: str) -> Optional[SessionState]:
        try:
            path = os.path.join(self._persist_dir, f"{session_id}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionState(**data)
        except Exception:
            pass
        return None


class CheckpointManager:
    def __init__(self, persistence: StatePersistence):
        self.persistence = persistence

    def create_checkpoint(self, state: SessionState) -> str:
        self.persistence.checkpoint(state)
        return state.session_id

    def resume(self, session_id: str) -> Optional[SessionState]:
        state = self.persistence.load(session_id)
        if state and state.plan_success is None:
            return state
        return None

    def get_next_step(self, state: SessionState) -> Optional[StepState]:
        for step in state.steps:
            if step.status in (StepStatus.PENDING, StepStatus.FAILED):
                return step
        return None
