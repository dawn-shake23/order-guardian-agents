from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import time


# ==========================
# 1. 真正强校验：统一元数据（带字段校验）
# ==========================
class AgentMeta(BaseModel):
    """统一元数据：贯穿调度、监控、审计（风控级强校验）"""
    agent_type: str
    version: str = Field(default="1.0.0", min_length=3, max_length=20)
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    required_fields: List[str]
    acl_scopes: List[str]

    # 强校验：agent_type 不允许为空
    @field_validator('agent_type')
    def agent_type_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("agent_type 不能为空")
        return v.strip()


# ==========================
# 2. 真正强校验：统一入参模型
# ==========================
class AgentInput(BaseModel):
    """Agent 入参强校验模型"""
    session_id: str
    task_id: str
    order_id: str
    params: Dict[str, Any]

    @field_validator('session_id', 'task_id', 'order_id')
    def id_not_empty(cls, v):
        if not v:
            raise ValueError("唯一标识不能为空")
        return v


# ==========================
# 3. 真正强校验：统一出参模型
# ==========================
class AgentOutput(BaseModel):
    """Agent 出参强校验模型（审计、风控、Coordinator 必须）"""
    agent_type: str
    session_id: str
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cost_ms: int
    meta: AgentMeta


# ==========================
# 4. 基类：全链路 Pydantic 强校验
# ==========================
class BaseWorkerAgent(ABC):
    """
    所有专家 Agent 基类
    对齐 Claude Code 工程规范
    全链路 Pydantic 强校验
    无状态、无记忆、可审计
    """

    def __init__(self, meta: AgentMeta):
        self._meta = meta

    @property
    def meta(self) -> AgentMeta:
        return self._meta

    # ==============================================
    # 真正强校验入口：接收 Pydantic 模型，不是字典
    # ==============================================
    def run(self, agent_input: AgentInput) -> AgentOutput:
        start = time.time()
        try:
            # 1. 强校验（Pydantic 自动完成）
            # 2. 业务执行
            result = self.execute(agent_input)

            # 3. 构建标准输出
            return AgentOutput(
                agent_type=self._meta.agent_type,
                session_id=agent_input.session_id,
                success=True,
                message="执行成功",
                data=result,
                cost_ms=int((time.time() - start) * 1000),
                meta=self._meta
            )

        except Exception as e:
            # 异常标准化（风控必须）
            return AgentOutput(
                agent_type=self._meta.agent_type,
                session_id=agent_input.session_id,
                success=False,
                error=str(e),
                cost_ms=int((time.time() - start) * 1000),
                meta=self._meta
            )

    @abstractmethod
    def execute(self, agent_input: AgentInput) -> Dict[str, Any]:
        """
        子类必须实现
        入参出参全部强校验
        """
        pass