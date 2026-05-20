import re
import math
from typing import Dict, Any, Optional, List, Set
from memory.storage.vector.vector_store import VectorMemoryStore
from memory.storage.structured.mysql_repo import MySQLMemoryRepo
from core.logger import get_logger


class BM25Scorer:
    """
    BM25 关键词检索评分器
    精确词匹配，弥补向量检索在专有名词/编号上的不足
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_dl = 0.0
        self.df: Dict[str, int] = {}
        self.doc_lens: Dict[str, int] = {}

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r'[\w]+', text.lower())
        return tokens

    def index(self, docs: List[Dict[str, Any]]):
        self.doc_count = len(docs)
        total_len = 0
        for i, doc in enumerate(docs):
            content = doc.get("content", "") + " " + doc.get("title", "")
            tokens = self._tokenize(content)
            self.doc_lens[str(i)] = len(tokens)
            total_len += len(tokens)
            seen = set()
            for t in tokens:
                if t not in seen:
                    self.df[t] = self.df.get(t, 0) + 1
                    seen.add(t)
        self.avg_dl = total_len / max(self.doc_count, 1)

    def score(self, query: str, doc_idx: int) -> float:
        if self.doc_count == 0:
            return 0.0
        query_tokens = self._tokenize(query)
        doc_len = self.doc_lens.get(str(doc_idx), 0)
        score = 0.0
        for qt in query_tokens:
            if qt not in self.df:
                continue
            idf = math.log((self.doc_count - self.df[qt] + 0.5) / (self.df[qt] + 0.5) + 1)
            tf = 0
            score += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_dl, 1)))
        return score


class HybridSearchEngine:
    """
    混合检索引擎
    解决：先按业务字段过滤 → 再做向量相似度检索
    避免"先召回再过滤"导致的无效/过期数据混入
    """

    def __init__(self, vector_store: VectorMemoryStore, mysql_repo: MySQLMemoryRepo):
        self.vector_store = vector_store
        self.mysql = mysql_repo
        self.bm25 = BM25Scorer()
        self.logger = get_logger("hybrid_search")

    def search_with_filter(
        self,
        query_embedding: List[float],
        biz_domain: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        exclude_deleted: bool = True,
        exclude_archived: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        混合检索：业务字段预过滤 + 向量检索
        核心思路：先从结构化库拿到符合业务条件的doc_id集合，
        再在向量库中只对这些doc做相似度检索
        """
        filters = filters or {}

        # Step 1: 业务字段预过滤（从结构化库）
        candidate_doc_ids: Optional[Set[str]] = None
        if biz_domain or filters:
            candidate_doc_ids = self._pre_filter(biz_domain, filters, exclude_deleted, exclude_archived)
            if candidate_doc_ids is not None and len(candidate_doc_ids) == 0:
                self.logger.debug("pre_filter_empty", extra={"biz_domain": biz_domain})

        # Step 2: 向量检索
        raw_results = self.vector_store.search(query_embedding, k=top_k * 3)

        # Step 3: 用预过滤结果裁剪向量检索结果
        # If pre-filter returned empty set, skip filtering (use raw vector results)
        skip_filter = (candidate_doc_ids is not None and len(candidate_doc_ids) == 0)
        filtered_results = []
        for r in raw_results:
            meta = r.get("metadata", {})
            doc_id = meta.get("doc_id", "")
            if not skip_filter and candidate_doc_ids is not None and doc_id not in candidate_doc_ids:
                continue
            if exclude_deleted and meta.get("is_deleted", False):
                continue
            if exclude_archived and meta.get("is_archived", False):
                continue
            filtered_results.append(r)

        # Step 4: 截断到 top_k
        filtered_results = filtered_results[:top_k]

        self.logger.info("混合检索完成", extra={
            "biz_domain": biz_domain,
            "candidates": len(candidate_doc_ids) if candidate_doc_ids else "all",
            "raw_results": len(raw_results),
            "filtered_results": len(filtered_results)
        })
        return filtered_results

    def _pre_filter(
        self,
        biz_domain: Optional[str],
        filters: Dict[str, Any],
        exclude_deleted: bool,
        exclude_archived: bool,
    ) -> Optional[Set[str]]:
        """
        从结构化库预过滤，返回符合条件的doc_id集合
        """
        conditions = dict(filters)
        if biz_domain:
            conditions["biz_domain"] = biz_domain
        if exclude_deleted:
            conditions["is_deleted"] = False
        if exclude_archived:
            conditions["is_archived"] = False

        table = conditions.pop("_table", "documents")
        rows = self.mysql.query(table, conditions)
        return {row.get("doc_id", row.get("id", "")) for row in rows}

    def multi_route_recall(
        self,
        query: str,
        query_embedding: List[float],
        biz_domain: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        多路召回：向量检索 + BM25关键词 + 业务规则过滤
        返回三路结果，供后续RRF融合
        """
        # 路径1: 向量检索（语义）
        vector_results = self.search_with_filter(
            query_embedding, biz_domain, filters, top_k
        )

        # 路径2: BM25 关键词检索（精确词）
        bm25_results = self._bm25_search(query, biz_domain, top_k)

        # 路径3: 业务规则过滤（结构化查询）
        rule_results = self._rule_search(query, biz_domain, filters, top_k)

        return {
            "vector": vector_results,
            "bm25": bm25_results,
            "rule": rule_results,
        }

    def _bm25_search(self, query: str, biz_domain: Optional[str], top_k: int) -> List[Dict[str, Any]]:
        conditions = {}
        if biz_domain:
            conditions["biz_domain"] = biz_domain
        rows = self.mysql.query("documents", conditions)
        if not rows:
            return []
        self.bm25.index(rows)
        scored = []
        for i, row in enumerate(rows):
            s = self.bm25.score(query, i)
            if s > 0:
                scored.append({"metadata": row, "bm25_score": s})
        scored.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored[:top_k]

    def _rule_search(self, query: str, biz_domain: Optional[str], filters: Optional[Dict], top_k: int) -> List[Dict[str, Any]]:
        conditions = dict(filters or {})
        if biz_domain:
            conditions["biz_domain"] = biz_domain
        rows = self.mysql.query("documents", conditions)
        return [{"metadata": row, "rule_match": True} for row in rows[:top_k]]

    @staticmethod
    def rrf_fusion(
        multi_route_results: Dict[str, List[Dict[str, Any]]],
        k: int = 60,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        RRF (Reciprocal Rank Fusion) 融合
        公式：score = Σ weight_i / (k + rank_i)
        解决多路结果合并、去重、排序问题
        """
        weights = weights or {"vector": 0.5, "bm25": 0.3, "rule": 0.2}
        doc_scores: Dict[str, float] = {}
        doc_meta: Dict[str, Dict] = {}

        for route_name, results in multi_route_results.items():
            w = weights.get(route_name, 0.1)
            for rank, item in enumerate(results):
                meta = item.get("metadata", {})
                doc_id = meta.get("doc_id", meta.get("id", str(rank)))
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = 0.0
                    doc_meta[doc_id] = meta
                doc_scores[doc_id] += w / (k + rank + 1)

        fused = [
            {"doc_id": did, "score": score, "metadata": doc_meta[did]}
            for did, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        ]
        return fused
