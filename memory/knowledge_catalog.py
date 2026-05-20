"""
Knowledge catalog with domain classification, hierarchical directory,
and weighted retrieval for precise knowledge matching.

Catalog structure:
  payment/
    timeout/     - E2001, callback handling
    channel/     - E2003, E2008, channel switching
    error_codes/ - E2001-E2015 reference
    callback/    - E2005, callback reconciliation
  risk/
    blacklist/   - E3002, user/device/IP blacklists
    scoring/     - E3003, risk score models
    rules/       - R001-R012 rule definitions
    fraud/       - E3009, E3010 fraud detection
  reconciliation/
    amount/      - E4001, amount discrepancy
    status/      - E4002, status mismatch
    batch/       - E4004, batch reconciliation
    cross_day/   - E4007, cross-day processing
  order/
    lifecycle/   - E1001-E1005, order state machine
    timeout/     - E1004, auto-close rules
  operation/
    sop/         - Standard operating procedures
    escalation/  - Approval workflows
    emergency/   - System failure response
"""
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from core.logger import get_logger


@dataclass
class CatalogEntry:
    path: str
    doc_id: str
    title: str
    keywords: List[str] = field(default_factory=list)
    weight: float = 1.0
    error_codes: List[str] = field(default_factory=list)


class KnowledgeCatalog:
    """
    Hierarchical knowledge directory with weighted domain retrieval.
    Maps error codes and business scenarios to specific catalog paths.
    """

    def __init__(self):
        self._entries: Dict[str, CatalogEntry] = {}
        self._tree: Dict[str, Any] = {}
        self._error_index: Dict[str, List[str]] = {}
        self._keyword_index: Dict[str, List[str]] = {}
        self.logger = get_logger("knowledge_catalog")
        self._build()

    def _build(self):
        self._tree = {
            "payment": {
                "label": "Payment Processing",
                "weight": 1.0,
                "children": {
                    "timeout": {"label": "Timeout (E2001)", "weight": 1.2},
                    "channel": {"label": "Channel Exception (E2003,E2008)", "weight": 1.1},
                    "error_codes": {"label": "Error Code Reference (E2001-E2015)", "weight": 0.9},
                    "callback": {"label": "Callback Handling (E2005)", "weight": 1.1},
                    "refund": {"label": "Refund Processing (E2004)", "weight": 0.8},
                },
            },
            "risk": {
                "label": "Risk Control",
                "weight": 1.0,
                "children": {
                    "blacklist": {"label": "Blacklist Rules (E3002)", "weight": 1.3},
                    "scoring": {"label": "Risk Scoring (E3003)", "weight": 1.0},
                    "rules": {"label": "Risk Rules (R001-R012)", "weight": 1.1},
                    "fraud": {"label": "Fraud Detection (E3009,E3010)", "weight": 1.2},
                    "high_freq": {"label": "High Frequency (E3004)", "weight": 0.9},
                },
            },
            "reconciliation": {
                "label": "Financial Reconciliation",
                "weight": 1.0,
                "children": {
                    "amount": {"label": "Amount Discrepancy (E4001)", "weight": 1.2},
                    "status": {"label": "Status Mismatch (E4002)", "weight": 1.1},
                    "batch": {"label": "Batch Processing (E4004)", "weight": 0.9},
                    "cross_day": {"label": "Cross-Day (E4007)", "weight": 0.8},
                },
            },
            "order": {
                "label": "Order Management",
                "weight": 0.9,
                "children": {
                    "lifecycle": {"label": "Order State Machine (E1001-E1005)", "weight": 1.0},
                    "timeout": {"label": "Auto-Close Rules (E1004)", "weight": 0.8},
                },
            },
            "operation": {
                "label": "Operations",
                "weight": 0.8,
                "children": {
                    "sop": {"label": "Standard Procedures", "weight": 1.0},
                    "escalation": {"label": "Approval Workflows", "weight": 1.0},
                    "emergency": {"label": "Emergency Response", "weight": 1.2},
                },
            },
        }

    def register(self, doc_id: str, title: str, biz_domain: str,
                 keywords: Optional[List[str]] = None,
                 error_codes: Optional[List[str]] = None,
                 sub_category: str = "general"):
        entry = CatalogEntry(
            path=f"{biz_domain}/{sub_category}",
            doc_id=doc_id, title=title,
            keywords=keywords or [],
            error_codes=error_codes or [],
            weight=self._get_category_weight(biz_domain, sub_category),
        )
        self._entries[doc_id] = entry

        for code in entry.error_codes:
            if code not in self._error_index:
                self._error_index[code] = []
            self._error_index[code].append(doc_id)

        for kw in entry.keywords:
            if kw not in self._keyword_index:
                self._keyword_index[kw] = []
            self._keyword_index[kw].append(doc_id)

    def lookup_by_error_code(self, error_code: str) -> List[str]:
        """Find document IDs relevant to an error code."""
        direct = self._error_index.get(error_code, [])
        prefix = self._error_index.get(error_code[:4], [])
        return list(set(direct + prefix))

    def lookup_by_domain(self, domain: str, sub_category: str = "") -> List[Tuple[str, float]]:
        """Find documents in a domain, with optional sub-category filter, sorted by weight."""
        results = []
        target_path = f"{domain}/{sub_category}" if sub_category else domain
        for doc_id, entry in self._entries.items():
            if entry.path.startswith(target_path):
                results.append((doc_id, entry.weight))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_weight(self, doc_id: str) -> float:
        entry = self._entries.get(doc_id)
        return entry.weight if entry else 1.0

    def get_catalog_tree(self) -> Dict[str, Any]:
        return self._tree

    def _get_category_weight(self, domain: str, sub_category: str) -> float:
        domain_node = self._tree.get(domain, {})
        base_weight = domain_node.get("weight", 1.0)
        children = domain_node.get("children", {})
        child = children.get(sub_category, {})
        child_weight = child.get("weight", 1.0)
        return base_weight * child_weight


