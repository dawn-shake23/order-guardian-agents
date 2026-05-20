"""
Layered memory system for agent cognitive continuity.

Three tiers:
  Tier 1 - ShortTermBuffer:   current conversation context, rolling window
  Tier 2 - LongTermTaskStore:  historical diagnosis tasks, indexed by order_id
  Tier 3 - ExperienceRepo:     accumulated business resolution experience
"""
import time
import json
import os
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict

from core.logger import get_logger


@dataclass
class MemoryConfig:
    short_term_window: int = 32
    short_term_ttl: int = 300
    long_term_max_tasks: int = 1000
    experience_max_entries: int = 500
    persistence_dir: str = "./data/memory"


class ShortTermBuffer:
    """
    Tier 1: Rolling window conversation context.
    Holds current session's agent outputs, query history, intermediate results.
    Auto-compresses when buffer exceeds threshold.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.cfg = config or MemoryConfig()
        self._buffer: OrderedDict = OrderedDict()
        self._context: Dict[str, Any] = {}
        self.logger = get_logger("memory.short_term")

    def put(self, key: str, value: Any):
        self._buffer[key] = {"value": value, "ts": time.time()}
        if len(self._buffer) > self.cfg.short_term_window:
            self._buffer.popitem(last=False)
        self.logger.debug("short_term_put", extra={"key": key, "size": len(self._buffer)})

    def get(self, key: str) -> Optional[Any]:
        entry = self._buffer.get(key)
        if entry is None:
            return None
        if time.time() - entry["ts"] > self.cfg.short_term_ttl:
            del self._buffer[key]
            return None
        return entry["value"]

    def get_context_snapshot(self) -> Dict[str, Any]:
        """Return all non-expired context for agent injection."""
        now = time.time()
        snapshot = {}
        for k, v in self._buffer.items():
            if now - v["ts"] <= self.cfg.short_term_ttl:
                snapshot[k] = v["value"]
        return snapshot

    def compress(self) -> str:
        """Summarize buffer content into a compact string for context injection."""
        snapshot = self.get_context_snapshot()
        parts = []
        for k, v in snapshot.items():
            vs = str(v)
            if len(vs) > 200:
                vs = vs[:200] + "..."
            parts.append(f"[{k}] {vs}")
        return "\n".join(parts)

    def clear_expired(self):
        now = time.time()
        expired = [k for k, v in self._buffer.items() if now - v["ts"] > self.cfg.short_term_ttl]
        for k in expired:
            del self._buffer[k]


class LongTermTaskStore:
    """
    Tier 2: Persistent store of completed diagnosis tasks.
    Indexed by order_id for quick lookup of similar historical cases.
    Autoloads from disk.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.cfg = config or MemoryConfig()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, List[str]] = {}
        self.logger = get_logger("memory.long_term")
        self._load()

    def record_task(self, order_id: str, task_result: Dict[str, Any]):
        task_id = f"task_{int(time.time())}_{order_id}"
        record = {
            "task_id": task_id,
            "order_id": order_id,
            "timestamp": time.time(),
            "risk_level": task_result.get("risk_level", ""),
            "root_cause": task_result.get("abnormal_root_cause", ""),
            "solution": task_result.get("solution", ""),
            "success": task_result.get("plan_success", False),
            "decision_type": task_result.get("decision_type", ""),
            "duration_ms": task_result.get("total_duration_ms", 0),
        }
        self._tasks[task_id] = record

        if order_id not in self._index:
            self._index[order_id] = []
        self._index[order_id].append(task_id)

        if len(self._tasks) > self.cfg.long_term_max_tasks:
            oldest = min(self._tasks.keys(), key=lambda k: self._tasks[k]["timestamp"])
            old_order = self._tasks[oldest]["order_id"]
            del self._tasks[oldest]
            if old_order in self._index:
                self._index[old_order] = [t for t in self._index[old_order] if t != oldest]
                if not self._index[old_order]:
                    del self._index[old_order]

        self._save()
        self.logger.info("task_recorded", extra={"task_id": task_id, "order_id": order_id})

    def find_similar(self, order_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find historical tasks for the same order."""
        task_ids = self._index.get(order_id, [])
        result = [self._tasks[tid] for tid in task_ids[-limit:] if tid in self._tasks]
        return sorted(result, key=lambda r: r["timestamp"], reverse=True)

    def find_by_error_pattern(self, risk_level: str = "", root_cause_keyword: str = "", limit: int = 5) -> List[Dict]:
        """Search historical tasks by risk level or root cause keyword."""
        candidates = []
        for task in self._tasks.values():
            if risk_level and task.get("risk_level") != risk_level:
                continue
            if root_cause_keyword and root_cause_keyword.lower() not in task.get("root_cause", "").lower():
                continue
            candidates.append(task)
        return sorted(candidates, key=lambda r: r["timestamp"], reverse=True)[:limit]

    def _save(self):
        os.makedirs(self.cfg.persistence_dir, exist_ok=True)
        path = os.path.join(self.cfg.persistence_dir, "long_term_tasks.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"tasks": self._tasks, "index": self._index}, f, ensure_ascii=False)
        except Exception:
            pass

    def _load(self):
        path = os.path.join(self.cfg.persistence_dir, "long_term_tasks.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._tasks = data.get("tasks", {})
                self._index = data.get("index", {})
                self.logger.info("long_term_loaded", extra={"tasks": len(self._tasks)})
            except Exception:
                pass

    @property
    def task_count(self) -> int:
        return len(self._tasks)


class ExperienceRepository:
    """
    Tier 3: Accumulated business resolution experience.
    Stores successful (error_code, domain) -> solution mappings.
    Auto-learns from completed tasks to build a resolution knowledge graph.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.cfg = config or MemoryConfig()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger("memory.experience")
        self._load()

    def learn(self, error_code: str, domain: str, solution: str, success: bool):
        if not success:
            return
        key = f"{domain}:{error_code}"
        if key not in self._entries:
            self._entries[key] = {"count": 0, "solutions": [], "domain": domain, "error_code": error_code}
        entry = self._entries[key]
        entry["count"] += 1
        h = hashlib.md5(solution.encode()).hexdigest()[:8]
        existing = [s for s in entry["solutions"] if s["hash"] == h]
        if existing:
            existing[0]["count"] += 1
        else:
            entry["solutions"].append({"hash": h, "text": solution, "count": 1})
        entry["solutions"].sort(key=lambda s: s["count"], reverse=True)
        if len(entry["solutions"]) > 10:
            entry["solutions"] = entry["solutions"][:10]
        if len(self._entries) > self.cfg.experience_max_entries:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].get("count", 0))
            del self._entries[oldest]
        self._save()

    def recall(self, error_code: str, domain: str = "") -> Optional[str]:
        """Recall the best solution for an error code."""
        if domain:
            key = f"{domain}:{error_code}"
            entry = self._entries.get(key)
            if entry and entry["solutions"]:
                return entry["solutions"][0]["text"]
        for key, entry in self._entries.items():
            if error_code in key and entry["solutions"]:
                return entry["solutions"][0]["text"]
        return None

    def get_domain_experiences(self, domain: str) -> List[Dict]:
        """Get all experiences for a business domain."""
        result = []
        for key, entry in self._entries.items():
            if entry["domain"] == domain:
                result.append({"error_code": entry["error_code"], "count": entry["count"],
                               "top_solution": entry["solutions"][0]["text"] if entry["solutions"] else ""})
        return sorted(result, key=lambda r: r["count"], reverse=True)

    def _save(self):
        os.makedirs(self.cfg.persistence_dir, exist_ok=True)
        path = os.path.join(self.cfg.persistence_dir, "experience_repo.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False)
        except Exception:
            pass

    def _load(self):
        path = os.path.join(self.cfg.persistence_dir, "experience_repo.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except Exception:
                pass


class AgentMemoryFacade:
    """
    Unified memory interface for agents.
    Combines all three tiers behind a single facade.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.cfg = config or MemoryConfig()
        self.short_term = ShortTermBuffer(self.cfg)
        self.long_term = LongTermTaskStore(self.cfg)
        self.experience = ExperienceRepository(self.cfg)
        self.logger = get_logger("memory.facade")

    def start_session(self, order_id: str):
        self.short_term = ShortTermBuffer(self.cfg)
        self.short_term.put("order_id", order_id)
        similar = self.long_term.find_similar(order_id, limit=3)
        if similar:
            self.short_term.put("historical_tasks", similar)
            self.logger.info("session_with_history", extra={"order_id": order_id, "similar": len(similar)})

    def record_agent_output(self, agent_type: str, result: Dict[str, Any]):
        self.short_term.put(f"agent_{agent_type}", result)

    def get_context_for_agent(self, agent_type: str) -> Dict[str, Any]:
        ctx = self.short_term.get_context_snapshot()
        experience = self.experience.get_domain_experiences(agent_type)[:5]
        ctx["relevant_experience"] = experience
        return ctx

    def finalize_task(self, order_id: str, final_result: Dict[str, Any]):
        self.long_term.record_task(order_id, final_result)
        error_code = final_result.get("abnormal_root_cause", "")
        domain = "payment"
        solution = final_result.get("solution", "")
        self.experience.learn(error_code, domain, solution, final_result.get("plan_success", False))
