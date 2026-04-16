class StepValidator:
    @staticmethod
    def validate_output(expert_type: str, result: dict):
        if "success" not in result:
            raise ValueError(f"{expert_type} 必须返回 success 字段")