"""
RAG Pipeline v3: chunked KB + jieba preprocessing + rule intent + retrieval logging.

Full trace: input query -> jieba clean -> rule intent -> embedding ->
FAISS search chunked KB -> context assembly -> Agent reasoning -> output.
"""
import time
from typing import Any, Dict, List, Optional

import numpy as np

from config import RAGConfig
from core.logger import get_logger


class RetrievalLogger:
    """Print full retrieval trace: chunks, scores, rules, topK details."""

    def __init__(self):
        self.logger = get_logger("retrieval_logger")

    def log_search(self, query: str, domain: str, results: List[Dict],
                   duration_ms: float):
        print(f"\n{'='*60}")
        print(f"  Retrieval Trace")
        print(f"{'='*60}")
        print(f"  Query      : {query}")
        print(f"  Domain     : {domain}")
        print(f"  TopK       : {len(results)}")
        print(f"  Duration   : {duration_ms:.1f} ms")
        print(f"  {'─'*50}")
        for i, item in enumerate(results):
            meta = item.get("metadata", {})
            chunk_id = meta.get("chunk_id", meta.get("doc_id", "?"))
            title = meta.get("title", "")
            content = meta.get("content", "")[:120]
            score = item.get("score", 0)
            distance = item.get("distance", 0)
            print(f"  [{i+1}] {chunk_id} | L2={distance:.4f} | score={score:.4f}")
            print(f"       title: {title[:80]}")
            print(f"       text : {content}")
        print(f"  {'='*60}\n")
        self.logger.info("retrieval_trace", extra={
            "query": query, "domain": domain, "topK": len(results),
            "scores": [round(r.get("score", 0), 4) for r in results],
            "distances": [round(r.get("distance", 0), 4) for r in results],
        })

    def log_chunks(self, doc_id: str, chunks: List[str]):
        print(f"\n  [chunking] {doc_id}: {len(chunks)} chunks")
        for i, c in enumerate(chunks):
            print(f"    chunk[{i}]: {c[:100]}...")


class RAGPipeline:
    """Complete RAG pipeline with jieba + intent + chunked retrieval + logging."""

    def __init__(self, config: Optional[RAGConfig] = None,
                 hybrid_engine=None, embedding_provider=None,
                 preprocessor=None, intent_recognizer=None):
        self.config = config or RAGConfig()
        self.hybrid_engine = hybrid_engine
        self.embedding = embedding_provider
        self.preprocessor = preprocessor
        self.intent_recognizer = intent_recognizer
        self.logger_obj = RetrievalLogger()
        self.prompt_builder = RAGPromptBuilder()

    def process_query(self, query: str, top_k: Optional[int] = None,
                      biz_domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Full RAG pipeline for a single query.

        1. jieba clean
        2. rule intent recognition
        3. embed query
        4. FAISS search chunked KB
        5. log retrieval trace
        6. assemble context + build prompt
        """
        start_time = time.time()

        # Step 1: jieba preprocessing
        clean_query = query
        keywords: List[str] = []
        if self.preprocessor:
            keywords = self.preprocessor.extract_keywords(query)
            clean_query = self.preprocessor.clean(query)

        # Step 2: rule-based intent recognition
        domain = biz_domain
        intent_confidence = 1.0
        matched_rules: List[str] = []
        if self.intent_recognizer and not domain:
            domain, intent_confidence, matched_rules = \
                self.intent_recognizer.recognize_with_confidence(query)
        domain = domain or self.config.intent.default_domain

        # Step 3: embed query
        query_embedding: List[float] = []
        if self.embedding:
            query_embedding = self.embedding.encode(clean_query)
        else:
            query_embedding = np.random.rand(1024).tolist()

        # Step 4: FAISS search
        k = top_k or self.config.retrieval.top_k
        results: List[Dict] = []
        if self.hybrid_engine:
            results = self.hybrid_engine.search_with_filter(
                query_embedding=query_embedding,
                biz_domain=domain,
                top_k=k,
            )

        # Step 5: log full retrieval trace
        elapsed = (time.time() - start_time) * 1000
        if results:
            self.logger_obj.log_search(clean_query, domain, results, elapsed)

        # Step 6: assemble context + build prompt
        docs = self._to_docs(results)
        prompt = self.prompt_builder.build_prompt(docs, query)

        return {
            "query": query,
            "clean_query": clean_query,
            "keywords": keywords,
            "domain": domain,
            "intent_confidence": intent_confidence,
            "matched_rules": matched_rules,
            "results": results,
            "result_count": len(results),
            "system_prompt": prompt.get("system", ""),
            "user_prompt": prompt.get("user", ""),
            "duration_ms": round(elapsed, 2),
        }

    def _to_docs(self, results: List[Dict]) -> List:
        from tools.DeepSearch.rag_pipeline import RAGDocument
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


from prompts.manager import PromptManager
from prompts.security import PromptSanitizer, PromptSecurityConstants


class RAGDocument:
    """Document wrapper for RAG context."""
    def __init__(self, doc_id: str = "", title: str = "", content: str = "",
                 score: float = 0.0, biz_domain: str = "",
                 relevance_score: float = 0.0, is_noise: bool = False):
        self.doc_id = doc_id
        self.title = title
        self.content = content
        self.score = score
        self.biz_domain = biz_domain
        self.relevance_score = relevance_score
        self.is_noise = is_noise

    def model_dump(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id, "title": self.title,
            "content": self.content, "score": self.score,
            "biz_domain": self.biz_domain,
            "relevance_score": self.relevance_score,
            "is_noise": self.is_noise,
        }


class RAGPromptBuilder:
    """Structured prompt builder using PromptManager templates."""

    def __init__(self, prompt_manager=None):
        if prompt_manager is None:
            prompt_manager = PromptManager()
        self.pm = prompt_manager
        self.sanitizer = PromptSanitizer()

    def build_prompt(self, docs: List[RAGDocument], query: str,
                     extra_context: Optional[Dict] = None) -> Dict[str, str]:
        safe_query = self.sanitizer.sanitize(query, "user_query")
        context_parts = []
        reference_items = []
        for doc in docs:
            safe_content = self.sanitizer.sanitize(doc.content, f"doc_{doc.doc_id}")
            context_parts.append(f"[{doc.doc_id}] {doc.title}\n{safe_content}")
            reference_items.append(
                f"### [{doc.doc_id}] {doc.title}\n"
                f"- domain: {doc.biz_domain}\n"
                f"- relevance: {doc.relevance_score:.2f}\n"
                f"- content: {doc.content}"
            )

        context_text = "\n\n---\n\n".join(context_parts)
        reference_section = "\n\n".join(reference_items) if reference_items else "no references"

        system_prompt = self.pm.get_system_prompt()
        system_prompt = system_prompt.replace("{reference_section}", reference_section)
        system_prompt += PromptSecurityConstants.ANTI_INJECTION_INSTRUCTION

        user_prompt = self.pm.get_user_prompt(context=context_text, question=safe_query)
        if extra_context:
            lines = [f"- {k}: {v}" for k, v in extra_context.items()]
            user_prompt += "\n\ncontext:\n" + "\n".join(lines)

        return {"system": system_prompt, "user": user_prompt}
