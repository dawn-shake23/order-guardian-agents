from datetime import datetime
from memory.sandbox.isolation_sandbox import SandboxMeta

class MemoryLifeCycle:
    @staticmethod
    def create_sandbox(session_id: str, step_id: int, agent_type: str) -> SandboxMeta:
        """
        创建沙箱元数据
        """
        return SandboxMeta(
            session_id=session_id,
            step_id=step_id,
            agent_type=agent_type,
            created_at=datetime.now().timestamp()
        )
    
    @staticmethod
    def is_sandbox_expired(sandbox_meta: SandboxMeta, timeout_seconds: int = 3600) -> bool:
        """
        检查沙箱是否过期
        """
        current_time = datetime.now().timestamp()
        return current_time - sandbox_meta.created_at > timeout_seconds
    
    @staticmethod
    def generate_memory_key(prefix: str, *args) -> str:
        """
        生成内存键
        """
        parts = [prefix] + [str(arg) for arg in args]
        return ":".join(parts)