import time
import threading
from typing import Dict, Any, Optional, List
from core.logger import get_logger


class AgentPool:
    def __init__(self, max_per_type: int = 3):
        self.max_per_type = max_per_type
        self._pool: Dict[str, List] = {}
        self._available: Dict[str, List] = {}
        self._lock = threading.Lock()
        self.logger = get_logger("agent_pool")

    def register(self, agent_type: str, agent):
        with self._lock:
            if agent_type not in self._pool:
                self._pool[agent_type] = []
                self._available[agent_type] = []
            self._pool[agent_type].append(agent)
            self._available[agent_type].append(agent)
        self.logger.info("Agent注册到池", extra={"agent_type": agent_type})

    def acquire(self, agent_type: str, timeout: float = 10.0) -> Optional[Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                available = self._available.get(agent_type, [])
                if available:
                    agent = available.pop(0)
                    self.logger.info("Agent从池中获取", extra={"agent_type": agent_type})
                    return agent
            time.sleep(0.1)
        self.logger.warning("Agent获取超时", extra={"agent_type": agent_type})
        return None

    def release(self, agent_type: str, agent):
        with self._lock:
            if agent_type not in self._available:
                self._available[agent_type] = []
            self._available[agent_type].append(agent)
        self.logger.info("Agent归还到池", extra={"agent_type": agent_type})

    def get_status(self) -> Dict[str, Any]:
        status = {}
        with self._lock:
            for agent_type, agents in self._pool.items():
                available = self._available.get(agent_type, [])
                status[agent_type] = {
                    "total": len(agents),
                    "available": len(available),
                    "in_use": len(agents) - len(available)
                }
        return status
