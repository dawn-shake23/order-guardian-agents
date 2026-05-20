"""
Harness orchestration framework with full lifecycle management,
priority scheduling, resource control, and fallback strategies.
"""
import time
import threading
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from queue import PriorityQueue
from concurrent.futures import ThreadPoolExecutor, Future

from core.logger import get_logger


class AgentLifecycle(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    IDLE = "idle"
    RUNNING = "running"
    DEGRADING = "degrading"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    DESTROYED = "destroyed"


class TaskPriority(int, Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


@dataclass(order=True)
class ScheduledTask:
    priority: int
    task_id: str = field(compare=False)
    agent_type: str = field(compare=False)
    step_id: int = field(compare=False)
    execute_fn: Any = field(compare=False, repr=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: Dict = field(compare=False, default_factory=dict)
    created_at: float = field(compare=False, default_factory=time.time)
    timeout_seconds: int = field(compare=False, default=30)
    max_retries: int = field(compare=False, default=1)
    depends_on: List[str] = field(compare=False, default_factory=list)


class AgentLifecycleManager:
    """Track and manage agent lifecycle states."""

    def __init__(self):
        self._states: Dict[str, AgentLifecycle] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.logger = get_logger("harness.lifecycle")

    def register(self, agent_type: str):
        with self._lock:
            self._states[agent_type] = AgentLifecycle.UNINITIALIZED
            self._history[agent_type] = []

    def transition(self, agent_type: str, new_state: AgentLifecycle, metadata: Optional[Dict] = None):
        with self._lock:
            old = self._states.get(agent_type, AgentLifecycle.UNINITIALIZED)
            self._states[agent_type] = new_state
            record = {"from": old.value, "to": new_state.value, "ts": time.time(), "meta": metadata or {}}
            self._history[agent_type].append(record)
            self.logger.info("lifecycle_transition", extra={
                "agent": agent_type, "from": old.value, "to": new_state.value,
            })

    def get_state(self, agent_type: str) -> AgentLifecycle:
        return self._states.get(agent_type, AgentLifecycle.UNINITIALIZED)

    def get_history(self, agent_type: str) -> List[Dict[str, Any]]:
        return self._history.get(agent_type, [])

    def is_available(self, agent_type: str) -> bool:
        state = self.get_state(agent_type)
        return state in (AgentLifecycle.IDLE, AgentLifecycle.COMPLETED)


class ResourceController:
    """Control concurrent agent execution and resource allocation."""

    def __init__(self, max_concurrent: int = 5, max_per_agent_type: int = 3):
        self.max_concurrent = max_concurrent
        self.max_per_type = max_per_agent_type
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._type_counters: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.logger = get_logger("harness.resource")

    def acquire(self, agent_type: str, timeout: float = 30.0) -> bool:
        with self._lock:
            current = self._type_counters.get(agent_type, 0)
            if current >= self.max_per_type:
                self.logger.warning("resource_type_limit", extra={"agent": agent_type, "current": current})
                return False
        acquired = self._semaphore.acquire(timeout=timeout)
        if acquired:
            with self._lock:
                self._type_counters[agent_type] = self._type_counters.get(agent_type, 0) + 1
        return acquired

    def release(self, agent_type: str):
        self._semaphore.release()
        with self._lock:
            current = self._type_counters.get(agent_type, 0)
            if current > 0:
                self._type_counters[agent_type] = current - 1

    def get_status(self) -> Dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "active": sum(self._type_counters.values()),
            "by_type": dict(self._type_counters),
        }


class FallbackStrategy:
    """Define agent degradation and fallback strategies."""

    DEGRADE_MAP: Dict[str, str] = {
        "payment": "order",
        "risk": "payment",
        "reconciliation": "order",
        "operation": "reconciliation",
    }

    FALLBACK_DATA: Dict[str, Dict[str, Any]] = {
        "order": {"status": "unknown", "suggestion": "Fallback: unable to query order", "fallback_used": True},
        "payment": {"payment_status": "unknown", "action": "Fallback: unable to verify payment", "fallback_used": True},
        "risk": {"risk_level": "low", "suggestion": "Fallback: default low risk", "fallback_used": True},
        "reconciliation": {"reconcile_result": "unknown", "suggestion": "Fallback: unable to reconcile", "fallback_used": True},
        "operation": {"operation_suggestion": "Fallback: routine processing", "priority": "low", "fallback_used": True},
    }

    @classmethod
    def get_degraded_agent(cls, agent_type: str) -> Optional[str]:
        return cls.DEGRADE_MAP.get(agent_type)

    @classmethod
    def get_fallback_data(cls, agent_type: str) -> Dict[str, Any]:
        return cls.FALLBACK_DATA.get(agent_type, {})


class HarnessOrchestrator:
    """
    Central orchestration engine.
    Manages full agent lifecycle, priority scheduling, parallel/serial execution,
    resource isolation, and failure recovery.
    """

    def __init__(self, max_workers: int = 5, enable_parallel: bool = True):
        self.lifecycle = AgentLifecycleManager()
        self.resources = ResourceController(max_concurrent=max_workers)
        self.fallback = FallbackStrategy()
        self.enable_parallel = enable_parallel
        self._executor: Optional[ThreadPoolExecutor] = None
        self._pending_tasks: PriorityQueue = PriorityQueue()
        self._task_results: Dict[str, Any] = {}
        self._task_futures: Dict[str, Future] = {}
        self._completed_deps: set = set()
        self._lock = threading.Lock()
        self.logger = get_logger("harness.orchestrator")

    def register_agent(self, agent_type: str):
        self.lifecycle.register(agent_type)

    def schedule(self, task: ScheduledTask):
        self._pending_tasks.put(task)
        self.logger.info("task_scheduled", extra={
            "task_id": task.task_id, "agent": task.agent_type,
            "priority": task.priority,
        })

    def execute_plan(self, tasks: List[ScheduledTask],
                     agent_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a plan of scheduled tasks with dependency resolution.
        Supports both serial (dependency-order) and parallel (same-priority) execution.
        """
        self._executor = ThreadPoolExecutor(max_workers=self.resources.max_concurrent)
        self._task_results.clear()
        self._task_futures.clear()
        self._completed_deps.clear()

        for agent_type in agent_map:
            self.register_agent(agent_type)

        for task in tasks:
            self.schedule(task)

        ordered_tasks = []
        while not self._pending_tasks.empty():
            ordered_tasks.append(self._pending_tasks.get())

        batch_map: Dict[int, List[ScheduledTask]] = {}
        for task in ordered_tasks:
            depth = len(task.depends_on)
            if depth not in batch_map:
                batch_map[depth] = []
            batch_map[depth].append(task)

        all_results: List[Dict[str, Any]] = []
        has_failure = False

        for depth in sorted(batch_map.keys()):
            batch = batch_map[depth]
            self.logger.info("executing_batch", extra={"depth": depth, "tasks": len(batch)})

            if self.enable_parallel and len(batch) > 1:
                batch_results = self._execute_parallel(batch, agent_map)
            else:
                batch_results = [self._execute_single(task, agent_map) for task in batch]

            for r in batch_results:
                if r.get("status") == "failed":
                    has_failure = True
                all_results.append(r)
                if r.get("task_id"):
                    self._completed_deps.add(r["task_id"])

        self._executor.shutdown(wait=True)

        return {
            "plan_success": not has_failure,
            "steps": all_results,
            "total_steps": len(all_results),
            "completed_steps": sum(1 for r in all_results if r.get("status") == "completed"),
            "failed_steps": sum(1 for r in all_results if r.get("status") == "failed"),
            "degraded_steps": sum(1 for r in all_results if r.get("degraded", False)),
        }

    def _execute_single(self, task: ScheduledTask, agent_map: Dict[str, Any]) -> Dict[str, Any]:
        self.lifecycle.transition(task.agent_type, AgentLifecycle.RUNNING)
        start = time.time()
        result = {
            "task_id": task.task_id, "step_id": task.step_id,
            "agent_type": task.agent_type, "status": "completed",
            "degraded": False, "retried": False,
        }
        agent = agent_map.get(task.agent_type)
        if not agent:
            degraded_type = self.fallback.get_degraded_agent(task.agent_type)
            if degraded_type and degraded_type in agent_map:
                self.lifecycle.transition(task.agent_type, AgentLifecycle.DEGRADING)
                agent = agent_map[degraded_type]
                result["degraded"] = True
                result["degraded_from"] = task.agent_type
            else:
                result["status"] = "failed"
                result["error"] = f"Agent {task.agent_type} not available"
                result["duration_ms"] = (time.time() - start) * 1000
                self.lifecycle.transition(task.agent_type, AgentLifecycle.FAILED)
                return result

        max_retries = task.max_retries
        for attempt in range(max_retries + 1):
            try:
                agent.initialize(task.task_id, task.step_id)
                agent_result = agent.run(task.kwargs.get("input_context", {}))
                agent.destroy()
                result["result"] = agent_result
                result["duration_ms"] = (time.time() - start) * 1000
                if attempt > 0:
                    result["retried"] = True
                    result["retry_attempt"] = attempt
                self.lifecycle.transition(task.agent_type, AgentLifecycle.COMPLETED)
                return result
            except Exception as e:
                if attempt < max_retries:
                    self.lifecycle.transition(task.agent_type, AgentLifecycle.RETRYING)
                    time.sleep(0.5 * (attempt + 1))
                else:
                    self.lifecycle.transition(task.agent_type, AgentLifecycle.FAILED)
                    fallback_data = self.fallback.get_fallback_data(task.agent_type)
                    result["status"] = "failed"
                    result["error"] = str(e)
                    result["result"] = fallback_data
                    result["duration_ms"] = (time.time() - start) * 1000
                    return result

        result["status"] = "failed"
        result["duration_ms"] = (time.time() - start) * 1000
        return result

    def _execute_parallel(self, batch: List[ScheduledTask],
                          agent_map: Dict[str, Any]) -> List[Dict[str, Any]]:
        futures: Dict[str, Future] = {}
        for task in batch:
            future = self._executor.submit(self._execute_single, task, agent_map)
            futures[task.task_id] = future
        results = []
        for task in batch:
            try:
                result = futures[task.task_id].result(timeout=task.timeout_seconds)
                results.append(result)
            except Exception as e:
                results.append({
                    "task_id": task.task_id, "step_id": task.step_id,
                    "agent_type": task.agent_type, "status": "failed",
                    "error": f"Timeout or execution error: {e}",
                })
        return results

    def get_orchestration_status(self) -> Dict[str, Any]:
        return {
            "lifecycle": {k: v.value for k, v in self.lifecycle._states.items()},
            "resources": self.resources.get_status(),
            "completed_deps": len(self._completed_deps),
            "pending_tasks": self._pending_tasks.qsize(),
        }
