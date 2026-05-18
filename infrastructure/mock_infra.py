import json
import time
import threading
import os
from typing import Dict, Any, Optional, List
from queue import Queue, Empty


class MockRedis:
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._ttl: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._ttl and time.time() > self._ttl[key]:
                del self._store[key]
                del self._ttl[key]
                return None
            return self._store.get(key)

    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        with self._lock:
            self._store[key] = value
            if expire:
                self._ttl[key] = time.time() + expire
            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                self._ttl.pop(key, None)
                return True
            return False

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def incr(self, key: str) -> int:
        with self._lock:
            val = self._store.get(key, 0) + 1
            self._store[key] = val
            return val

    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            return list(self._store.keys())


class MockMQ:
    def __init__(self):
        self._queues: Dict[str, Queue] = {}
        self._lock = threading.Lock()

    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        with self._lock:
            if topic not in self._queues:
                self._queues[topic] = Queue()
            self._queues[topic].put(message)
        return True

    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        with self._lock:
            if topic not in self._queues:
                return None
        try:
            return self._queues[topic].get(timeout=timeout)
        except Empty:
            return None


class MockDB:
    def __init__(self, persist_path: Optional[str] = None):
        self._tables: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    def insert(self, table: str, pk: str, data: Dict[str, Any]) -> bool:
        with self._lock:
            if table not in self._tables:
                self._tables[table] = {}
            self._tables[table][pk] = data
            self._persist()
        return True

    def get(self, table: str, pk: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._tables.get(table, {}).get(pk)

    def update(self, table: str, pk: str, data: Dict[str, Any]) -> bool:
        with self._lock:
            if table in self._tables and pk in self._tables[table]:
                self._tables[table][pk].update(data)
                self._persist()
                return True
        return False

    def delete(self, table: str, pk: str) -> bool:
        with self._lock:
            if table in self._tables and pk in self._tables[table]:
                del self._tables[table][pk]
                self._persist()
                return True
        return False

    def query(self, table: str, conditions: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        with self._lock:
            rows = list(self._tables.get(table, {}).values())
        if not conditions:
            return rows
        result = []
        for row in rows:
            match = True
            for k, v in conditions.items():
                if row.get(k) != v:
                    match = False
                    break
            if match:
                result.append(row)
        return result

    def count(self, table: str) -> int:
        with self._lock:
            return len(self._tables.get(table, {}))

    def _persist(self):
        if self._persist_path:
            try:
                with open(self._persist_path, "w", encoding="utf-8") as f:
                    json.dump(self._tables, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _load(self):
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                self._tables = json.load(f)
        except Exception:
            self._tables = {}


class MockMetrics:
    def __init__(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def inc_counter(self, name: str, value: float = 1.0, tags: Optional[Dict] = None):
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float, tags: Optional[Dict] = None):
        with self._lock:
            self._gauges[name] = value

    def record_histogram(self, name: str, value: float, tags: Optional[Dict] = None):
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = []
            self._histograms[name].append(value)

    def get_counter(self, name: str) -> float:
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        return self._gauges.get(name)

    def get_histogram_summary(self, name: str) -> Dict[str, float]:
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "avg": 0, "max": 0, "min": 0}
        return {
            "count": len(values),
            "avg": sum(values) / len(values),
            "max": max(values),
            "min": min(values)
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: self.get_histogram_summary(k) for k in self._histograms}
            }


class MockRAG:
    def __init__(self):
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add_document(self, doc_id: str, title: str, content: str, biz_domain: str, doc_type: str = "rule"):
        with self._lock:
            self._documents[doc_id] = {
                "doc_id": doc_id, "title": title, "content": content,
                "biz_domain": biz_domain, "doc_type": doc_type
            }

    def search(self, query: str, biz_domain: Optional[str] = None, top_k: int = 5,
               doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            candidates = list(self._documents.values())
        if biz_domain:
            candidates = [d for d in candidates if d.get("biz_domain") == biz_domain]
        if doc_type:
            candidates = [d for d in candidates if d.get("doc_type") == doc_type]
        scored = []
        query_lower = query.lower()
        for doc in candidates:
            score = 0.0
            title_lower = doc.get("title", "").lower()
            content_lower = doc.get("content", "").lower()
            for kw in query_lower.split():
                if kw in title_lower:
                    score += 3.0
                if kw in content_lower:
                    score += 1.0
            if score > 0:
                scored.append({**doc, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._documents.get(doc_id)

    def list_documents(self, biz_domain: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = list(self._documents.values())
        if biz_domain:
            docs = [d for d in docs if d.get("biz_domain") == biz_domain]
        return docs
