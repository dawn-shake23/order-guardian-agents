import time
import threading
from typing import Dict, Any, Optional, Callable
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0,
                 half_open_max_calls: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return self.half_open_calls < self.half_open_max_calls
        return False

    def record_success(self):
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def get_state(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count
        }


class RateLimiter:
    def __init__(self, name: str, max_requests: int = 100, window_seconds: float = 60.0):
        self.name = name
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self.window_seconds]
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        current = [t for t in self._timestamps if now - t < self.window_seconds]
        return {
            "name": self.name,
            "current_requests": len(current),
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds
        }


class HeartbeatMonitor:
    def __init__(self, interval_seconds: float = 10.0):
        self.interval = interval_seconds
        self._beats: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_unhealthy: Optional[Callable] = None

    def register(self, component_name: str):
        with self._lock:
            self._beats[component_name] = time.time()

    def beat(self, component_name: str):
        with self._lock:
            self._beats[component_name] = time.time()

    def check_health(self) -> Dict[str, Any]:
        now = time.time()
        result = {}
        with self._lock:
            for name, last_beat in self._beats.items():
                elapsed = now - last_beat
                result[name] = {
                    "healthy": elapsed < self.interval * 3,
                    "last_beat_ago": round(elapsed, 2),
                    "status": "healthy" if elapsed < self.interval * 3 else "unhealthy"
                }
        return result

    def start(self, on_unhealthy: Optional[Callable] = None):
        self._on_unhealthy = on_unhealthy
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            health = self.check_health()
            for name, info in health.items():
                if not info["healthy"] and self._on_unhealthy:
                    self._on_unhealthy(name, info)
            time.sleep(self.interval)


class ConcurrencyController:
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        acquired = self._semaphore.acquire(timeout=timeout)
        if acquired:
            with self._lock:
                self._active_count += 1
        return acquired

    def release(self):
        self._semaphore.release()
        with self._lock:
            self._active_count = max(0, self._active_count - 1)

    def get_status(self) -> Dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "active_count": self._active_count,
            "available": self.max_concurrent - self._active_count
        }
