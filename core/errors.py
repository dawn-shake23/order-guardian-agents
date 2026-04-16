from enum import Enum
from typing import Optional, Dict, Any

class ErrorCode(Enum):
    """错误码枚举"""
    # 系统级错误
    SYSTEM_ERROR = "SYSTEM_ERROR"  # 系统错误
    NETWORK_ERROR = "NETWORK_ERROR"  # 网络错误
    DATABASE_ERROR = "DATABASE_ERROR"  # 数据库错误
    
    # 业务级错误
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"  # 订单不存在
    PAYMENT_FAILED = "PAYMENT_FAILED"  # 支付失败
    RISK_CHECK_FAILED = "RISK_CHECK_FAILED"  # 风险检查失败
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"  # 对账失败
    
    # Agent相关错误
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"  # Agent不存在
    AGENT_TIMEOUT = "AGENT_TIMEOUT"  # Agent超时
    AGENT_PERMISSION_DENIED = "AGENT_PERMISSION_DENIED"  # Agent权限不足
    
    # 工具相关错误
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"  # 工具不存在
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"  # 工具执行失败
    
    # 输入输出错误
    INVALID_INPUT = "INVALID_INPUT"  # 无效输入
    INVALID_OUTPUT = "INVALID_OUTPUT"  # 无效输出

class OrderGuardianError(Exception):
    """OrderGuardian基础异常类"""
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        self.error_code = error_code
        self.message = message
        self.extra = extra or {}
        super().__init__(f"{error_code.value}: {message}")

class SystemError(OrderGuardianError):
    """系统错误"""
    def __init__(self, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.SYSTEM_ERROR, message, extra)

class BusinessError(OrderGuardianError):
    """业务错误"""
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)

class AgentError(OrderGuardianError):
    """Agent错误"""
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)

class ToolError(OrderGuardianError):
    """工具错误"""
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)

class InputOutputError(OrderGuardianError):
    """输入输出错误"""
    def __init__(self, error_code: ErrorCode, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, extra)