from typing import Dict, Any

class StepValidator:
    def __init__(self):
        # 有效的专家类型
        self.valid_expert_types = {
            "order",
            "payment",
            "risk",
            "reconciliation",
            "operation"
        }
    
    def validate(self, step: Dict[str, Any]) -> bool:
        """
        验证步骤是否合法
        """
        # 检查必要字段
        required_fields = ["step_id", "expert_type", "goal"]
        for field in required_fields:
            if field not in step:
                return False
        
        # 检查step_id是否为正整数
        if not isinstance(step.get("step_id"), int) or step.get("step_id") <= 0:
            return False
        
        # 检查expert_type是否有效
        if step.get("expert_type") not in self.valid_expert_types:
            return False
        
        # 检查goal是否为非空字符串
        if not isinstance(step.get("goal"), str) or not step.get("goal").strip():
            return False
        
        # 检查depends_on是否为整数列表
        depends_on = step.get("depends_on", [])
        if not isinstance(depends_on, list):
            return False
        for dep in depends_on:
            if not isinstance(dep, int) or dep <= 0:
                return False
        
        return True