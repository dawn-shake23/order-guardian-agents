"""
对账 Agent — 金额核算 + 渠道金额校验 + 重复支付检测

输出统一 Finding 模型。
"""

from typing import Dict, Any, List, Optional
from core.tracing import traceable
from models.mock_orders import MockOrder, PaymentState
from models.finding import Finding, FindingType, Severity, Evidence, AgentReport


class ReconciliationAgent:
    """对账校验专家 — 订单-渠道金额一致性和重复支付"""

    def __init__(self):
        self.agent_type = "reconciliation"

    @traceable(name="reconciliation:reconcile", run_type="chain", tags=["agent", "reconciliation"])
    def reconcile(self, order: MockOrder, context: Optional[Dict[str, Any]] = None) -> AgentReport:
        findings: List[Finding] = []

        findings.extend(self._reconcile_amounts(order))
        findings.extend(self._detect_duplicate(order))
        findings.extend(self._check_channel_amount(order))
        findings.extend(self._check_payment_ids(order))

        if not findings:
            findings.append(Finding.normal(self.agent_type))

        passed = all(f.severity in (Severity.NONE, Severity.LOW) for f in findings)
        return AgentReport.from_findings(self.agent_type, findings)

    # ------------------------------------------------------------------
    # 金额核算
    # ------------------------------------------------------------------

    def _reconcile_amounts(self, order: MockOrder) -> List[Finding]:
        findings = []
        order_amount = order.order.order_amount
        total_paid = sum(
            p.amount for p in order.payments
            if p.state in (PaymentState.SUCCESS, PaymentState.PROCESSING)
        )

        if total_paid == 0 and order.payments:
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_MISMATCH,
                severity=Severity.HIGH, confidence=0.85,
                agent_type=self.agent_type,
                title="存在支付记录但成功金额为0",
                detail=f"订单{order_amount}元，实际到账0元",
                evidence=[
                    Evidence(source="order", field="order_amount", expected=str(order_amount), actual=str(order_amount)),
                    Evidence(source="payment", field="total_paid", expected=str(order_amount), actual="0"),
                ],
            ))
            return findings

        if not order.payments or total_paid == 0:
            return findings

        diff = total_paid - order_amount
        pct = diff / order_amount if order_amount > 0 else 0
        meta = order.metadata

        if meta.get("zero_amount_anomaly"):
            findings.append(Finding.create(
                finding_type=FindingType.CHANNEL_AMOUNT_ANOMALY,
                severity=Severity.CRITICAL, confidence=0.95,
                agent_type=self.agent_type,
                title="渠道回调金额为0",
                detail=f"订单{order_amount}元，渠道回调金额为0",
                evidence=[
                    Evidence(source="order", field="order_amount", expected=str(order_amount), actual=str(order_amount)),
                    Evidence(source="channel", field="callback_amount", expected=str(order_amount), actual="0"),
                ],
                suggestion="排查渠道回调数据格式，确认实际扣款金额",
            ))

        elif abs(diff) > 0.005:
            severity = Severity.HIGH if abs(pct) > 0.01 or abs(diff) > 50 else Severity.MEDIUM
            findings.append(Finding.create(
                finding_type=FindingType.AMOUNT_MISMATCH,
                severity=severity, confidence=0.88,
                agent_type=self.agent_type,
                title=f"支付金额与订单金额不一致: 差异{diff:+.2f}元",
                detail=f"订单{order_amount}元，实际支付{total_paid}元，差异{diff:+.2f}元({pct:+.2%})",
                evidence=[
                    Evidence(source="order", field="order_amount", expected=str(order_amount), actual=str(order_amount)),
                    Evidence(source="payment", field="total_paid", expected=str(order_amount), actual=str(total_paid)),
                ],
                suggestion=(
                    f"差异{diff:+.2f}元，需人工确认" if abs(diff) < 1.0
                    else f"差异{diff:+.2f}元，触发退款或补款"
                ),
                metadata={"diff_amount": round(diff, 2), "diff_pct": round(pct, 6)},
            ))

        return findings

    # ------------------------------------------------------------------
    # 重复支付
    # ------------------------------------------------------------------

    def _detect_duplicate(self, order: MockOrder) -> List[Finding]:
        findings = []
        success = [p for p in order.payments if p.state == PaymentState.SUCCESS]
        if len(success) <= 1:
            return findings

        overpaid = sum(p.amount for p in success) - order.order.order_amount
        findings.append(Finding.create(
            finding_type=FindingType.DUPLICATE_PAYMENT,
            severity=Severity.CRITICAL, confidence=0.95,
            agent_type=self.agent_type,
            title=f"重复支付: {len(success)}笔成功支付",
            detail=f"多渠道重复扣款，超额{overpaid:.2f}元",
            evidence=[
                Evidence(source="payment", field="success_count", expected="1", actual=str(len(success))),
                Evidence(source="payment", field="total_overpaid", actual=f"{overpaid:.2f}"),
            ],
            suggestion=f"确认实际支付渠道，退回重复扣款{overpaid:.2f}元",
            metadata={"payment_ids": [p.payment_id for p in success], "overpaid": overpaid},
        ))
        return findings

    # ------------------------------------------------------------------
    # 渠道金额异常
    # ------------------------------------------------------------------

    def _check_channel_amount(self, order: MockOrder) -> List[Finding]:
        findings = []
        for payment in order.payments:
            if payment.state != PaymentState.SUCCESS:
                continue

            ratio = payment.amount / order.order.order_amount if order.order.order_amount > 0 else 0
            if ratio < 0.01 and payment.amount < 1.0:
                findings.append(Finding.create(
                    finding_type=FindingType.CHANNEL_AMOUNT_ANOMALY,
                    severity=Severity.CRITICAL, confidence=0.93,
                    agent_type=self.agent_type,
                    title=f"疑似探测支付: {payment.amount}元 (订单{order.order.order_amount}元)",
                    detail=f"支付金额仅为订单金额的{ratio:.6%}",
                    evidence=[
                        Evidence(source="payment", field="amount", expected=str(order.order.order_amount), actual=str(payment.amount)),
                    ],
                    suggestion="标记为探测行为，不发货，联系用户确认",
                    metadata={"payment_id": payment.payment_id, "ratio": ratio},
                ))

            raw = payment.raw_channel_response
            if raw and raw.get("amount"):
                try:
                    raw_amount = float(raw["amount"])
                    if abs(raw_amount - payment.amount) > 0.005:
                        findings.append(Finding.create(
                            finding_type=FindingType.AMOUNT_MISMATCH,
                            severity=Severity.MEDIUM, confidence=0.75,
                            agent_type=self.agent_type,
                            title="渠道原始金额与记录不一致",
                            detail=f"渠道返回{raw_amount}元，系统记录{payment.amount}元",
                            evidence=[
                                Evidence(source="channel", field="raw_amount", actual=str(raw_amount)),
                                Evidence(source="payment", field="amount", actual=str(payment.amount)),
                            ],
                            metadata={"payment_id": payment.payment_id},
                        ))
                except (ValueError, TypeError):
                    pass
        return findings

    # ------------------------------------------------------------------
    # 支付ID完整性
    # ------------------------------------------------------------------

    def _check_payment_ids(self, order: MockOrder) -> List[Finding]:
        findings = []
        for payment in order.payments:
            if not payment.channel_order_no:
                findings.append(Finding.create(
                    finding_type=FindingType.FIELD_MISSING,
                    severity=Severity.MEDIUM, confidence=0.99,
                    agent_type=self.agent_type,
                    title="缺少渠道订单号",
                    detail=f"支付记录{payment.payment_id}无渠道订单号",
                    suggestion="补全渠道订单号以支持对账查询",
                    metadata={"payment_id": payment.payment_id},
                ))
            if payment.state == PaymentState.SUCCESS and not payment.paid_at:
                findings.append(Finding.create(
                    finding_type=FindingType.FIELD_MISSING,
                    severity=Severity.LOW, confidence=0.99,
                    agent_type=self.agent_type,
                    title="成功支付缺少支付时间",
                    detail=f"支付记录{payment.payment_id}缺少paid_at",
                    metadata={"payment_id": payment.payment_id},
                ))
        return findings
