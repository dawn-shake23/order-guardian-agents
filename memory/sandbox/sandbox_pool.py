from typing import dict
from sandbox.isolation_sandbox import IsolatedAgentSandbox

class SandboxPool:
    def __init__(self, max_pool_size: int = 20):
        self.pool: dict[str, IsolatedAgentSandbox] = {}
        self.max_size = max_pool_size

    def acquire(self, key: str, sandbox: IsolatedAgentSandbox) -> None:
        if len(self.pool) >= self.max_size:
            raise RuntimeError("sandbox pool overflow")
        self.pool[key] = sandbox

    def release(self, key: str) -> None:
        if key in self.pool:
            self.pool[key].destroy()
            del self.pool[key]