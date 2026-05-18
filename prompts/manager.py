"""
Prompt Manager — 模板加载、缓存与渲染
借鉴 Java KnowledgeBaseQueryService 中从文件加载 prompt 的模式
"""
import os
from typing import Dict, Optional
from core.logger import get_logger


# 默认模板目录
PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


class PromptManager:
    """
    统一 Prompt 管理器
    借鉴 Java 通过 ResourceLoader 加载 classpath:prompts/*.st 的模式
    """

    def __init__(self, prompts_dir: Optional[str] = None):
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self._cache: Dict[str, str] = {}
        self.logger = get_logger("prompt_manager")

    def get_system_prompt(self, extra_instructions: Optional[str] = None) -> str:
        """获取系统提示词"""
        template = self._load("system.st")
        if extra_instructions:
            template += f"\n\n# Additional Instructions\n{extra_instructions}"
        from prompts.security import PromptSecurityConstants
        template += PromptSecurityConstants.ANTI_INJECTION_INSTRUCTION
        return template

    def get_user_prompt(self, context: str, question: str) -> str:
        """获取用户提示词，注入上下文和问题"""
        template = self._load("user.st")
        return template.format(context=context, question=question)

    def get_rewrite_prompt(self, question: str, history: str = "") -> str:
        """获取查询改写提示词"""
        template = self._load("rewrite.st")
        history_section = f"\n对话历史：\n{history}" if history else ""
        return template.format(question=question, history=history_section)

    def render(self, template_name: str, variables: Optional[Dict[str, str]] = None) -> str:
        """通用模板渲染"""
        template = self._load(template_name)
        if variables:
            return template.format(**variables)
        return template

    def _load(self, name: str) -> str:
        """加载模板文件（带缓存）"""
        if name in self._cache:
            return self._cache[name]

        filepath = os.path.join(self.prompts_dir, name)
        if not os.path.exists(filepath):
            self.logger.error("模板文件不存在", extra={"path": filepath})
            return ""

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        self._cache[name] = content
        self.logger.debug("模板加载完成", extra={"name": name, "size": len(content)})
        return content

    def reload(self, name: Optional[str] = None):
        """重新加载模板（热更新）"""
        if name:
            self._cache.pop(name, None)
            self._load(name)
        else:
            self._cache.clear()
        self.logger.info("模板缓存已刷新", extra={"name": name or "all"})

    def list_templates(self) -> list:
        """列出所有可用模板"""
        templates = []
        if os.path.isdir(self.prompts_dir):
            for f in os.listdir(self.prompts_dir):
                if f.endswith('.st'):
                    templates.append(f)
        return sorted(templates)
