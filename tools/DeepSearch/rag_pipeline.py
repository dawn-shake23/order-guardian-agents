import re
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from core.logger import get_logger


class RAGDocument(BaseModel):
    doc_id: str
    title: str
    content: str
    score: float
    biz_domain: str = ""
    relevance_score: float = Field(default=0.0, description="相关性评分 0-1")
    is_noise: bool = Field(default=False, description="是否为噪声")


class ContextWindow:
    """
    上下文窗口管理
    解决：召回内容太多塞满上下文的问题
    策略：动态截断 + 关键信息抽取 + 优先级排序
    """

    def __init__(self, max_tokens: int = 4000, reserved_for_prompt: int = 1000):
        self.max_tokens = max_tokens
        self.reserved_for_prompt = reserved_for_prompt
        self.available_tokens = max_tokens - reserved_for_prompt

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 2 + len(re.findall(r'[\u4e00-\u9fff]', text))

    def compress_documents(self, docs: List[RAGDocument], query: str) -> List[RAGDocument]:
        """
        动态截断策略：
        1. 按相关性排序
        2. 逐条加入，超窗口时截断内容
        3. 保留标题和关键句
        """
        sorted_docs = sorted(docs, key=lambda d: d.relevance_score, reverse=True)
        used_tokens = 0
        result = []

        for doc in sorted_docs:
            full_tokens = self.estimate_tokens(doc.content)
            remaining = self.available_tokens - used_tokens

            if remaining <= 0:
                break

            if full_tokens <= remaining:
                result.append(doc)
                used_tokens += full_tokens
            else:
                compressed = self._extract_key_sentences(doc.content, query, remaining)
                doc.content = compressed
                result.append(doc)
                used_tokens += self.estimate_tokens(compressed)
                break

        return result

    def _extract_key_sentences(self, content: str, query: str, max_tokens: int) -> str:
        """
        关键信息抽取：提取与query最相关的句子
        """
        sentences = re.split(r'[。！？\n]', content)
        query_words = set(re.findall(r'[\w]+', query.lower()))

        scored_sentences = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_words = set(re.findall(r'[\w]+', sent.lower()))
            overlap = len(query_words & sent_words)
            scored_sentences.append((sent, overlap))

        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        result = []
        used = 0
        for sent, _ in scored_sentences:
            tokens = self.estimate_tokens(sent)
            if used + tokens > max_tokens:
                break
            result.append(sent)
            used += tokens

        return "。".join(result) + "。"


class NoiseFilter:
    """
    噪声过滤器
    解决：检索结果噪声大，LLM会被带偏
    策略：相关性校验 + 置信度阈值 + 业务域匹配
    """

    def __init__(self, relevance_threshold: float = 0.1, domain_match_bonus: float = 0.3):
        self.relevance_threshold = relevance_threshold
        self.domain_match_bonus = domain_match_bonus
        self.logger = get_logger("noise_filter")

    def _char_ngrams(self, text: str, n: int = 2) -> set:
        chars = re.sub(r'\s+', '', text.lower())
        if len(chars) < n:
            return {chars}
        return {chars[i:i+n] for i in range(len(chars) - n + 1)}

    def filter(self, docs: List[RAGDocument], query: str, biz_domain: Optional[str] = None) -> List[RAGDocument]:
        """
        过滤噪声文档：
        1. 计算相关性分数（基于字符n-gram重叠）
        2. 低于阈值的标记为噪声
        3. 业务域匹配加分
        """
        query_ngrams = self._char_ngrams(query)
        filtered = []

        for doc in docs:
            content_ngrams = self._char_ngrams(doc.title + " " + doc.content)
            if not query_ngrams or not content_ngrams:
                overlap = 0.0
            else:
                overlap = len(query_ngrams & content_ngrams) / max(len(query_ngrams), 1)

            relevance = overlap

            if biz_domain and doc.biz_domain == biz_domain:
                relevance += self.domain_match_bonus

            if doc.score > 0.5:
                relevance += 0.2

            doc.relevance_score = min(relevance, 1.0)
            doc.is_noise = relevance < self.relevance_threshold

            if not doc.is_noise:
                filtered.append(doc)
            else:
                self.logger.info("过滤噪声文档", extra={
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "relevance": relevance,
                    "threshold": self.relevance_threshold
                })

        self.logger.info("噪声过滤完成", extra={
            "input_count": len(docs),
            "output_count": len(filtered),
            "filtered_count": len(docs) - len(filtered)
        })
        return filtered


