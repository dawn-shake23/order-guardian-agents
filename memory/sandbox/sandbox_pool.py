from typing import Dict, Optional
from Memory.sandbox.isolation_sandbox import IsolatedAgentSandbox

class SandboxPool:
    def __init__(self):
        self.sandboxes: Dict[str, IsolatedAgentSandbox] = {}
    
    def acquire(self, key: str, sandbox: IsolatedAgentSandbox) -> bool:
        """
         acquire a sandbox into the pool
        """
        if key not in self.sandboxes:
            self.sandboxes[key] = sandbox
            return True
        return False
    
    def release(self, key: str) -> bool:
        """
        Release a sandbox from the pool
        """
        if key in self.sandboxes:
            del self.sandboxes[key]
            return True
        return False
    
    def get(self, key: str) -> Optional[IsolatedAgentSandbox]:
        """
        Get a sandbox from the pool
        """
        return self.sandboxes.get(key)
    
    def clear(self):
        """
        Clear all sandboxes from the pool
        """
        self.sandboxes.clear()