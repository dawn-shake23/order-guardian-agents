from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

# 工具元数据模型
class ToolMeta(BaseModel):
    tool_name: str
    tool_version: str = "1.0.0"
    tool_description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    allowed_agent_types: List[str]  # 允许调用的Agent类型
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    max_retry: int = Field(default=2, ge=0, le=3)
    need_sandbox: bool = True
    need_memory: bool = False
    sensitive_level: str = Field(default="public", description="public/internal/confidential")

# 工具执行结果模型
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error_msg: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    used_sandbox: bool = False
    agent_type: str

# 工具基类：所有工具必须继承
class BaseTool(ABC):
    def __init__(self, meta: ToolMeta):
        self.meta = meta
        self.is_initialized = False
        self.is_destroyed = False

    # 生命周期：初始化
    def initialize(self) -> None:
        if self.is_initialized or self.is_destroyed:
            raise RuntimeError("工具状态异常，无法初始化")
        self._on_initialize()
        self.is_initialized = True

    # 生命周期：权限前置校验
    def pre_check(self, agent_type: str, params: Dict[str, Any]) -> bool:
        if not self.is_initialized or self.is_destroyed:
            return False
        if agent_type not in self.meta.allowed_agent_types:
            return False
        return self._pre_check_logic(agent_type, params)

    # 生命周期：工具执行
    def execute(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any] = None) -> ToolResult:
        try:
            # 前置校验
            if not self.pre_check(agent_type, params):
                return ToolResult(
                    tool_name=self.meta.tool_name,
                    success=False,
                    error_msg="前置校验/权限校验失败",
                    agent_type=agent_type
                )
            # 执行前处理
            self._before_execute(agent_type, params, sandbox)
            # 核心执行逻辑
            result_data = self._execute_logic(agent_type, params, sandbox)
            # 执行后处理
            self._after_execute(agent_type, result_data, sandbox)
            return ToolResult(
                tool_name=self.meta.tool_name,
                success=True,
                data=result_data,
                used_sandbox=self.meta.need_sandbox,
                agent_type=agent_type
            )
        except Exception as e:
            self._on_error(agent_type, str(e))
            return ToolResult(
                tool_name=self.meta.tool_name,
                success=False,
                error_msg=str(e),
                agent_type=agent_type
            )

    # 生命周期：资源销毁
    def destroy(self) -> None:
        if self.is_destroyed or not self.is_initialized:
            return
        self._on_destroy()
        self.is_destroyed = True
        self.is_initialized = False

    # ------------------- 子类实现方法 -------------------
    @abstractmethod
    def _on_initialize(self) -> None:
        """初始化逻辑"""
        pass

    @abstractmethod
    def _pre_check_logic(self, agent_type: str, params: Dict[str, Any]) -> bool:
        """前置校验逻辑"""
        pass

    @abstractmethod
    def _execute_logic(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any]) -> Dict[str, Any]:
        """核心执行逻辑"""
        pass

    def _before_execute(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any]) -> None:
        """执行前钩子"""
        pass

    def _after_execute(self, agent_type: str, result: Dict[str, Any], sandbox: Optional[Any]) -> None:
        """执行后钩子"""
        pass

    def _on_error(self, agent_type: str, error: str) -> None:
        """异常处理钩子"""
        pass

    def _on_destroy(self) -> None:
        """资源销毁钩子"""
        pass