from typing import Dict

class PromptManager:
    def __init__(self):
        # 提示词管理：agent_type -> task_type -> prompt
        self.prompts: Dict[str, Dict[str, str]] = {
            "order": {
                "query": "你是订单专家，负责查询和分析订单基础信息。\n请根据提供的订单ID查询相关信息，并分析订单状态。",
                "analyze": "你是订单专家，负责分析订单异常。\n请根据订单信息分析可能的异常原因。"
            },
            "payment": {
                "query": "你是支付专家，负责核查支付渠道状态。\n请根据提供的订单ID查询支付状态。",
                "analyze": "你是支付专家，负责分析支付异常。\n请根据支付信息分析可能的异常原因。"
            },
            "risk": {
                "assess": "你是风险评估专家，负责评估订单风险。\n请根据订单和支付信息评估风险等级。",
                "analyze": "你是风险评估专家，负责分析风险原因。\n请根据风险评估结果分析可能的风险来源。"
            },
            "reconciliation": {
                "check": "你是对账专家，负责账实核对。\n请根据订单和支付信息进行账实核对。",
                "analyze": "你是对账专家，负责分析对账异常。\n请根据对账结果分析可能的异常原因。"
            },
            "operation": {
                "analyze": "你是运营专家，负责分析订单异常对运营的影响。\n请根据订单、支付和风险信息分析运营影响。",
                "recommend": "你是运营专家，负责给出运营建议。\n请根据订单异常情况给出合理的运营建议。"
            }
        }
    
    def get_prompt(self, agent_type: str, task_type: str) -> str:
        """
        获取Agent的提示词
        """
        agent_prompts = self.prompts.get(agent_type, {})
        return agent_prompts.get(task_type, f"你是{agent_type}专家，请完成{task_type}任务。")
    
    def set_prompt(self, agent_type: str, task_type: str, prompt: str):
        """
        设置Agent的提示词
        """
        if agent_type not in self.prompts:
            self.prompts[agent_type] = {}
        self.prompts[agent_type][task_type] = prompt