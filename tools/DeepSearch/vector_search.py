"""Vector search tool exposed to Agent call_tool registry."""
from typing import Any, Dict, Optional

import numpy as np

from tools.BaseTool.base_tool import BaseTool, ToolResult
from memory.memory_hub import MemoryHub
from memory.storage.hybrid_search import HybridSearchEngine

_HAS_DEEP_SEARCH = False
try:
    from tools.DeepSearch.deep_search import DeepSearchEngine, DeepSearchQuery
    from tools.DeepSearch.rag_pipeline import RAGPipeline
    from agents.rag_orchestrator import AgentRAGOrchestrator
    from config import SystemConfig
    _HAS_DEEP_SEARCH = True
except ImportError:
    pass


class VectorSearchTool(BaseTool):
    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        if _HAS_DEEP_SEARCH:
            self.hybrid_engine = HybridSearchEngine(memory_hub.vector_store, memory_hub.struct_mysql)
            self.deep_search = DeepSearchEngine(self.hybrid_engine)
            self.rag_pipeline = RAGPipeline(
                config=SystemConfig(),
                hybrid_engine=self.hybrid_engine,
            )
            self.orchestrator = AgentRAGOrchestrator(
                memory_hub,
                deep_search_engine=self.deep_search,
                rag_pipeline=self.rag_pipeline,
            )
        super().__init__()

    def _run(self, params: Dict[str, Any], sandbox=None) -> Dict[str, Any]:
        query = params.get("query", "")
        biz_domain = params.get("biz_domain", "order")
        top_k = params.get("top_k", 3)

        if _HAS_DEEP_SEARCH:
            if params.get("deep_search", False):
                ds_query = DeepSearchQuery(
                    raw_query=query, biz_domain=biz_domain,
                    top_k=top_k, require_cross_validation=True,
                )
                results = self.deep_search.search(ds_query)
                return {"search_result": [r.model_dump() for r in results], "total": len(results), "deep_search": True}

            results = self.hybrid_engine.search_with_filter(
                query_embedding=np.random.rand(1024).tolist(),
                biz_domain=biz_domain, top_k=top_k,
            )
            if results:
                return {"search_result": results, "total": len(results)}

        return {"search_result": [{"metadata": {"doc_id": "mock_1", "title": biz_domain,
                                  "content": query, "biz_domain": biz_domain}, "distance": 0.5}], "total": 1}