class KnowledgeRouter:
    """
    Route queries to the correct knowledge catalog path.
    Determines which domain + sub-category to search based on query content.
    """

    def __init__(self, catalog: Optional[KnowledgeCatalog] = None):
        self.catalog = catalog or KnowledgeCatalog()
        self.logger = get_logger("knowledge_router")

    def route(self, query: str, error_code: str = "", domain: str = "") -> Dict[str, Any]:
        """
        Determine the optimal retrieval path for a query.
        Returns target paths with weights for FAISS search filtering.
        """
        paths: Dict[str, float] = {}
        query_lower = query.lower()

        if error_code:
            matching_docs = self.catalog.lookup_by_error_code(error_code)
            for doc_id in matching_docs:
                entry = self.catalog._entries.get(doc_id)
                if entry:
                    paths[entry.path] = max(paths.get(entry.path, 0), entry.weight)

        if domain:
            domain_results = self.catalog.lookup_by_domain(domain)
            for doc_id, weight in domain_results:
                entry = self.catalog._entries.get(doc_id)
                if entry:
                    paths[entry.path] = max(paths.get(entry.path, 0), weight)

        patterns = [
            (["payment", "timeout", "callback", "E2001", "channel", "refund", "E2004", "E2005"], "payment"),
            (["risk", "blacklist", "fraud", "score", "block", "E3001", "E3002", "R00"], "risk"),
            (["reconciliation", "reconcile", "diff", "mismatch", "ledger", "E4001", "E4002"], "reconciliation"),
            (["order", "status", "lifecycle", "close", "create", "E100"], "order"),
            (["sop", "operation", "manual", "approval", "escalation"], "operation"),
        ]
        for keywords, matched_domain in patterns:
            if any(kw in query_lower for kw in keywords):
                domain_results = self.catalog.lookup_by_domain(matched_domain)
                for doc_id, weight in domain_results:
                    entry = self.catalog._entries.get(doc_id)
                    if entry:
                        paths[entry.path] = max(paths.get(entry.path, 0), weight)

        sorted_paths = sorted(paths.items(), key=lambda x: x[1], reverse=True)
        self.logger.info("knowledge_route", extra={"query": query[:60], "paths": len(sorted_paths)})
        return {"paths": sorted_paths, "primary_domain": domain or (sorted_paths[0][0].split("/")[0] if sorted_paths else "payment")}
