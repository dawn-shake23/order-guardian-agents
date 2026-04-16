from typing import Dict, Set

class ACLMatrix:
    def __init__(self):
        # 权限矩阵：agent_type -> 允许的操作
        self.permissions: Dict[str, Set[str]] = {
            "coordinator": {
                "plan:read",
                "step:schedule",
                "result:aggregate",
                "decision:make"
            },
            "plan": {
                "plan:create",
                "plan:rewrite",
                "plan:analyze"
            },
            "order": {
                "order:read",
                "order:analyze"
            },
            "payment": {
                "payment:read",
                "payment:analyze"
            },
            "risk": {
                "risk:assess",
                "risk:read"
            },
            "reconciliation": {
                "reconciliation:check",
                "reconciliation:analyze"
            },
            "operation": {
                "operation:analyze",
                "operation:recommend"
            }
        }
    
    def check_permission(self, agent_type: str, action: str) -> bool:
        """
        检查Agent是否有权限执行指定操作
        """
        agent_permissions = self.permissions.get(agent_type, set())
        return action in agent_permissions
    
    def add_permission(self, agent_type: str, action: str):
        """
        为Agent添加权限
        """
        if agent_type not in self.permissions:
            self.permissions[agent_type] = set()
        self.permissions[agent_type].add(action)
    
    def remove_permission(self, agent_type: str, action: str):
        """
        为Agent移除权限
        """
        if agent_type in self.permissions:
            self.permissions[agent_type].discard(action)