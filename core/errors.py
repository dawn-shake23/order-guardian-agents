import time
import json
import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class ErrorCode(str, Enum):
    E1001 = "E1001"
    E1002 = "E1002"
    E1003 = "E1003"
    E1004 = "E1004"
    E1005 = "E1005"
    E2001 = "E2001"
    E2002 = "E2002"
    E2003 = "E2003"
    E2004 = "E2004"
    E2005 = "E2005"
    E3001 = "E3001"
    E3002 = "E3002"
    E3003 = "E3003"
    E3004 = "E3004"
    E3005 = "E3005"
    SYSTEM_ERROR = "SYS_001"
    NETWORK_ERROR = "SYS_002"
    AGENT_NOT_FOUND = "AGENT_001"
    AGENT_TIMEOUT = "AGENT_002"
    AGENT_PERMISSION_DENIED = "AGENT_003"
    TOOL_NOT_FOUND = "TOOL_001"
    TOOL_EXECUTION_FAILED = "TOOL_002"
    CIRCUIT_OPEN = "SYS_003"
    RATE_LIMITED = "SYS_004"
    INVALID_INPUT = "IO_001"
    INVALID_OUTPUT = "IO_002"


ERROR_CODE_DESC = {
    ErrorCode.E1001: "订单不存在",
    ErrorCode.E1002: "订单状态异常",
    ErrorCode.E1003: "订单金额不一致",
    ErrorCode.E1004: "订单超时未支付",
    ErrorCode.E1005: "订单重复创建",
    ErrorCode.E2001: "支付超时",
    ErrorCode.E2002: "支付余额不足",
    ErrorCode.E2003: "支付渠道异常",
    ErrorCode.E2004: "支付已退回",
    ErrorCode.E2005: "支付回调丢失",
    ErrorCode.E3001: "风控拦截-高风险",
    ErrorCode.E3002: "风控拦截-黑名单",
    ErrorCode.E3003: "风控评分异常",
    ErrorCode.E3004: "对账不一致-金额差异",
    ErrorCode.E3005: "对账不一致-状态差异",
    ErrorCode.SYSTEM_ERROR: "系统内部错误",
    ErrorCode.NETWORK_ERROR: "网络异常",
    ErrorCode.AGENT_NOT_FOUND: "Agent未找到",
    ErrorCode.AGENT_TIMEOUT: "Agent执行超时",
    ErrorCode.AGENT_PERMISSION_DENIED: "Agent权限不足",
    ErrorCode.TOOL_NOT_FOUND: "工具未注册",
    ErrorCode.TOOL_EXECUTION_FAILED: "工具执行失败",
    ErrorCode.CIRCUIT_OPEN: "熔断器开启",
    ErrorCode.RATE_LIMITED: "请求被限流",
    ErrorCode.INVALID_INPUT: "输入参数无效",
    ErrorCode.INVALID_OUTPUT: "输出格式无效",
}


class OrderGuardianError(Exception):
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        self.error_code = error_code
        self.message = message
        self.extra = extra or {}
        super().__init__(f"[{error_code.value}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "description": ERROR_CODE_DESC.get(self.error_code, ""),
            "extra": self.extra
        }


class SystemError(OrderGuardianError):
    def __init__(self, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.SYSTEM_ERROR, message, extra)


class BusinessError(OrderGuardianError):
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)


class AgentError(OrderGuardianError):
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)


class ToolError(OrderGuardianError):
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)


class InputOutputError(OrderGuardianError):
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)
