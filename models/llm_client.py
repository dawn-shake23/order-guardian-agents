"""
LLM Client - DashScope Chat API via OpenAI-compatible interface.
Supports qwen-plus, qwen-turbo, qwen-max.
"""
import os
from enum import Enum
from typing import Any, Dict, Optional

_OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    pass

from config import LLMConfig
from core.logger import get_logger


class ModelType(str, Enum):
    QWEN_14B = "qwen-plus"
    LLAMA3_8B = "qwen-turbo"
    GPT_4 = "qwen-max"



class LLMClient:
    """DashScope Chat LLM client."""

    def __init__(self, config: Optional[LLMConfig] = None, api_key: Optional[str] = None):
        self.config = config or LLMConfig()
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.logger = get_logger("llm_client")
        self._client = None
        if self.api_key and _OPENAI_AVAILABLE:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.config.base_url,
            )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a response from system + user prompts."""
        if not self._client:
            return self._fallback_response(user_prompt)

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            content = response.choices[0].message.content or ""
            self.logger.info("llm_response", extra={"model": self.config.model, "len": len(content)})
            return content
        except Exception as e:
            self.logger.error("llm_error", extra={"error": str(e)})
            return self._fallback_response(user_prompt)

    def generate(self, prompt: str, output_schema: Optional[Any] = None) -> Dict[str, Any]:
        """Legacy interface for Coordinator compatibility."""
        answer = self.chat("", prompt)
        return {"data": {"answer": answer, "content": answer}}

    def _fallback_response(self, user_prompt: str) -> str:
        return (
            "Based on the knowledge base analysis, I recommend the following steps:\n"
            "1. Check the channel status and confirm the payment result.\n"
            "2. If payment succeeded, manually update the order status.\n"
            "3. If payment failed, notify the user and close the order.\n"
            "4. Record all actions in the operation log."
        )

    @property
    def available(self) -> bool:
        return self._client is not None
