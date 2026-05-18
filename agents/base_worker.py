import time
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from memory.memory_hub import MemoryHub
from memory.sandbox.isolation_sandbox import IsolatedAgentSandbox
from tools.tool_registry import tool_registry
from tools.BaseTool.base_tool import ToolResult
from core.errors import AgentError, ToolError, ErrorCode
from core.logger import get_logger
from infrastructure.resilience import CircuitBreaker, RateLimiter
from infrastructure.mock_infra import MockMetrics


class AgentMeta(BaseModel):
    agent_type: str
    version: str = "1.0.0"
    allowed_tools: List[str] = Field(default_factory=list)
    allowed_memory_access: bool = True
    sandbox_isolated: bool = True
    timeout_seconds: int = 30
    required_fields: List[str] = Field(default_factory=list)
    acl_scopes: List[str] = Field(default_factory=list)


class AgentInput(BaseModel):
    session_id: str
    order_id: str
    params: Dict[str, Any]


class AgentOutput(BaseModel):
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: Optional[float] = None
    retried: bool = False
    fallback_used: bool = False


class BaseAgent(ABC):
    def __init__(self, meta: AgentMeta, memory_hub: MemoryHub,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        self.meta = meta
        self.memory_hub = memory_hub
        self.metrics = metrics
        self.circuit_breaker = circuit_breaker
        self.rate_limiter = rate_limiter
        self.sandbox: Optional[IsolatedAgentSandbox] = None
        self.initialized = False
        self.logger = get_logger(f"agent.{meta.agent_type}")

    def initialize(self, session_id: str, step_id: int) -> None:
        if self.initialized:
            return
        if self.meta.sandbox_isolated:
            self.sandbox = self.memory_hub.create_sandbox(
                session_id=session_id,
                step_id=step_id,
                agent_type=self.meta.agent_type
            )
        self.initialized = True
        self.logger.info("Agent初始化完成", extra={
            "session_id": session_id, "step_id": step_id,
            "agent_type": self.meta.agent_type
        })

    def call_tool(self, tool_name: str, params: Dict[str, Any],
                  max_retries: int = 1, retry_interval: float = 0.5) -> ToolResult:
        if not self.initialized:
            return ToolResult(
                tool_name=tool_name, success=False,
                error_msg="Agent未初始化", agent_type=self.meta.agent_type
            )

        if tool_name not in self.meta.allowed_tools:
            self.logger.warning("工具权限拒绝", extra={
                "agent_type": self.meta.agent_type, "tool_name": tool_name
            })
            return ToolResult(
                tool_name=tool_name, success=False,
                error_msg=f"Agent[{self.meta.agent_type}]无权调用工具[{tool_name}]",
                agent_type=self.meta.agent_type
            )

        if self.rate_limiter and not self.rate_limiter.allow():
            return ToolResult(
                tool_name=tool_name, success=False,
                error_msg="请求被限流", agent_type=self.meta.agent_type
            )

        if self.circuit_breaker and not self.circuit_breaker.can_execute():
            return ToolResult(
                tool_name=tool_name, success=False,
                error_msg="熔断器开启，拒绝执行", agent_type=self.meta.agent_type
            )

        tool = tool_registry.get_tool(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name, success=False,
                error_msg=f"工具 {tool_name} 未注册", agent_type=self.meta.agent_type
            )

        last_result = None
        for attempt in range(max_retries + 1):
            try:
                result = tool.execute(
                    agent_type=self.meta.agent_type,
                    params=params,
                    sandbox=self.sandbox
                )
                if result.success:
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success()
                    if self.metrics:
                        self.metrics.inc_counter(f"tool.{tool_name}.success")
                    return result
                last_result = result
                if attempt < max_retries:
                    self.logger.info("工具调用重试", extra={
                        "tool_name": tool_name, "attempt": attempt + 1
                    })
                    time.sleep(retry_interval)
            except Exception as e:
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure()
                if self.metrics:
                    self.metrics.inc_counter(f"tool.{tool_name}.error")
                last_result = ToolResult(
                    tool_name=tool_name, success=False,
                    error_msg=str(e), agent_type=self.meta.agent_type
                )
                if attempt < max_retries:
                    time.sleep(retry_interval)

        if self.circuit_breaker:
            self.circuit_breaker.record_failure()
        return last_result or ToolResult(
            tool_name=tool_name, success=False,
            error_msg="未知错误", agent_type=self.meta.agent_type
        )

    @abstractmethod
    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        try:
            for field in self.meta.required_fields:
                if field not in agent_input.params:
                    return AgentOutput(
                        success=False,
                        error=f"缺少必填字段: {field}",
                        error_code=ErrorCode.INVALID_INPUT.value
                    )

            result = self.run({
                "session_id": agent_input.session_id,
                "order_id": agent_input.order_id,
                **agent_input.params
            })

            duration = (time.time() - start_time) * 1000
            if self.metrics:
                self.metrics.record_histogram(f"agent.{self.meta.agent_type}.duration", duration)
                self.metrics.inc_counter(f"agent.{self.meta.agent_type}.success")

            return AgentOutput(
                success=True,
                data=result,
                duration_ms=round(duration, 2)
            )
        except AgentError as e:
            duration = (time.time() - start_time) * 1000
            self.logger.error("Agent执行错误", extra={
                "agent_type": self.meta.agent_type,
                "error_code": e.error_code.value, "message": e.message,
                "duration_ms": round(duration, 2)
            })
            if self.metrics:
                self.metrics.inc_counter(f"agent.{self.meta.agent_type}.agent_error")
            return AgentOutput(
                success=False, error=e.message,
                error_code=e.error_code.value, duration_ms=round(duration, 2)
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.logger.error("Agent执行异常", extra={
                "agent_type": self.meta.agent_type,
                "error": str(e), "duration_ms": round(duration, 2)
            }, exc_info=True)
            if self.metrics:
                self.metrics.inc_counter(f"agent.{self.meta.agent_type}.unexpected_error")
            fallback = self._fallback(agent_input)
            if fallback:
                fallback.fallback_used = True
                return fallback
            return AgentOutput(
                success=False, error=str(e),
                error_code=ErrorCode.SYSTEM_ERROR.value, duration_ms=round(duration, 2)
            )

    def _fallback(self, agent_input: AgentInput) -> Optional[AgentOutput]:
        return None

    def destroy(self) -> None:
        if self.sandbox:
            self.memory_hub.destroy_sandbox(
                self.sandbox.meta.session_id,
                self.sandbox.meta.step_id,
                self.meta.agent_type
            )
        self.initialized = False
        self.logger.info("Agent销毁完成", extra={"agent_type": self.meta.agent_type})


class BaseWorkerAgent(BaseAgent):
    def __init__(self, meta: AgentMeta, memory_hub: MemoryHub,
                 metrics: Optional[MockMetrics] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        super().__init__(meta, memory_hub, metrics, circuit_breaker, rate_limiter)
