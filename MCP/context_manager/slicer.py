from typing import Dict, Any

class ContextSlicer:
    def __init__(self):
        # 上下文访问控制：agent_type -> 允许访问的字段
        self.context_access: Dict[str, set] = {
            "order": {
                "session_id",
                "order_id",
                "intent",
                "order_info"
            },
            "payment": {
                "session_id",
                "order_id",
                "payment_info"
            },
            "risk": {
                "session_id",
                "order_id",
                "order_info",
                "payment_info",
                "risk_info"
            },
            "reconciliation": {
                "session_id",
                "order_id",
                "order_info",
                "payment_info",
                "reconciliation_info"
            },
            "operation": {
                "session_id",
                "order_id",
                "order_info",
                "payment_info",
                "risk_info",
                "reconciliation_info"
            }
        }
    
    def slice(self, agent_type: str, full_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        上下文切片，只返回Agent有权访问的内容
        """
        allowed_fields = self.context_access.get(agent_type, set())
        sliced_context = {}
        
        for key, value in full_context.items():
            if key in allowed_fields:
                sliced_context[key] = value
        
        return sliced_context