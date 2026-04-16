from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime

class AgentSandboxMemory(BaseModel):
    session_id: str
    step_id: int
    agent_type: str
    private_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    expire_at: datetime
    quota_limit: int = Field(default=20, description="单沙盒字段配额")
    is_isolated: bool = Field(default=True)