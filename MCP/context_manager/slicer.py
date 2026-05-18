"""
Context Slicer — 上下文切片器（升级版）
借鉴 Java KnowledgeBaseQueryService 的上下文管理：
1. 按 agent_type 字段级权限裁剪
2. Token 感知的动态截断
3. 多轮对话历史注入
"""
from typing import Dict, Any, List, Optional
from core.logger import get_logger


class ContextSlicer:
    """
    上下文切片器
    借鉴 Java ContextSlicer 的字段级访问控制 + Token 感知截断
    """

    # 每个 agent_type 允许访问的字段
    CONTEXT_ACCESS: Dict[str, set] = {
        "order": {"session_id", "order_id", "intent", "order_info", "chat_history"},
        "payment": {"session_id", "order_id", "payment_info", "chat_history"},
        "risk": {"session_id", "order_id", "order_info", "payment_info", "risk_info", "chat_history"},
        "reconciliation": {"session_id", "order_id", "order_info", "payment_info", "reconciliation_info", "chat_history"},
        "operation": {"session_id", "order_id", "order_info", "payment_info", "risk_info", "reconciliation_info", "chat_history"},
        "plan": {"session_id", "order_id", "intent", "global_analysis", "data_requirements", "chat_history"},
        "coordinator": {"session_id", "order_id", "intent", "global_analysis",
                         "order_info", "payment_info", "risk_info", "reconciliation_info", "chat_history"},
    }

    # 每个 agent 的 token 上限
    MAX_TOKENS_PER_AGENT: Dict[str, int] = {
        "order": 2000,
        "payment": 2000,
        "risk": 3000,
        "reconciliation": 3000,
        "operation": 4000,
        "plan": 4000,
        "coordinator": 6000,
    }

    def __init__(self):
        self.logger = get_logger("context_slicer")

    def slice(self, agent_type: str, full_context: Dict[str, Any],
              max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        上下文切片：字段裁剪 + Token 截断
        """
        allowed = self.CONTEXT_ACCESS.get(agent_type, set())
        sliced = {}

        for key, value in full_context.items():
            if key in allowed:
                sliced[key] = self._trim_value(key, value, agent_type)

        # Token 级别的动态截断
        token_limit = max_tokens or self.MAX_TOKENS_PER_AGENT.get(agent_type, 2000)
        total_tokens = self._estimate_context_tokens(sliced)

        if total_tokens > token_limit:
            self.logger.info("上下文超限，执行截断", extra={
                "agent_type": agent_type,
                "total_tokens": total_tokens,
                "limit": token_limit
            })
            sliced = self._trim_by_token_budget(sliced, token_limit)

        self.logger.debug("上下文切片完成", extra={
            "agent_type": agent_type,
            "fields": list(sliced.keys()),
            "tokens": self._estimate_context_tokens(sliced)
        })

        return sliced

    def _trim_value(self, key: str, value: Any, agent_type: str) -> Any:
        """按字段类型修剪值"""
        if isinstance(value, str) and len(value) > 8000:
            return value[:8000] + "..."
        if isinstance(value, dict):
            return {k: self._trim_value(k, v, agent_type) for k, v in value.items()}
        if isinstance(value, list) and len(value) > 20:
            return value[:20]
        return value

    def _trim_by_token_budget(self, context: Dict[str, Any], limit: int) -> Dict[str, Any]:
        """按 token 预算裁剪上下文，优先保留关键字段"""
        priority_order = [
            "session_id", "order_id", "intent", "global_analysis",
            "order_info", "payment_info", "risk_info", "reconciliation_info",
            "chat_history", "data_requirements"
        ]

        result = {}
        used = 0
        for key in priority_order:
            if key not in context:
                continue
            value = context[key]
            tokens = self._estimate_tokens(str(value))
            remaining = limit - used

            if tokens <= remaining:
                result[key] = value
                used += tokens
            elif remaining > 50:
                if isinstance(value, str):
                    result[key] = value[:remaining * 2] + "..."
                elif isinstance(value, list):
                    result[key] = value[:max(1, remaining // 10)]
                used = limit
                break
            else:
                break

        return result

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Token 估算（中文≈字符数，英文≈词数*1.3）"""
        import re
        chinese = len(re.findall(r'[一-鿿]', text))
        english = len(re.findall(r'[a-zA-Z0-9]+', text))
        return chinese + int(english * 1.3)

    def _estimate_context_tokens(self, context: Dict[str, Any]) -> int:
        return self._estimate_tokens(str(context))
