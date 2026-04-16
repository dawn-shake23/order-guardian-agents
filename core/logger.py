import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

class JsonFormatter(logging.Formatter):
    """JSON格式的日志格式化器"""
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # 添加额外的上下文信息
        if hasattr(record, "extra"):
            log_record.update(record.extra)
        
        # 处理异常信息
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        
        return json.dumps(log_record)

class Logger:
    """日志管理器"""
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(console_handler)
            
            # 创建文件处理器
            file_handler = logging.FileHandler("order-guardian.log")
            file_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(file_handler)
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录信息级别的日志"""
        extra = extra or {}
        self.logger.info(message, extra=extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: Optional[bool] = False):
        """记录错误级别的日志"""
        extra = extra or {}
        self.logger.error(message, extra=extra, exc_info=exc_info)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录警告级别的日志"""
        extra = extra or {}
        self.logger.warning(message, extra=extra)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录调试级别的日志"""
        extra = extra or {}
        self.logger.debug(message, extra=extra)

# 全局日志实例
def get_logger(name: str = "order-guardian") -> Logger:
    """获取日志实例"""
    return Logger(name)