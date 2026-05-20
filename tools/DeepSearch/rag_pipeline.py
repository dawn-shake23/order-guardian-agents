"""
RAG Pipeline: preprocessing -> intent -> embed -> FAISS search -> context -> LLM answer.
Full retrieval trace logging: chunk count, content, L2 scores, hit rules.
"""
import time
from typing import Any, Dict, List, Optional

import numpy as np

from config import SystemConfig
from core.logger import get_logger


class RetrievalLogger:
    """Print full retrieval trace for every query."""

    def __init__(self):
        self.logger = get_logger("retrieval_logger")

    def log_search(self, query: str, domain: str, results: List[Dict], duration_ms: float):
        print(f"\n{'='*60}")
        print(f"  RAG Retrieval Trace")
        print(f"{'='*60}")
        print(f"  query     : {query}")
        print(f"  domain    : {domain}")
        print(f"  topK      : {len(results)}")
        print(f"  duration  : {duration_ms:.1f} ms")
        print(f"  vector cnt: {self._vec_count}")
        print(f"  {'-'*50}")
        for i, item in enumerate(results):
            meta = item.get("metadata", {})
            cid = meta.get("chunk_id", meta.get("doc_id", "?"))
            title = meta.get("title", "")
            text = meta.get("content", "")[:150]
            score = item.get("score", 0)
            dist = item.get("distance", 0)
            print(f"  [{i+1}] {cid}")
            print(f"       L2={dist:.4f}  score={score:.4f}")
            print(f"       title: {title[:80]}")
            print(f"       text : {text}")
        print(f"  {'='*60}\n")

    def log_chunking(self, doc_id: str, chunk_count: int, chunk_size: int):
        print(f"  [chunking] {doc_id}: {chunk_count} chunks (size={chunk_size})")

    def set_vector_count(self, n: int):
        self._vec_count = n


class RAGPipeline:
    """
    Full RAG pipeline:
      user input -> jieba clean -> rule intent -> embed ->
      FAISS search -> context assembly -> LLM answer generation.
    """

    def __init__(self, config: Optional[SystemConfig] = None,
                 hybrid_engine=None, embedding_provider=None,
                 llm_client=None, preprocessor=None, intent_recognizer=None):
        self.cfg = config or SystemConfig()
        self.hybrid_engine = hybrid_engine
        self.embedding = embedding_provider
        self.llm = llm_client
        self.preprocessor = preprocessor
        self.intent_recognizer = intent_recognizer
        self.logger = RetrievalLogger()
        self.prompt_builder = RAGPromptBuilder()

    def process_query(self, query: str, top_k: Optional[int] = None,
                      biz_domain: Optional[str] = None) -> Dict[str, Any]:
        """Execute the complete RAG pipeline end-to-end."""
        start_time = time.time()

        # 1. jieba preprocessing
        clean_query = query
        keywords: List[str] = []
        if self.preprocessor:
            keywords = self.preprocessor.extract_keywords(query)
            clean_query = self.preprocessor.clean(query)

        # 2. rule-based intent recognition
        domain = biz_domain
        confidence = 1.0
        matched_rules: List[str] = []
        if self.intent_recognizer and not domain:
            domain, confidence, matched_rules = self.intent_recognizer.recognize_with_confidence(query)
        domain = domain or self.cfg.intent.default_domain

        # 3. embed query
        if self.embedding:
            query_embedding = self.embedding.encode(clean_query)
        else:
            query_embedding = np.random.rand(self.cfg.embedding.dim).tolist()

        # 4. FAISS search
        k = top_k or self.cfg.retrieval.top_k
        results: List[Dict] = []
        if self.hybrid_engine:
            results = self.hybrid_engine.search_with_filter(
                query_embedding=query_embedding, biz_domain=domain, top_k=k,
            )

        # 5. log retrieval trace
        elapsed = (time.time() - start_time) * 1000
        if hasattr(self.hybrid_engine, 'vector_store'):
            self.logger.set_vector_count(len(self.hybrid_engine.vector_store))
        if results:
            self.logger.log_search(clean_query, domain, results, elapsed)

        # 6. context assembly
        context_parts = []
        for r in results:
            meta = r.get("metadata", {})
            context_parts.append(
                f"[{meta.get('chunk_id', meta.get('doc_id', '?'))}] "
                f"{meta.get('title', '')}\n{meta.get('content', '')}"
            )
        context_text = "\n\n---\n\n".join(context_parts)

        # 7. build prompts + LLM answer generation
        system_prompt, user_prompt = self.prompt_builder.build(context_text, query, domain)
        answer = ""
        if self.llm and self.llm.available:
            answer = self.llm.chat(system_prompt, user_prompt)

        total_ms = (time.time() - start_time) * 1000

        print(f"  [RAG] answer generated: {len(answer)} chars, total={total_ms:.1f}ms\n")

        return {
            "query": query, "clean_query": clean_query, "keywords": keywords,
            "domain": domain, "intent_confidence": confidence,
            "matched_rules": matched_rules,
            "results": results, "result_count": len(results),
            "system_prompt": system_prompt, "user_prompt": user_prompt,
            "answer": answer, "duration_ms": round(total_ms, 2),
        }


    def process(self, search_results: List[Dict], query: str,
                biz_domain: Optional[str] = None,
                extra_context: Optional[Dict] = None) -> Dict[str, str]:
        """Backward-compatible wrapper for AgentRAGOrchestrator."""
        clean_query = query
        if self.preprocessor:
            clean_query = self.preprocessor.clean(query)
        context_text = "\n\n---\n\n".join(
            f"[{r.get('metadata', r).get('doc_id', '?')}] {r.get('metadata', r).get('title', '')}\n{r.get('metadata', r).get('content', '')}"
            for r in search_results
        )
        sys_p, usr_p = self.prompt_builder.build(context_text, clean_query, biz_domain or "")
        return {"system": sys_p, "user": usr_p}


from prompts.manager import PromptManager
from prompts.security import PromptSanitizer, PromptSecurityConstants


class RAGPromptBuilder:
    """Build structured prompts from templates, with injection sanitization."""

    def __init__(self, prompt_manager=None):
        if prompt_manager is None:
            prompt_manager = PromptManager()
        self.pm = prompt_manager
        self.sanitizer = PromptSanitizer()

    def build(self, context_text: str, query: str, domain: str = "") -> tuple:
        """Return (system_prompt, user_prompt)."""
        safe_query = self.sanitizer.sanitize(query, "user_query")
        system_prompt = self.pm.get_system_prompt()
        system_prompt = system_prompt.replace("{reference_section}", context_text)
        system_prompt += PromptSecurityConstants.ANTI_INJECTION_INSTRUCTION
        user_prompt = self.pm.get_user_prompt(context=context_text, question=safe_query)
        return system_prompt, user_prompt
