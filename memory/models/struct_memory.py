from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

# 会话记忆（Redis+MySQL）
class SessionMemory(BaseModel):
    session_id: str
    order_id: str
    global_context: Dict[str, Any]
    status: str = Field(default="running", description="running/paused/done/error")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    is_deleted: bool = Field(default=False)

# 步骤记忆（断点续传）
class StepMemory(BaseModel):
    step_id: int
    session_id: str
    expert_type: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    status: str = Field(default="pending")
    ttl_seconds: int = Field(default=1800)
    created_at: datetime = Field(default_factory=datetime.now)