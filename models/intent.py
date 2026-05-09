"""
意图分类 & 向量检索 — 小模型预留组件

生产环境：
- IntentClassifier → 小模型（如 Qwen3-1.7B / Llama3-8B）做意图分类和任务重写
- VectorRetriever → embedding 模型 + FAISS 做业务手册/历史案例相似检索

当前 Mock 实现基于订单 metadata 和异常类型做确定性分类和规则检索，
接口与生产组件一致，后续换成模型调用即可。
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field

from models.mock_orders import MockOrder, AnomalyType
from core.tracing import traceable


class Intent(str, Enum):
    """意图分类结果"""
    PAYMENT_INTEGRITY = "payment_integrity"     # 支付完整性检查（掉单/丢单/回调）
    RECONCILIATION = "reconciliation"            # 对账核查（金额不符/重复支付）
    RISK_ASSESSMENT = "risk_assessment"          # 风控评估（欺诈/退款滥用）
    FULL_AUDIT = "full_audit"                   # 全量审计


class IntentResult(BaseModel):
    """意图分类结果"""
    primary_intent: Intent = Field(description="主要意图")
    secondary_intents: List[Intent] = Field(default_factory=list, description="次级意图")
    confidence: float = Field(ge=0.0, le=1.0, description="分类置信度")
    rewritten_query: str = Field(default="", description="任务重写结果")
    dispatched_agents: List[str] = Field(default_factory=list, description="需要调度的Agent列表")
    reasoning: str = Field(default="", description="分类推理过程")


class RetrievedCase(BaseModel):
    """检索到的参考案例"""
    case_id: str
    title: str
    similarity: float = Field(ge=0.0, le=1.0)
    resolution: str = ""
    tags: List[str] = Field(default_factory=list)


class VectorRetrievalResult(BaseModel):
    """向量检索结果"""
    query: str
    cases: List[RetrievedCase] = Field(default_factory=list)
    relevant_rules: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0


# ============================================================
# IntentClassifier
# ============================================================

# 异常类型 → 意图映射
_ANOMALY_INTENT_MAP: Dict[AnomalyType, List[Intent]] = {
    AnomalyType.NORMAL: [Intent.PAYMENT_INTEGRITY],
    AnomalyType.DROPPED_ORDER: [Intent.PAYMENT_INTEGRITY, Intent.RISK_ASSESSMENT],
    AnomalyType.LOST_ORDER: [Intent.PAYMENT_INTEGRITY, Intent.RISK_ASSESSMENT],
    AnomalyType.RECONCILIATION_MISMATCH: [Intent.RECONCILIATION, Intent.PAYMENT_INTEGRITY],
    AnomalyType.RISK_SUSPICIOUS: [Intent.RISK_ASSESSMENT, Intent.RECONCILIATION],
}

# 意图 → Agent 映射
_INTENT_AGENT_MAP: Dict[Intent, str] = {
    Intent.PAYMENT_INTEGRITY: "payment_integrity",
    Intent.RECONCILIATION: "reconciliation",
    Intent.RISK_ASSESSMENT: "risk",
    Intent.FULL_AUDIT: "payment_integrity,reconciliation,risk",
}


class IntentClassifier:
    """
    意图分类器 — Mock 实现

    生产环境替换为:
        self.model = load_model("qwen3-1.7b") 或调用 LLM API
        result = self.model.classify(order_data)
    """

    def __init__(self):
        self.model_name = "mock_intent_classifier"
        self.version = "1.0.0"

    @traceable(name="intent_classifier:classify", run_type="chain", tags=["intent", "classification"])
    def classify(self, order: MockOrder) -> IntentResult:
        """分类订单意图，决定调度哪些 Agent"""
        anomaly_type = order.anomaly_type
        intents = _ANOMALY_INTENT_MAP.get(anomaly_type, [Intent.FULL_AUDIT])

        primary = intents[0]
        secondary = intents[1:] if len(intents) > 1 else []

        # 附加条件: 高风险 metadata 强制加风控
        if order.metadata.get("suspicious_ip") or order.metadata.get("overseas_ip"):
            if Intent.RISK_ASSESSMENT not in intents:
                secondary.append(Intent.RISK_ASSESSMENT)

        # 附加条件: 有金额差异强制加对账
        if order.metadata.get("diff_amount") or order.metadata.get("duplicate_payment"):
            if Intent.RECONCILIATION not in intents:
                secondary.append(Intent.RECONCILIATION)

        dispatched = list(dict.fromkeys(
            _INTENT_AGENT_MAP[i] for i in [primary] + secondary
        ))

        return IntentResult(
            primary_intent=primary,
            secondary_intents=secondary,
            confidence=0.95,
            rewritten_query=self._rewrite(order, primary),
            dispatched_agents=dispatched,
            reasoning=self._explain(order, primary, dispatched),
        )

    def _rewrite(self, order: MockOrder, intent: Intent) -> str:
        rewrites = {
            Intent.PAYMENT_INTEGRITY: f"检查订单 {order.order.order_id} 支付链路完整性："
                                      f"是否存在掉单/丢单/回调丢失，订单状态与支付状态是否一致",
            Intent.RECONCILIATION: f"核对订单 {order.order.order_id} 支付金额一致性："
                                    f"渠道金额与订单金额是否匹配，是否存在重复支付",
            Intent.RISK_ASSESSMENT: f"评估订单 {order.order.order_id} 交易风险："
                                     f"IP/设备/金额/频率是否存在异常信号",
            Intent.FULL_AUDIT: f"对订单 {order.order.order_id} 执行全量审计",
        }
        return rewrites.get(intent, rewrites[Intent.FULL_AUDIT])

    def _explain(self, order: MockOrder, intent: Intent, agents: list) -> str:
        return (
            f"订单类型={order.anomaly_type.value}, "
            f"主意图={intent.value}, "
            f"调度Agent={agents}"
        )


# ============================================================
# VectorRetriever
# ============================================================

class VectorRetriever:
    """
    向量检索引擎 — Mock 实现

    生产环境替换为:
        self.embedder = SentenceTransformer("bge-large-zh")
        self.index = faiss.read_index("business_rules.index")
        results = self.index.search(embedding, top_k)
    """

    def __init__(self):
        self.model_name = "mock_vector_retriever"
        self.version = "1.0.0"

        # Mock 知识库
        self._rules_db = {
            "掉单": [
                "掉单处理 SOP: 1.主动查询渠道订单状态 2.比对扣款记录 3.补单或关单",
                "回调超时阈值: 支付宝30s / 微信15s / 银联60s / 银行转账120s",
            ],
            "丢单": [
                "丢单处理 SOP: 1.确认支付入口可用性 2.发送支付提醒 3.超2小时关闭订单",
                "高价值订单(>10000元)丢单需立即人工跟进",
            ],
            "对账": [
                "对账差异<0.01元可自动抹平，>0.01元需人工确认",
                "渠道手续费导致的金额差异需标记 bank_fee，不归为异常",
            ],
            "风控": [
                "夜间(00:00-05:00)大额交易(>5000元)需人工复核",
                "7天内换设备>=2次触发增强验证",
                "30天退款率>50%或退款>5笔标记为退款滥用",
            ],
        }

    @traceable(name="vector_retriever:search", run_type="retriever", tags=["retrieval", "vector"])
    def search(self, query: str, top_k: int = 5) -> VectorRetrievalResult:
        """向量检索 - Mock 基于关键词匹配"""
        matched_cases = []
        matched_rules = []

        # 简化实现: 关键词 → 规则匹配（生产替换为 embedding + FAISS）
        keywords = {
            "掉单": ["掉单"],
            "丢单": ["丢单"],
            "对账": ["对账"],
            "金额": ["对账"],
            "差异": ["对账"],
            "风险": ["风控"],
            "欺诈": ["风控"],
            "退款": ["风控"],
            "批量": ["风控"],
            "回调": ["掉单"],
            "支付": ["掉单", "对账"],
        }

        matched_categories = set()
        for kw, categories in keywords.items():
            if kw in query:
                matched_categories.update(categories)

        for cat in matched_categories:
            rules = self._rules_db.get(cat, [])
            matched_rules.extend(rules)

        if not matched_rules:
            matched_rules.append("通用订单异常排查流程: 逐项检查支付状态/金额/回调/风控信号")

        # 构造 Mock 案例
        for i, rule in enumerate(matched_rules[:top_k]):
            matched_cases.append(RetrievedCase(
                case_id=f"CASE-{i+1:04d}",
                title=rule[:50],
                similarity=round(0.95 - i * 0.08, 2),
                resolution=rule,
                tags=list(matched_categories),
            ))

        return VectorRetrievalResult(
            query=query,
            cases=matched_cases,
            relevant_rules=matched_rules[:top_k],
            latency_ms=round(1.5 + len(matched_rules) * 0.3, 2),
        )
