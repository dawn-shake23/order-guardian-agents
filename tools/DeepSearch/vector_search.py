from typing import Dict, Any, Optional
from tools.BaseTool.base_tool import BaseTool, ToolResult
from memory.memory_hub import MemoryHub

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from memory.storage.hybrid_search import HybridSearchEngine
    from tools.DeepSearch.deep_search import DeepSearchEngine, DeepSearchQuery
    from tools.DeepSearch.rag_pipeline import RAGPipeline, RagConfig
    from agents.rag_orchestrator import AgentRAGOrchestrator
    _HAS_DEEP_SEARCH = True
except ImportError:
    _HAS_DEEP_SEARCH = False


class VectorSearchTool(BaseTool):
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        if _HAS_DEEP_SEARCH:
            self.hybrid_engine = HybridSearchEngine(memory_hub.vector_store, memory_hub.struct_mysql)
            self.deep_search = DeepSearchEngine(self.hybrid_engine)
            self.rag_pipeline = RAGPipeline(config=RagConfig(max_context_tokens=4000))
            self.orchestrator = AgentRAGOrchestrator(
                memory_hub,
                deep_search_engine=self.deep_search,
                rag_pipeline=self.rag_pipeline
            )
        super().__init__()

    def _run(self, params: Dict[str, Any], sandbox: Optional[Any] = None) -> Dict[str, Any]:
        query = params.get("query", "")
        biz_domain = params.get("biz_domain", "order")
        top_k = params.get("top_k", 3)

        if _HAS_DEEP_SEARCH and _HAS_NUMPY:
            use_deep_search = params.get("deep_search", False)
            if use_deep_search:
                ds_query = DeepSearchQuery(
                    raw_query=query, biz_domain=biz_domain,
                    top_k=top_k, require_cross_validation=True
                )
                results = self.deep_search.search(ds_query)
                search_results = [r.model_dump() for r in results]
                return {"search_result": search_results, "total": len(search_results), "deep_search": True}

            mock_embedding = np.random.rand(1024).tolist()
            results = self.hybrid_engine.search_with_filter(
                query_embedding=mock_embedding, biz_domain=biz_domain, top_k=top_k
            )
            if results:
                return {"search_result": results, "total": len(results)}

        return {
            "search_result": [
                {"metadata": {"doc_id": "mock_1", "title": f"{biz_domain}业务规则",
                 "content": f"关于{query}的处理规范", "biz_domain": biz_domain}, "distance": 0.5}
            ],
            "total": 1
        }
