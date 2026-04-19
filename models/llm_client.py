from enum import Enum
from typing import Dict, Any, Optional
import json

class ModelType(Enum):
    QWEN_14B = "qwen14b"
    LLAMA3_8B = "llama3_8b"
    GPT_4 = "gpt4"

class LLMClient:
    def __init__(self, model_type: ModelType = ModelType.QWEN_14B):
        self.model_type = model_type

    def generate(self, prompt: str, output_schema: Optional[Any] = None) -> Dict[str, Any]:
        mock_response = {
            "data": {
                "abnormal_root_cause": "支付渠道回调延迟，导致订单状态与支付状态不一致",
                "solution": "1. 联系支付渠道确认回调状态；2. 如确认支付成功，手动更新订单状态；3. 建议增加回调超时补偿机制",
                "risk_level": "low",
                "final_summary": "订单支付状态待确认，经多专家协同诊断，根因为支付渠道回调延迟，建议增加补偿机制"
            }
        }
        
        if output_schema:
            pass
        
        return mock_response
