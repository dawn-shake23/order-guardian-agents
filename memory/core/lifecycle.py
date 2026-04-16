from datetime import datetime, timedelta
from typing import Optional
from models.sandbox_memory import AgentSandboxMemory
from core.quota_manager import SandboxQuota

class MemoryLifeCycle:
    # 沙盒创建（自动计算过期时间）
    @staticmethod
    def create_sandbox(session_id: str, step_id: int, agent_type: str) -> AgentSandboxMemory:
        created_at = datetime.now()
        expire_at = created_at + timedelta(minutes=5)
        return AgentSandboxMemory(
            session_id=session_id,
            step_id=step_id,
            agent_type=agent_type,
            created_at=created_at,
            expire_at=expire_at
        )

    # 校验沙盒有效性
    @staticmethod
    def is_sandbox_valid(sandbox: AgentSandboxMemory, agent_type: str) -> bool:
        # 权限隔离：仅自身可访问
        if sandbox.agent_type != agent_type:
            return False
        # 过期校验
        if datetime.now() > sandbox.expire_at:
            return False
        # 配额校验
        if not SandboxQuota.check_quota(sandbox):
            return False
        return True

    # 沙盒GC销毁
    @staticmethod
    def destroy_sandbox(sandbox: AgentSandboxMemory) -> None:
        sandbox.private_data.clear()
        del sandbox

    # 缓存过期校验
    @staticmethod
    def is_cache_expired(ttl_seconds: int, created_at: datetime) -> bool:
        return (datetime.now() - created_at).total_seconds() > ttl_seconds