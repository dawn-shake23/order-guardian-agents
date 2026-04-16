from typing import Dict, Set

class ToolACL:
    def __init__(self):
        # 工具访问控制：agent_type -> 允许的工具
        self.tool_access: Dict[str, Set[str]] = {
            "order": {
                "order_query",
                "order_analyze"
            },
            "payment": {
                "payment_query",
                "payment_analyze"
            },
            "risk": {
                "risk_assess",
                "risk_analyze"
            },
            "reconciliation": {
                "reconciliation_check",
                "reconciliation_analyze"
            },
            "operation": {
                "operation_analyze",
                "operation_recommend"
            }
        }
    
    def check_access(self, agent_type: str, tool_name: str) -> bool:
        """
        检查Agent是否有权限使用指定的工具
        """
        agent_tools = self.tool_access.get(agent_type, set())
        return tool_name in agent_tools
    
    def add_tool_access(self, agent_type: str, tool_name: str):
        """
        为Agent添加工具访问权限
        """
        if agent_type not in self.tool_access:
            self.tool_access[agent_type] = set()
        self.tool_access[agent_type].add(tool_name)
    
    def remove_tool_access(self, agent_type: str, tool_name: str):
        """
        为Agent移除工具访问权限
        """
        if agent_type in self.tool_access:
            self.tool_access[agent_type].discard(tool_name)