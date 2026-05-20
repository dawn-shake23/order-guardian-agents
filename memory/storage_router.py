"""
Unified storage router with data classification, cold/hot separation, incremental updates.

Four storage tiers:
  hot_store  - Structured business data (orders, payments, risks, reconciliations)
  vector_store - Vector knowledge base (FAISS indexed)
  cold_store - Task run logs, audit trails, historical snapshots
  rule_store - Risk rule configurations, decision policies, SOP templates
"""
import json
import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from core.logger import get_logger


class StorageTier(str, Enum):
    HOT = "hot"
    VECTOR = "vector"
    COLD = "cold"
    RULE = "rule"


@dataclass
class StorageConfig:
    hot_dir: str = "./data/hot_store"
    vector_dir: str = "./data/faiss_index"
    cold_dir: str = "./data/cold_store"
    rule_dir: str = "./data/rule_store"
    hot_ttl_seconds: int = 86400
    cold_archive_days: int = 30
    max_hot_records: int = 10000


class HotStore:
    """
    In-memory structured business data with TTL-based expiration.
    Stores: orders, payments, risk_assessments, reconciliations, sessions.
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.cfg = config or StorageConfig()
        self._tables: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, Dict[str, float]] = {}
        self.logger = get_logger("storage.hot")

    def put(self, table: str, pk: str, data: Dict[str, Any]):
        if table not in self._tables:
            self._tables[table] = {}
            self._timestamps[table] = {}
        self._tables[table][pk] = data
        self._timestamps[table][pk] = time.time()
        self._evict_if_needed(table)

    def get(self, table: str, pk: str) -> Optional[Dict[str, Any]]:
        if table not in self._tables or pk not in self._tables[table]:
            return None
        ts = self._timestamps[table].get(pk, 0)
        if time.time() - ts > self.cfg.hot_ttl_seconds:
            self._expire_one(table, pk)
            return None
        return self._tables[table][pk]

    def query(self, table: str, conditions: Optional[Dict[str, Any]] = None) -> List[Dict]:
        if table not in self._tables:
            return []
        rows = list(self._tables[table].values())
        if not conditions:
            return rows
        result = []
        for row in rows:
            if all(row.get(k) == v for k, v in conditions.items()):
                result.append(row)
        return result

    def count(self, table: str) -> int:
        return len(self._tables.get(table, {}))

    def _expire_one(self, table: str, pk: str):
        self._tables[table].pop(pk, None)
        self._timestamps[table].pop(pk, None)

    def _evict_if_needed(self, table: str):
        if len(self._tables.get(table, {})) > self.cfg.max_hot_records:
            oldest = sorted(self._timestamps[table].items(), key=lambda x: x[1])
            for pk, _ in oldest[:100]:
                self._expire_one(table, pk)
            self.logger.info("hot_eviction", extra={"table": table, "kept": len(self._tables[table])})


class ColdStore:
    """
    Append-only persistent log store for task runs, audit trails, diagnostics.
    Data is written to daily JSONL files; auto-archived after archive_days.
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.cfg = config or StorageConfig()
        os.makedirs(self.cfg.cold_dir, exist_ok=True)
        self.logger = get_logger("storage.cold")

    def append(self, stream: str, record: Dict[str, Any]):
        record["_ts"] = time.time()
        record["_stream"] = stream
        today = time.strftime("%Y-%m-%d")
        path = os.path.join(self.cfg.cold_dir, f"{stream}_{today}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._cleanup(stream)

    def read_recent(self, stream: str, limit: int = 50) -> List[Dict]:
        today = time.strftime("%Y-%m-%d")
        path = os.path.join(self.cfg.cold_dir, f"{stream}_{today}.jsonl")
        if not os.path.exists(path):
            return []
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        return lines[-limit:]

    def _cleanup(self, stream: str):
        threshold = time.time() - self.cfg.cold_archive_days * 86400
        for fname in os.listdir(self.cfg.cold_dir):
            if fname.startswith(stream) and fname.endswith(".jsonl"):
                path = os.path.join(self.cfg.cold_dir, fname)
                if os.path.getmtime(path) < threshold:
                    os.remove(path)
                    self.logger.info("cold_archived", extra={"file": fname})


class RuleStore:
    """
    Risk rule and decision policy configuration store.
    Supports hot-reload from JSON config files.
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.cfg = config or StorageConfig()
        os.makedirs(self.cfg.rule_dir, exist_ok=True)
        self._rules: Dict[str, Dict[str, Any]] = {}
        self._load_defaults()
        self.logger = get_logger("storage.rule")

    def _load_defaults(self):
        self._rules = {
            "E2001": {"domain": "payment", "action": "compensate", "priority": "medium",
                       "description": "Payment timeout - query channel and manual fill if paid"},
            "E2002": {"domain": "payment", "action": "notify", "priority": "medium",
                       "description": "Insufficient balance - notify user to change payment method"},
            "E2003": {"domain": "payment", "action": "switch_channel", "priority": "high",
                       "description": "Channel exception - immediately switch to backup channel"},
            "E2004": {"domain": "payment", "action": "auto_resolve", "priority": "low",
                       "description": "Payment reversed - update order status and notify user"},
            "E2005": {"domain": "payment", "action": "compensate", "priority": "high",
                       "description": "Callback lost - actively query channel and resend callback"},
            "E3001": {"domain": "risk", "action": "manual_review", "priority": "high",
                       "description": "High risk interception - freeze order, manual review required"},
            "E3002": {"domain": "risk", "action": "block", "priority": "critical",
                       "description": "Blacklist user - directly reject all transactions"},
            "E3004": {"domain": "reconciliation", "action": "manual_review", "priority": "medium",
                       "description": "Amount discrepancy - if >1 yuan, financial confirmation required"},
            "E3005": {"domain": "reconciliation", "action": "auto_resolve", "priority": "low",
                       "description": "Status discrepancy - correct order status from payment channel"},
        }
        path = os.path.join(self.cfg.rule_dir, "risk_rules.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                self._rules.update(custom)
            except Exception:
                pass

    def get_rule(self, error_code: str) -> Optional[Dict[str, Any]]:
        return self._rules.get(error_code)

    def get_rules_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        result = []
        for code, rule in self._rules.items():
            if rule.get("domain") == domain:
                result.append({"error_code": code, **rule})
        return result

    def add_rule(self, error_code: str, rule: Dict[str, Any]):
        self._rules[error_code] = rule
        path = os.path.join(self.cfg.rule_dir, "risk_rules.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._rules, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reload(self):
        self._load_defaults()
        self.logger.info("rules_reloaded", extra={"count": len(self._rules)})


class StorageRouter:
    """
    Unified storage facade. Routes data to the correct storage tier based on type.
    """

    def __init__(self, config: Optional[StorageConfig] = None,
                 vector_store=None, memory_hub=None):
        self.cfg = config or StorageConfig()
        self.hot = HotStore(self.cfg)
        self.cold = ColdStore(self.cfg)
        self.rule = RuleStore(self.cfg)
        self.vector_store = vector_store
        self.memory_hub = memory_hub
        self.logger = get_logger("storage.router")

    def route_put(self, tier: StorageTier, table: str, pk: str, data: Dict[str, Any]):
        if tier == StorageTier.HOT:
            self.hot.put(table, pk, data)
        elif tier == StorageTier.COLD:
            self.cold.append(table, data)
        elif tier == StorageTier.RULE:
            self.rule.add_rule(pk, data)
        elif tier == StorageTier.VECTOR and self.vector_store and self.memory_hub:
            embedding = data.pop("_embedding", None)
            if embedding:
                self.vector_store.add(embedding, data)
                self.memory_hub.struct_mysql.save(table, pk, data)

    def log_task(self, task_result: Dict[str, Any]):
        self.cold.append("task_runs", task_result)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "hot_tables": {t: self.hot.count(t) for t in self.hot._tables},
            "rules_count": len(self.rule._rules),
            "vector_count": len(self.vector_store) if self.vector_store else 0,
        }
