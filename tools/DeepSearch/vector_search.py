from typing import Dict, Any, Optional
from tools.BaseTool.base_tool import BaseTool, ToolResult
from memory.memory_hub import MemoryHub
from memory.storage.hybrid_search import HybridSearchEngine
from tools.DeepSearch.deep_search import DeepSearchEngine, DeepSearchQuery
from tools.DeepSearch.rag_pipeline import RAGPipeline
from agents.rag_orchestrator import AgentRAGOrchestrator
import numpy as np


class VectorSearchTool(BaseTool):
    """
    增强版向量检索工具
    集成：混合检索 + DeepSearch + RAG流水线 + Agent编排
    """

    def __init__(self, memory_hub: MemoryHub):
        self.memory_hub = memory_hub
        self.hybrid_engine = HybridSearchEngine(memory_hub.vector_store, memory_hub.struct_mysql)
        self.deep_search = DeepSearchEngine(self.hybrid_engine)
        self.rag_pipeline = RAGPipeline(max_context_tokens=4000)
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
        use_deep_search = params.get("deep_search", False)
        agent_type = params.get("agent_type", biz_domain)
        session_id = params.get("session_id", "")
        order_id = params.get("order_id", "")

        if use_deep_search:
            ds_query = DeepSearchQuery(
                raw_query=query,
                biz_domain=biz_domain,
                top_k=top_k,
                require_cross_validation=True
            )
            results = self.deep_search.search(ds_query)
            search_results = [r.model_dump() for r in results]
            rag_prompt = self.rag_pipeline.process(
                search_results, query, biz_domain,
                extra_context={"session_id": session_id, "order_id": order_id}
            )
            return {
                "search_result": search_results,
                "total": len(search_results),
                "rag_prompt": rag_prompt,
                "deep_search": True
            }

        mock_embedding = np.random.rand(128).tolist()
        results = self.hybrid_engine.search_with_filter(
            query_embedding=mock_embedding,
            biz_domain=biz_domain,
            top_k=top_k
        )

        if not results:
            results = [
                {"metadata": {"doc_id": "mock_1", "title": f"{biz_domain}业务规则",
                 "content": f"关于{query}的处理规范", "biz_domain": biz_domain}, "distance": 0.5}
            ]

        return {"search_result": results, "total": len(results)}
