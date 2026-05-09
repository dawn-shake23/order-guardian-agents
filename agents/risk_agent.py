"""
风控 Agent — 交易风险评估 + 异常行为检测 + 置信度打分

输出统一 Finding 模型。
"""

from typing import Dict, Any, List, Optional
from core.tracing import traceable
from models.mock_orders import MockOrder
from models.finding import Finding, FindingType, Severity, Evidence, AgentReport


class RiskAgent:
    """风控专家 Agent — 6维度交易风险检测"""

    def __init__(self):
        self.agent_type = "risk"

        self.thresholds = {
            "bulk_order_count": 3,
            "high_value_threshold": 10000.0,
            "refund_rate_threshold": 0.5,
            "refund_count_threshold": 5,
            "night_start": 0,
            "night_end": 5,
        }

    @traceable(name="risk_agent:assess", run_type="chain", tags=["agent", "risk"])
    def assess(self, order: MockOrder, context: Optional[Dict[str, Any]] = None) -> AgentReport:
        findings: List[Finding] = []

        # ---- 6维度检测 ----
        findings.extend(self._check_ip(order))
        findings.extend(self._check_device(order))
        findings.extend(self._check_time(order))
        findings.extend(self._check_amount(order))
        findings.extend(self._check_frequency(order))
        findings.extend(self._check_refund(order))

        if not findings:
            findings.append(Finding.normal(self.agent_type))

        passed = all(f.severity in (Severity.NONE, Severity.LOW) for f in findings)
        return AgentReport.from_findings(self.agent_type, findings)

    # ------------------------------------------------------------------
    # 1. IP 检测
    # ------------------------------------------------------------------

    def _check_ip(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        findings = []

        if meta.get("overseas_ip"):
            findings.append(Finding.create(
                finding_type=FindingType.IP_ANOMALY,
                severity=Severity.MEDIUM,
                confidence=0.78,
                agent_type=self.agent_type,
                title="海外IP访问",
                detail="订单来源IP归属海外，与用户常用地不符",
                evidence=[Evidence(source="order", field="ip_address", actual=order.order.ip_address or "unknown")],
            ))

        if meta.get("suspicious_ip"):
            findings.append(Finding.create(
                finding_type=FindingType.IP_ANOMALY,
                severity=Severity.MEDIUM,
                confidence=0.75,
                agent_type=self.agent_type,
                title="可疑IP段（VPN/代理）",
                detail="订单来源IP疑似代理或VPN",
                evidence=[Evidence(source="order", field="ip_address", actual=order.order.ip_address or "unknown")],
            ))

        if meta.get("ip_geo_mismatch"):
            findings.append(Finding.create(
                finding_type=FindingType.IP_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.82,
                agent_type=self.agent_type,
                title="IP归属地与用户常用地不匹配",
                detail="IP地理位置与用户历史地址偏差过大",
            ))

        return findings

    # ------------------------------------------------------------------
    # 2. 设备检测
    # ------------------------------------------------------------------

    def _check_device(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        findings = []

        if meta.get("new_device"):
            findings.append(Finding.create(
                finding_type=FindingType.DEVICE_ANOMALY,
                severity=Severity.MEDIUM,
                confidence=0.70,
                agent_type=self.agent_type,
                title="新设备首次登录",
                detail="用户使用新设备下单，设备指纹未识别",
                evidence=[Evidence(source="order", field="device_fingerprint", actual=order.order.device_fingerprint or "unknown")],
            ))

        changes = meta.get("device_change_count_7d", 0)
        if changes >= 2:
            findings.append(Finding.create(
                finding_type=FindingType.DEVICE_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.80,
                agent_type=self.agent_type,
                title=f"7天内更换设备{changes}次",
                detail="高频设备更换，可能存在账号共享或盗用",
                suggestion="触发增强验证（短信/人脸）",
                metadata={"device_changes_7d": changes},
            ))

        return findings

    # ------------------------------------------------------------------
    # 3. 时间检测
    # ------------------------------------------------------------------

    def _check_time(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        created_hour = meta.get("created_hour", "")

        try:
            hour = int(created_hour.split(":")[0]) if created_hour else -1
        except (ValueError, AttributeError):
            return []

        is_night = 0 <= hour < self.thresholds["night_start"] or hour >= 22
        if not is_night:
            return []

        is_large = order.order.order_amount > self.thresholds["high_value_threshold"]
        findings = []

        if is_large:
            findings.append(Finding.create(
                finding_type=FindingType.TIME_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.75,
                agent_type=self.agent_type,
                title=f"深夜大额交易 ({created_hour})",
                detail=f"深夜{created_hour}下单{order.order.order_amount}元，与正常消费模式不符",
                suggestion="建议人工复核后放行",
            ))
        else:
            findings.append(Finding.create(
                finding_type=FindingType.TIME_ANOMALY,
                severity=Severity.LOW,
                confidence=0.60,
                agent_type=self.agent_type,
                title=f"深夜时段下单 ({created_hour})",
                detail="下单时间处于深夜时段",
            ))

        return findings

    # ------------------------------------------------------------------
    # 4. 金额检测
    # ------------------------------------------------------------------

    def _check_amount(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        findings = []

        if meta.get("test_amount_suspicious"):
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.90,
                agent_type=self.agent_type,
                title="支付金额异常（疑似0.01元探测）",
                detail=f"订单{order.order.order_amount}元但支付金额极小",
                suggestion="标记为探测行为，不发货，加入风控黑名单",
            ))
            return findings

        anomaly_score = meta.get("amount_anomaly_score", 0)
        if anomaly_score > 0.7:
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_ANOMALY,
                severity=Severity.HIGH,
                confidence=anomaly_score,
                agent_type=self.agent_type,
                title=f"金额异常评分过高: {anomaly_score:.0%}",
                detail="交易金额模式与用户历史严重偏离",
            ))

        is_large = order.order.order_amount > self.thresholds["high_value_threshold"]
        is_new = meta.get("new_account_days", 999) < 7
        if is_large and is_new:
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.78,
                agent_type=self.agent_type,
                title="新账户大额交易",
                detail=f"账户创建{meta.get('new_account_days')}天内下单{order.order.order_amount}元",
                suggestion="需人工审核后放行",
            ))

        usual = meta.get("user_usual_amount", 0)
        is_first_large = meta.get("first_large_order") and order.order.order_amount > 10 * usual
        if is_first_large:
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_ANOMALY,
                severity=Severity.HIGH,
                confidence=0.72,
                agent_type=self.agent_type,
                title=f"首笔大额远超平时消费（平时{usual}元）",
                detail=f"用户历史平均消费{usual}元，当前订单{order.order.order_amount}元",
                suggestion="触发大额交易验证",
                metadata={"user_usual_amount": usual},
            ))

        return findings

    # ------------------------------------------------------------------
    # 5. 频率检测
    # ------------------------------------------------------------------

    def _check_frequency(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        findings = []

        bulk_count = meta.get("bulk_order_count_30min", 0)
        if bulk_count >= self.thresholds["bulk_order_count"]:
            findings.append(Finding.create(
                finding_type=FindingType.BULK_ORDER_RISK,
                severity=Severity.HIGH,
                confidence=0.82,
                agent_type=self.agent_type,
                title=f"短时批量下单: 30分钟内{bulk_count}笔",
                detail=f"30分钟内同一IP创建{bulk_count}笔订单，总金额{meta.get('total_amount_30min', 0)}元",
                evidence=[
                    Evidence(source="metadata", field="bulk_order_count_30min", actual=str(bulk_count)),
                    Evidence(source="metadata", field="total_amount_30min", actual=str(meta.get("total_amount_30min", 0))),
                ],
                suggestion="暂停该IP下单，人工审核历史订单",
                metadata={"bulk_count": bulk_count, "total_amount_30min": meta.get("total_amount_30min")},
            ))

        return findings

    # ------------------------------------------------------------------
    # 6. 退款检测
    # ------------------------------------------------------------------

    def _check_refund(self, order: MockOrder) -> List[Finding]:
        meta = order.metadata
        findings = []

        refund_rate = meta.get("refund_rate", 0)
        refund_count = meta.get("refund_count_30d", 0)

        if refund_rate >= self.thresholds["refund_rate_threshold"] or refund_count >= self.thresholds["refund_count_threshold"]:
            findings.append(Finding.create(
                finding_type=FindingType.REFUND_ABUSE,
                severity=Severity.CRITICAL,
                confidence=0.88,
                agent_type=self.agent_type,
                title=f"疑似退款滥用: 30天退款{refund_rate:.0%}/{refund_count}笔",
                detail=f"30天内退款率{refund_rate:.0%}，退款总额{meta.get('refund_amount_30d', 0)}元",
                evidence=[
                    Evidence(source="metadata", field="refund_rate_30d", expected="<50%", actual=f"{refund_rate:.0%}"),
                    Evidence(source="metadata", field="refund_count_30d", actual=str(refund_count)),
                ],
                suggestion="标记为退款滥用，暂停该用户退款权限，人工审核历史退款",
                metadata={"refund_rate": refund_rate, "refund_count": refund_count},
            ))

        return findings
