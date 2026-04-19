from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from memory.memory_hub import MemoryHub
from memory.sandbox.isolation_sandbox import IsolatedAgentSandbox
from tools.tool_registry import tool_registry
from tools.BaseTool.base_tool import ToolResult

# 专家Agent元信息
class AgentMeta(BaseModel):
    agent_type: str
    version: str = "1.0.0"
    allowed_tools: List[str] = Field(default_factory=list)
    allowed_memory_access: bool = True
    sandbox_isolated: bool = True
    timeout_seconds: int = 30
    required_fields: List[str] = Field(default_factory=list)
    acl_scopes: List[str] = Field(default_factory=list)

# Agent输入
class AgentInput(BaseModel):
    session_id: str
    order_id: str
    params: Dict[str, Any]

# Agent输出
class AgentOutput(BaseModel):
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

# 所有专家Agent的父类
class BaseAgent(ABC):
    def __init__(self, meta: AgentMeta, memory_hub: MemoryHub):
        self.meta = meta
        self.memory_hub = memory_hub
        self.sandbox: Optional[IsolatedAgentSandbox] = None
        self.initialized = False

    # 初始化：创建沙盒
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

    # 统一工具调用（MCP 授权后才能调用）
    def call_tool(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        if not self.initialized:
            raise RuntimeError("Agent未初始化")

        # 工具权限校验
        if tool_name not in self.meta.allowed_tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error_msg="该Agent无此工具权限",
                agent_type=self.meta.agent_type
            )

        tool = tool_registry.get_tool(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error_msg=f"工具 {tool_name} 未注册或未初始化",
                agent_type=self.meta.agent_type
            )
        return tool.execute(
            agent_type=self.meta.agent_type,
            params=params,
            sandbox=self.sandbox
        )

    # 专家核心执行逻辑
    @abstractmethod
    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    # 销毁：清理沙盒
    def destroy(self) -> None:
        if self.sandbox:
            self.memory_hub.destroy_sandbox(
                self.sandbox.meta.session_id,
                self.sandbox.meta.step_id,
                self.meta.agent_type
            )
        self.initialized = False

# BaseWorkerAgent类，用于Coordinator和PlanAgent
class BaseWorkerAgent(BaseAgent):
    def __init__(self, meta: AgentMeta):
        # 注意：这里简化处理，实际应该传入memory_hub
        super().__init__(meta, MemoryHub())
    
    def execute(self, agent_input: AgentInput) -> Dict[str, Any]:
        """
        执行Agent任务
        """
        raise NotImplementedError