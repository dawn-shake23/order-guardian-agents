from datetime import datetime
from models.cache_memory import CacheItem

class TTLCache:
    @staticmethod
    def is_expired(item: CacheItem) -> bool:
        return (datetime.now() - item.created_at).total_seconds() > item.ttl_seconds