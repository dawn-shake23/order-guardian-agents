from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class CacheItem(BaseModel):
    key: str
    value: Any
    created_at: datetime = Field(default_factory=datetime.now)
    ttl_seconds: int = Field(default=300)
    source: str = Field(default="unknown")