"""
Query Rewrite Service — 查询改写服务
借鉴 Java KnowledgeBaseQueryService.rewriteQuestion()：
1. LLM将用户原始问题改写为更适合检索的单句查询
2. 支持对话历史上下文（处理追问/指代消解）
3. 改写失败时回退到原问题
4. 可配置开关
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from core.logger import get_logger


@dataclass
class RewriteConfig:
    """改写配置 — 借鉴 KnowledgeBaseQueryProperties.Rewrite"""
    enabled: bool = True
    max_history_chars: int = 200       # 历史上下文最大字符数
    max_rewrite_attempts: int = 1      # 改写重试次数


REWRITE_PROMPT_TEMPLATE = """你是一个检索查询改写助手。你的任务是把用户原始问题改写成更适合知识库检索的单句查询。

要求：
1. 保留用户核心意图，不引入原问题没有的事实
2. 对过短、过泛的问题补充必要语义，使其更可检索
3. 输出必须是单行纯文本，不要 Markdown，不要解释
4. 如果原问题已经足够具体，原样输出
5. 如果存在对话历史，结合上下文理解用户的追问意图
6. 对于中文查询，确保关键词明确且区分度足够

用户原始问题：
{question}
{history}"""


class QueryRewriteService:
    """
    查询改写服务
    借鉴 Java KnowledgeBaseQueryService.rewriteQuestion()
    """

    def __init__(self, config: Optional[RewriteConfig] = None, llm_client=None):
        self.config = config or RewriteConfig()
        self.llm = llm_client
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
            prompt = REWRITE_PROMPT_TEMPLATE.format(
                question=question,
                history=f"\n对话历史：\n{history_text}" if history_text else ""
            )

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
        for msg in reversed(history):  # 从最近的开始
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                prefix = "用户: "
            elif role == "assistant":
                prefix = "助手: "
            else:
                continue

            # 截断过长的回复
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
        """
        基于规则的改写（无LLM时的回退方案）
        从 prompt 中提取原问题作为 baseline
        """
        import re
        match = re.search(r'用户原始问题：\s*\n\s*(.+?)(?:\n|$)', prompt)
        if match:
            question = match.group(1).strip()
            # 基础处理：去除无意义的前缀
            question = re.sub(r'^(请问|我想知道|帮我查一下|帮我看看|请告诉我)\s*', '', question)
            return question
        return None


class CandidateQueryGenerator:
    """
    候选查询生成器 — 借鉴 Java 的 LinkedHashSet<候选查询> 级联回退模式
    生成多个候选查询，按优先级排序：
    1. LLM改写后的查询
    2. 原始查询
    3. 关键词提取变体
    """

    def __init__(self, rewrite_service: Optional[QueryRewriteService] = None):
        self.rewrite_service = rewrite_service
        self.logger = get_logger("candidate_query")

    def generate(self, question: str, history: Optional[List[Dict]] = None) -> List[str]:
        """
        生成候选查询列表（已去重，保持优先级顺序）
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

        # 候选3: 关键词变体（从原始查询中提取核心关键词组合）
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
        # 移除常见停用词
        stopwords = {'的', '了', '是', '在', '和', '有', '我', '怎么', '什么', '如何', '为什么', '请问'}
        tokens = re.findall(r'[\w一-鿿]+', question)
        keywords = [t for t in tokens if t.lower() not in stopwords and len(t) >= 2]
        if len(keywords) >= 2:
            return " ".join(keywords[:5])
        return None
