import re
import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from memory.storage.hybrid_search import HybridSearchEngine
from core.logger import get_logger


class DeepSearchQuery(BaseModel):
    raw_query: str
    biz_domain: Optional[str] = None
    time_range: Optional[Dict[str, str]] = None
    filters: Optional[Dict[str, Any]] = None
    top_k: int = 5
    require_cross_validation: bool = Field(default=False, description="是否需要交叉验证")


class DeepSearchResult(BaseModel):
    doc_id: str
    title: str
    content: str
    score: float
    biz_domain: str
    source_route: List[str] = Field(default_factory=list, description="命中哪些召回路径")
    validated: bool = Field(default=False, description="是否经过交叉验证")


class QueryDecomposer:
    """
    查询理解与拆分
    将复杂查询拆解为：时间过滤 + 业务域过滤 + 关键词匹配 + 向量召回
    """

    TIME_KEYWORDS = {
        "今天": 1, "昨日": 1, "昨天": 1,
        "近7天": 7, "近一周": 7, "最近一周": 7,
        "近30天": 30, "近一个月": 30, "最近一个月": 30,
        "近90天": 90, "近三个月": 90,
    }

    BIZ_DOMAIN_KEYWORDS = {
        "支付": "payment", "付款": "payment", "退款": "payment",
        "订单": "order", "下单": "order",
        "风险": "risk", "风控": "risk",
        "对账": "reconciliation", "账实": "reconciliation",
        "运营": "operation",
    }

    def decompose(self, raw_query: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "keywords": [],
            "biz_domain": None,
            "time_range": None,
            "filters": {},
        }

        tokens = re.findall(r'[\w]+', raw_query)
        result["keywords"] = tokens

        for kw, domain in self.BIZ_DOMAIN_KEYWORDS.items():
            if kw in raw_query:
                result["biz_domain"] = domain
                break

        for kw, days in self.TIME_KEYWORDS.items():
            if kw in raw_query:
                result["time_range"] = {"days": days}
                break

        return result


class CoarseRanker:
    """
    粗排：快速缩小范围
    策略：业务域匹配 + 时间过滤 + 简单关键词命中
    """

    def rank(self, docs: List[Dict[str, Any]], query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        scored = []
        for doc in docs:
            meta = doc.get("metadata", doc)
            score = 0.0

            if query_info.get("biz_domain") and meta.get("biz_domain") == query_info["biz_domain"]:
                score += 10.0

            if query_info.get("time_range"):
                days = query_info["time_range"].get("days", 999)
                updated = meta.get("updated_at", meta.get("created_at", 0))
                if updated and (time.time() - updated) < days * 86400:
                    score += 5.0

            for kw in query_info.get("keywords", []):
                content = meta.get("content", "") + meta.get("title", "")
                if kw.lower() in content.lower():
                    score += 2.0

            scored.append({**doc, "coarse_score": score})

        scored.sort(key=lambda x: x.get("coarse_score", 0), reverse=True)
        return scored


class FineRanker:
    """
    精排：高精度匹配
    策略：RRF融合分 + 语义相似度 + 业务权重
    """

    def rank(self, docs: List[Dict[str, Any]], rrf_score_weight: float = 0.6,
             coarse_weight: float = 0.4) -> List[Dict[str, Any]]:
        scored = []
        for doc in docs:
            rrf_score = doc.get("score", 0)
            coarse_score = doc.get("coarse_score", 0)
            distance = doc.get("distance", 1.0)
            semantic_score = max(0, 1.0 - distance)

            final_score = (
                rrf_score * rrf_score_weight
                + coarse_score * coarse_weight * 0.1
                + semantic_score * 0.3
            )
            scored.append({**doc, "final_score": final_score})

        scored.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return scored


class CrossValidator:
    """
    交叉验证：多路结果互相验证，提高召回精准度
    如果一个文档在多条路径都被召回，置信度更高
    """

    def validate(self, multi_route: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[str]]:
        doc_routes: Dict[str, List[str]] = {}
        for route_name, results in multi_route.items():
            for item in results:
                meta = item.get("metadata", item)
                doc_id = meta.get("doc_id", meta.get("id", ""))
                if doc_id not in doc_routes:
                    doc_routes[doc_id] = []
                if route_name not in doc_routes[doc_id]:
                    doc_routes[doc_id].append(route_name)
        return doc_routes


class DeepSearchEngine:
    """
    DeepSearch 深度检索引擎
    完整流程：查询理解 → 多路召回 → RRF融合 → 粗排 → 精排 → 交叉验证
    """

    def __init__(self, hybrid_engine: HybridSearchEngine):
        self.hybrid = hybrid_engine
        self.decomposer = QueryDecomposer()
        self.coarse_ranker = CoarseRanker()
        self.fine_ranker = FineRanker()
        self.cross_validator = CrossValidator()
        self.logger = get_logger("deep_search")

    def search(self, query: DeepSearchQuery, query_embedding: Optional[List[float]] = None) -> List[DeepSearchResult]:
        self.logger.info("DeepSearch开始", extra={"query": query.raw_query, "biz_domain": query.biz_domain})

        # Step 1: 查询理解与拆分
        query_info = self.decomposer.decompose(query.raw_query)
        if query.biz_domain:
            query_info["biz_domain"] = query.biz_domain
        if query.time_range:
            query_info["time_range"] = query.time_range
        if query.filters:
            query_info["filters"].update(query.filters)

        self.logger.info("查询拆解完成", extra={"query_info": query_info})

        # Step 2: 多路召回
        import numpy as np
        if query_embedding is None:
            query_embedding = np.random.rand(128).tolist()

        multi_route = self.hybrid.multi_route_recall(
            query=query.raw_query,
            query_embedding=query_embedding,
            biz_domain=query_info.get("biz_domain"),
            filters=query_info.get("filters"),
            top_k=query.top_k * 3,
        )

        # Step 3: RRF融合
        fused = HybridSearchEngine.rrf_fusion(
            multi_route,
            weights={"vector": 0.5, "bm25": 0.3, "rule": 0.2}
        )

        # Step 4: 粗排
        coarse = self.coarse_ranker.rank(fused, query_info)

        # Step 5: 精排
        fine = self.fine_ranker.rank(coarse)

        # Step 6: 交叉验证
        doc_routes = self.cross_validator.validate(multi_route)

        # Step 7: 组装结果
        results = []
        for item in fine[:query.top_k]:
            meta = item.get("metadata", {})
            doc_id = meta.get("doc_id", meta.get("id", ""))
            validated = query.require_cross_validation and len(doc_routes.get(doc_id, [])) >= 2

            results.append(DeepSearchResult(
                doc_id=doc_id,
                title=meta.get("title", ""),
                content=meta.get("content", ""),
                score=item.get("final_score", 0),
                biz_domain=meta.get("biz_domain", ""),
                source_route=doc_routes.get(doc_id, []),
                validated=validated or len(doc_routes.get(doc_id, [])) >= 2,
            ))

        self.logger.info("DeepSearch完成", extra={
            "total_results": len(results),
            "validated_count": sum(1 for r in results if r.validated)
        })
        return results
