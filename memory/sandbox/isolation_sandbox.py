from typing import Any, Optional
from models.sandbox_memory import AgentSandboxMemory
from core.lifecycle import MemoryLifeCycle

class IsolatedAgentSandbox:
    def __init__(self, sandbox_meta: AgentSandboxMemory):
        self.meta = sandbox_meta
        self.is_destroyed = False

    # 沙盒写入（配额+权限校验）
    def set_data(self, key: str, value: Any, agent_type: str) -> None:
        if self.is_destroyed:
            raise RuntimeError("沙盒已销毁，无法写入")
        if not MemoryLifeCycle.is_sandbox_valid(self.meta, agent_type):
            raise PermissionError("沙盒权限校验失败")
        self.meta.private_data[key] = value

    # 沙盒读取
    def get_data(self, key: str, agent_type: str) -> Optional[Any]:
        if not MemoryLifeCycle.is_sandbox_valid(self.meta, agent_type):
            raise PermissionError("沙盒权限校验失败")
        return self.meta.private_data.get(key)

    # 主动销毁
    def destroy(self) -> None:
        MemoryLifeCycle.destroy_sandbox(self.meta)
        self.is_destroyed = True