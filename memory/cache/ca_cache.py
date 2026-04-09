# memory/cache/ca_cache.py
from typing import Optional, Dict, Any
from pydantic import BaseModel
import time
import numpy as np

class CACacheEntry(BaseModel):
    key: str               # session_id + turn_id
    attention_weights: np.ndarray  # (seq_len, seq_len)
    kv_cache: Dict[str, np.ndarray]
    last_access: float
    ttl: int = 300  # 5分钟

class CACache:
    """
    DeerFlow 2.0 官方实现的 Context Attention Cache
    """
    def __init__(self, max_size: int = 1024):
        self.max_size = max_size
        self.cache: Dict[str, CACacheEntry] = {}

    def get(self, key: str) -> Optional[CACacheEntry]:
        entry = self.cache.get(key)
        if not entry:
            return None
        if time.time() - entry.last_access > entry.ttl:
            self.cache.pop(key)
            return None
        entry.last_access = time.time()
        return entry

    def set(self, key: str, attn_weights: np.ndarray, kv_cache: Dict[str, np.ndarray]):
        if len(self.cache) >= self.max_size:
            self._evict_lru()
        self.cache[key] = CACacheEntry(
            key=key,
            attention_weights=attn_weights,
            kv_cache=kv_cache,
            last_access=time.time()
        )

    def _evict_lru(self):
        sorted_entries = sorted(self.cache.items(), key=lambda x: x[1].last_access)
        if sorted_entries:
            self.cache.pop(sorted_entries[0][0])