class RAGPromptBuilder:
    """
    结构化Prompt构造器
    解决：怎么把检索结果结构化塞进提示词
    策略：明确区分"参考资料"和"对话内容"，结构化注入
    """

    SYSTEM_TEMPLATE = """你是一个订单异常诊断专家。以下【参考资料】来自知识库检索，仅供参考，不是对话内容。

## 参考资料
{reference_section}

## 指令
- 基于参考资料中的信息回答问题
- 如果参考资料不足以回答，请明确说明
- 不要编造参考资料中没有的信息
- 引用参考资料时标注来源 [来源: doc_id]
"""

    REFERENCE_ITEM_TEMPLATE = """### [{doc_id}] {title}
- 业务域: {biz_domain}
- 相关性: {relevance:.2f}
- 内容: {content}"""

    def build_prompt(self, docs: List[RAGDocument], query: str, extra_context: Optional[Dict] = None) -> str:
        """
        构建结构化RAG Prompt
        """
        reference_items = []
        for doc in docs:
            reference_items.append(self.REFERENCE_ITEM_TEMPLATE.format(
                doc_id=doc.doc_id,
                title=doc.title,
                biz_domain=doc.biz_domain,
                relevance=doc.relevance_score,
                content=doc.content
            ))

        reference_section = "\n\n".join(reference_items) if reference_items else "无相关参考资料"

        system_prompt = self.SYSTEM_TEMPLATE.format(reference_section=reference_section)

        user_prompt = f"问题: {query}"
        if extra_context:
            context_lines = [f"- {k}: {v}" for k, v in extra_context.items()]
            user_prompt += f"\n\n额外上下文:\n" + "\n".join(context_lines)

        return f"{system_prompt}\n\n{user_prompt}"


class RAGPipeline:
    """
    RAG完整流水线
    检索 → 噪声过滤 → 上下文压缩 → 结构化Prompt注入
    """

    def __init__(self, max_context_tokens: int = 4000):
        self.context_window = ContextWindow(max_tokens=max_context_tokens)
        self.noise_filter = NoiseFilter()
        self.prompt_builder = RAGPromptBuilder()
        self.logger = get_logger("rag_pipeline")

    def process(
        self,
        search_results: List[Dict[str, Any]],
        query: str,
        biz_domain: Optional[str] = None,
        extra_context: Optional[Dict] = None,
    ) -> str:
        """
        完整RAG处理流程
        """
        # Step 1: 转换为RAGDocument
        docs = self._to_rag_documents(search_results)

        self.logger.info("RAG流水线开始", extra={
            "input_docs": len(docs),
            "query": query,
            "biz_domain": biz_domain
        })

        # Step 2: 噪声过滤
        filtered = self.noise_filter.filter(docs, query, biz_domain)

        # Step 3: 上下文压缩
        compressed = self.context_window.compress_documents(filtered, query)

        # Step 4: 构建结构化Prompt
        prompt = self.prompt_builder.build_prompt(compressed, query, extra_context)

        self.logger.info("RAG流水线完成", extra={
            "filtered_docs": len(filtered),
            "compressed_docs": len(compressed),
            "prompt_length": len(prompt)
        })

        return prompt

    def _to_rag_documents(self, results: List[Dict[str, Any]]) -> List[RAGDocument]:
        docs = []
        for r in results:
            meta = r.get("metadata", r)
            docs.append(RAGDocument(
                doc_id=meta.get("doc_id", meta.get("id", "")),
                title=meta.get("title", ""),
                content=meta.get("content", ""),
                score=r.get("score", r.get("distance", 0)),
                biz_domain=meta.get("biz_domain", ""),
            ))
        return docs
