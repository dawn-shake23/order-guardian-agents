"""
统一 Agent 输出规范 — 所有 Agent 遵循同一接口

设计原则：
- 所有 Agent 输出同一个 Finding 模型，Coordinator 直接聚合，不做字段翻译
- severity / confidence 使用统一算法和标尺
- evidence 携带可追溯的证据链，每条证据关联数据源
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """统一严重度"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(str, Enum):
    """差错类型枚举"""
    # 支付完整性
    STATE_INCONSISTENCY = "state_inconsistency"       # 订单-支付状态不一致
    CALLBACK_MISSING = "callback_missing"              # 回调丢失
    DROPPED_ORDER = "dropped_order"                   # 掉单
    LOST_ORDER = "lost_order"                         # 丢单
    PAYMENT_TIMEOUT = "payment_timeout"               # 支付超时
    PAYMENT_FAILED = "payment_failed"                 # 支付失败
    # 对账
    AMOUNT_MISMATCH = "amount_mismatch"               # 金额不符
    DUPLICATE_PAYMENT = "duplicate_payment"           # 重复支付
    CHANNEL_AMOUNT_ANOMALY = "channel_amount_anomaly"  # 渠道金额异常
    # 风控
    FRAUD_SUSPICION = "fraud_suspicion"               # 欺诈嫌疑
    REFUND_ABUSE = "refund_abuse"                     # 退款滥用
    BULK_ORDER_RISK = "bulk_order_risk"               # 批量下单风险
    DEVICE_ANOMALY = "device_anomaly"                 # 设备异常
    IP_ANOMALY = "ip_anomaly"                         # IP异常
    TIME_ANOMALY = "time_anomaly"                     # 时间异常
    AMOUNT_ANOMALY = "amount_anomaly"                 # 金额异常
    # 数据质量
    FIELD_MISSING = "field_missing"                   # 字段缺失
    FIELD_INVALID = "field_invalid"                   # 字段无效
    # 通用
    NORMAL = "normal"                                 # 无异常


class Evidence(BaseModel):
    """证据条目 — 可追溯的数据来源"""
    source: str = Field(description="证据来源: order / payment / channel / metadata")
    field: str = Field(description="字段名")
    expected: Any = Field(default=None, description="期望值")
    actual: Any = Field(default=None, description="实际值")
    detail: str = Field(default="", description="证据描述")


class Finding(BaseModel):
    """
    统一 Agent 发现模型 — 所有 Agent 的唯一输出格式

    每个 Finding 代表一个检出项。Agent 可以返回多个 Finding。
    """
    finding_type: FindingType = Field(description="差错类型")
    severity: Severity = Field(description="严重度")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0=不确定 1=完全确定")
    agent_type: str = Field(description="产出 Agent")
    title: str = Field(default="", description="一句话摘要")
    detail: str = Field(default="", description="详细描述")
    evidence: List[Evidence] = Field(default_factory=list, description="证据链")
    suggestion: str = Field(default="", description="处理建议")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    @classmethod
    def normal(cls, agent_type: str) -> "Finding":
        """快捷构造: 无异常发现"""
        return cls(
            finding_type=FindingType.NORMAL,
            severity=Severity.NONE,
            confidence=0.98,
            agent_type=agent_type,
            title="无异常",
            detail="该维度检查未发现异常",
        )

    @classmethod
    def create(
        cls,
        finding_type: FindingType,
        severity: Severity,
        confidence: float,
        agent_type: str,
        title: str,
        detail: str,
        evidence: Optional[List[Evidence]] = None,
        suggestion: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Finding":
        """标准化构造器"""
        return cls(
            finding_type=finding_type,
            severity=severity,
            confidence=round(confidence, 4),
            agent_type=agent_type,
            title=title,
            detail=detail,
            evidence=evidence or [],
            suggestion=suggestion,
            metadata=metadata or {},
        )


class AgentReport(BaseModel):
    """单个 Agent 的完整报告（含多个 Finding）"""
    agent_type: str
    passed: bool = Field(description="该 Agent 是否放行")
    findings: List[Finding] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_findings(cls, agent_type: str, findings: List[Finding]) -> "AgentReport":
        """从 Finding 列表构造报告"""
        if not findings:
            return cls(agent_type=agent_type, passed=True, overall_confidence=0.98)

        passed = all(f.severity in (Severity.NONE, Severity.LOW) for f in findings)
        confidences = [f.confidence for f in findings]
        overall = sum(confidences) / len(confidences) if confidences else 0.98

        return cls(
            agent_type=agent_type,
            passed=passed,
            findings=findings,
            overall_confidence=round(overall, 4),
        )


# ============================================================
# 置信度计算 — 统一算法
# ============================================================

def compute_confidence_from_signals(
    positive_signals: int,
    total_checks: int,
    strong_signal_count: int = 0,
) -> float:
    """
    根据信号数量计算置信度。

    规则：
    - 无信号(0 positive) → 高置信度放行
    - 信号越多/越强 → 置信度越高（系统越确定存在问题）
    """
    if total_checks == 0:
        return 0.95
    if positive_signals == 0:
        return 0.97
    ratio = positive_signals / total_checks
    boost = min(strong_signal_count * 0.08, 0.16)
    return min(0.50 + ratio * 0.35 + boost, 1.0)
