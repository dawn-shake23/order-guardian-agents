import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

_initialized = False


def _setup_root_logger():
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger("order-guardian")
    root.setLevel(logging.DEBUG)

    # Console: WARNING+ only (no JSON noise in interactive mode)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(ch)

    # File: DEBUG+ with JSON format
    fh = logging.FileHandler("order-guardian.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        obj = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
        }
        if hasattr(record, "extra") and record.extra:
            obj["extra"] = record.extra
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


class Logger:
    def __init__(self, name: str):
        _setup_root_logger()
        self.logger = logging.getLogger(f"order-guardian.{name}")

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.info(message, extra={"extra": extra} if extra else {})

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        self.logger.error(message, extra={"extra": extra} if extra else {}, exc_info=exc_info)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.warning(message, extra={"extra": extra} if extra else {})

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.debug(message, extra={"extra": extra} if extra else {})


def get_logger(name: str = "order-guardian") -> Logger:
    return Logger(name)

os.makedirs("data", exist_ok=True)
os.makedirs("state_checkpoints", exist_ok=True)
