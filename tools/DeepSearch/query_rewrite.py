"""
Query Rewrite Service — 查询改写服务
借鉴 Java KnowledgeBaseQueryService.rewriteQuestion()：
1. LLM将用户原始问题改写为更适合检索的单句查询
2. 支持对话历史上下文（处理追问/指代消解）
3. 改写失败时回退到原问题
4. 可配置开关
5. 从 prompts/rewrite.st 加载模板
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from core.logger import get_logger


@dataclass
class RewriteConfig:
    """改写配置 — 借鉴 KnowledgeBaseQueryProperties.Rewrite"""
    enabled: bool = True
    max_history_chars: int = 200
    max_rewrite_attempts: int = 1


class QueryRewriteService:
    """
    查询改写服务
    借鉴 Java KnowledgeBaseQueryService.rewriteQuestion()
    """

    def __init__(self, config: Optional[RewriteConfig] = None, llm_client=None,
                 prompt_manager=None):
        self.config = config or RewriteConfig()
        self.llm = llm_client
        if prompt_manager is None:
            from prompts.manager import PromptManager
            prompt_manager = PromptManager()
        self.pm = prompt_manager
        self.logger = get_logger("query_rewrite")

    def rewrite(self, question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        改写用户查询
        返回改写后的查询，失败时返回原问题
        """
        if not self.config.enabled or not question or not question.strip():
            return question

        question = question.strip()

        # 短查询不需要改写
        compact = question.replace(" ", "")
        if len(compact) <= 2:
            return question

        try:
            history_text = self._format_history(history)
            prompt = self.pm.get_rewrite_prompt(question=question, history=history_text)

            # 使用LLM改写
            rewritten = self._call_llm(prompt)

            if rewritten and rewritten.strip():
                result = rewritten.strip()
                self.logger.info("查询改写成功", extra={
                    "original": question[:80],
                    "rewritten": result[:80],
                    "has_history": bool(history_text)
                })
                return result

        except Exception as e:
            self.logger.warning("查询改写失败，使用原问题", extra={"error": str(e)})

        return question

    def _format_history(self, history: Optional[List[Dict[str, str]]]) -> str:
        """格式化对话历史 — 借鉴 formatHistoryForRewrite()"""
        if not history:
            return ""

        lines = []
        total_chars = 0
        for msg in reversed(history):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                prefix = "用户: "
            elif role == "assistant":
                prefix = "助手: "
            else:
                continue

            if len(content) > self.config.max_history_chars:
                content = content[:self.config.max_history_chars] + "..."

            line = prefix + content
            total_chars += len(line)
            if total_chars > self.config.max_history_chars * 3:
                break

            lines.append(line)

        lines.reverse()
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用LLM进行改写"""
        if self.llm is None:
            return self._rule_based_rewrite(prompt)

        try:
            result = self.llm.generate(prompt)
            if isinstance(result, dict):
                return result.get("data", {}).get("rewritten_query") or result.get("content", "")
            if isinstance(result, str):
                return result
        except Exception:
            pass

        return self._rule_based_rewrite(prompt)

    def _rule_based_rewrite(self, prompt: str) -> Optional[str]:
        """基于规则的改写（无LLM时的回退方案）"""
        import re
        match = re.search(r'用户原始问题：[^\n]*\n([^\n]+)', prompt)
        if match:
            question = match.group(1).strip()
            question = re.sub(r'^(请问|我想知道|帮我查一下|帮我看看|请告诉我)\s*', '', question)
            return question
        return None


class CandidateQueryGenerator:
    """
    候选查询生成器 — 借鉴 Java 的 LinkedHashSet<candidates> 级联回退模式
    生成多个候选查询，按优先级排序：LLM改写 → 原始查询 → 关键词变体
    """

    def __init__(self, rewrite_service: Optional[QueryRewriteService] = None):
        self.rewrite_service = rewrite_service
        self.logger = get_logger("candidate_query")

    def generate(self, question: str, history: Optional[List[Dict]] = None) -> List[str]:
        """
        生成候选查询列表（去重，保持优先级顺序）
        借鉴 Java: Set<String> candidates = new LinkedHashSet<>()
        """
        seen = set()
        candidates = []

        def add(candidate: str):
            c = candidate.strip()
            if c and c not in seen:
                seen.add(c)
                candidates.append(c)

        # 候选1: LLM改写查询
        if self.rewrite_service:
            rewritten = self.rewrite_service.rewrite(question, history)
            if rewritten != question:
                add(rewritten)

        # 候选2: 原始查询
        add(question)

        # 候选3: 关键词变体
        keywords_variant = self._extract_keyword_variant(question)
        if keywords_variant:
            add(keywords_variant)

        self.logger.info("候选查询生成完成", extra={
            "candidates": len(candidates),
            "queries": [c[:60] for c in candidates]
        })

        return candidates

    def _extract_keyword_variant(self, question: str) -> Optional[str]:
        """提取核心关键词作为备选查询"""
        import re
        stopwords = {'的', '了', '是', '在', '和', '有', '我', '怎么', '什么', '如何', '为什么', '请问'}
        tokens = re.findall(r'[\w一-鿿]+', question)
        keywords = [t for t in tokens if t.lower() not in stopwords and len(t) >= 2]
        if len(keywords) >= 2:
            return " ".join(keywords[:5])
        return None
