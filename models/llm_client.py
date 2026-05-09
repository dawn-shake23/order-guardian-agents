from enum import Enum
from typing import Dict, Any, Optional

from langsmith.run_helpers import trace as _langsmith_trace


class ModelType(Enum):
    QWEN_14B = "qwen14b"
    LLAMA3_8B = "llama3_8b"
    GPT_4 = "gpt4"


class LLMClient:
    def __init__(self, model_type: ModelType = ModelType.QWEN_14B):
        self.model_type = model_type
        # 实际项目中这里应该初始化真实的LLM客户端

    def generate(
        self,
        prompt: str,
        output_schema: Optional[Any] = None,
        *,
        trace_metadata: Optional[Dict[str, Any]] = None,
        trace_tags: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        生成LLM响应，自动创建 LangSmith Span。

        实际项目中这里应该调用真实的LLM API。
        接入真实 API 后，推荐使用 langsmith.wrap_openai() 等原生封装。
        """
        with _langsmith_trace(
            name=f"llm:{self.model_type.value}",
            run_type="llm",
            inputs={"prompt": prompt, "output_schema": str(output_schema)},
            metadata={
                "model": self.model_type.value,
                "model_type": self.model_type.name,
                **(trace_metadata or {}),
            },
            tags=trace_tags or ["llm", self.model_type.value],
        ) as run:
            # ---- LLM 调用 ----
            # 模拟LLM响应（生产环境替换为真实 API 调用）
            mock_response = {
                "data": {
                    "session_id": "test_session",
                    "order_id": "test_order",
                    "plan_success": True,
                    "abnormal_root_cause": "模拟根因分析",
                    "solution": "模拟解决方案",
                    "risk_level": "low",
                    "expert_steps": [],
                    "final_summary": "模拟总结",
                }
            }

            if output_schema:
                # 生产环境：根据 output_schema 做校验和转换
                pass

            run.end(outputs=mock_response)
            return mock_response
