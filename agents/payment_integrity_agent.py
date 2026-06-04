"""
支付完整性 Agent — 状态一致性 + 掉单丢单 + 回调完整性 + 支付链路诊断

合并了旧版 BizValidationAgent + PaymentFlowAgent 中与支付相关的职责。
输出统一 Finding 模型。
"""

from typing import Dict, Any, List, Optional
from core.tracing import traceable
from models.mock_orders import MockOrder, PaymentState, OrderState, PaymentRecord
from models.finding import (
    Finding, FindingType, Severity, Evidence,
    AgentReport, compute_confidence_from_signals,
)


class PaymentIntegrityAgent:
    """支付完整性校验专家 — 专注支付链路端到端诊断"""

    def __init__(self):
        self.agent_type = "payment_integrity"

    @traceable(name="payment_integrity:check", run_type="chain", tags=["agent", "payment_integrity"])
    def check(self, order: MockOrder, context: Optional[Dict[str, Any]] = None) -> AgentReport:
        findings: List[Finding] = []

        # ---- 1. 丢单检测 ----
        findings.extend(self._detect_lost_order(order))

        # ---- 2. 逐笔支付记录诊断 ----
        for payment in order.payments:
            findings.extend(self._diagnose_payment(order, payment))

        # ---- 3. 状态一致性检查 ----
        findings.extend(self._check_state_consistency(order))

        # ---- 4. 跨字段逻辑 ----
        findings.extend(self._check_cross_field(order))

        if not findings:
            findings.append(Finding.normal(self.agent_type))

        passed = all(f.severity in (Severity.NONE, Severity.LOW) for f in findings)
        return AgentReport.from_findings(self.agent_type, findings)

    # ------------------------------------------------------------------
    # 丢单检测
    # ------------------------------------------------------------------

    def _detect_lost_order(self, order: MockOrder) -> List[Finding]:
        if order.payments:
            return []

        no_action = order.metadata.get("no_action_minutes", 0)
        findings = []

        if no_action > 0:
            severity = Severity.HIGH if no_action > 120 else Severity.MEDIUM
            confidence = compute_confidence_from_signals(1, 3, 1 if no_action > 120 else 0)
            findings.append(Finding.create(
                finding_type=FindingType.LOST_ORDER,
                severity=severity,
                confidence=confidence if no_action < 60 else min(confidence + 0.10, 1.0),
                agent_type=self.agent_type,
                title="丢单: 订单无支付记录",
                detail=f"订单创建{no_action}分钟后无任何支付发起",
                evidence=[
                    Evidence(source="order", field="state", expected="paid", actual=order.order.state.value),
                    Evidence(source="order", field="payments_count", expected=">=1", actual="0"),
                ],
                suggestion=(
                    "关闭订单通知用户重下单" if no_action > 120
                    else "发送支付提醒通知" if no_action > 30
                    else "观察中暂不干预"
                ),
            ))

        if order.metadata.get("suspicious_ip"):
            findings.append(Finding.create(
                finding_type=FindingType.IP_ANOMALY,
                severity=Severity.MEDIUM,
                confidence=0.75,
                agent_type=self.agent_type,
                title="丢单伴随可疑IP",
                detail="订单无支付记录且来源IP可疑，疑似探测行为",
                evidence=[Evidence(source="metadata", field="suspicious_ip", expected="false", actual="true")],
                suggestion="标记为可疑探测，加入观察名单",
            ))

        return findings

    # ------------------------------------------------------------------
    # 单笔支付诊断
    # ------------------------------------------------------------------

    def _diagnose_payment(self, order: MockOrder, payment: PaymentRecord) -> List[Finding]:
        findings = []

        # 支付超时 → 掉单
        if payment.state == PaymentState.TIMEOUT:
            findings.append(Finding.create(
                finding_type=FindingType.DROPPED_ORDER,
                severity=Severity.HIGH,
                confidence=0.88,
                agent_type=self.agent_type,
                title=f"掉单: 渠道{payment.channel.value}支付超时",
                detail=f"支付 {payment.payment_id} 超时未完成",
                evidence=[
                    Evidence(source="payment", field="state", expected="success", actual="timeout"),
                    Evidence(source="payment", field="channel", actual=payment.channel.value),
                ],
                suggestion=f"主动查询{payment.channel.value}订单 {payment.channel_order_no or 'N/A'}，确认是否已扣款",
                metadata={"payment_id": payment.payment_id, "channel": payment.channel.value},
            ))

        # 支付失败
        if payment.state == PaymentState.FAILED:
            raw = payment.raw_channel_response
            err_msg = raw.get("msg", raw.get("error", "未知错误"))
            retryable = raw.get("code") == "UNKNOWN"
            findings.append(Finding.create(
                finding_type=FindingType.PAYMENT_FAILED,
                severity=Severity.MEDIUM if retryable else Severity.LOW,
                confidence=0.85,
                agent_type=self.agent_type,
                title=f"支付失败: {err_msg}",
                detail=f"渠道{payment.channel.value}返回失败: {err_msg}",
                evidence=[
                    Evidence(source="payment", field="state", expected="success", actual="failed"),
                    Evidence(source="channel", field="response", actual=str(raw)),
                ],
                suggestion="建议重试支付或切换渠道" if retryable else f"通知用户更换支付方式 ({err_msg})",
                metadata={"payment_id": payment.payment_id, "retryable": retryable},
            ))

        # 支付成功但回调丢失 → 掉单
        if payment.state == PaymentState.SUCCESS and not payment.callback_received:
            gap = order.metadata.get("gap_minutes", 0)
            findings.append(Finding.create(
                finding_type=FindingType.CALLBACK_MISSING,
                severity=Severity.HIGH,
                confidence=0.92,
                agent_type=self.agent_type,
                title=f"回调丢失: 渠道{payment.channel.value}已扣款但未通知",
                detail=f"支付成功{gap}分钟后仍未收到回调",
                evidence=[
                    Evidence(source="payment", field="callback_received", expected="true", actual="false"),
                    Evidence(source="payment", field="paid_at", actual=payment.paid_at or "unknown"),
                ],
                suggestion=f"立即补单: 以渠道{payment.channel.value}扣款记录为准更新订单状态",
                metadata={"payment_id": payment.payment_id, "gap_minutes": gap},
            ))

        # 处理中超时
        if payment.state == PaymentState.PROCESSING and order.metadata.get("gap_minutes", 0) > 30:
            findings.append(Finding.create(
                finding_type=FindingType.PAYMENT_TIMEOUT,
                severity=Severity.MEDIUM,
                confidence=0.70,
                agent_type=self.agent_type,
                title="支付处理中超过30分钟",
                detail="可能存在掉单风险，需主动查询",
                evidence=[Evidence(source="payment", field="state", expected="success", actual="processing")],
                suggestion=f"主动查询{payment.channel.value}订单状态",
                metadata={"payment_id": payment.payment_id},
            ))

        return findings

    # ------------------------------------------------------------------
    # 状态一致性
    # ------------------------------------------------------------------

    def _check_state_consistency(self, order: MockOrder) -> List[Finding]:
        findings = []
        order_state = order.order.state

        if not order.payments:
            if order_state in (OrderState.PAID, OrderState.PROCESSING, OrderState.SHIPPED, OrderState.COMPLETED):
                findings.append(Finding.create(
                    finding_type=FindingType.STATE_INCONSISTENCY,
                    severity=Severity.HIGH,
                    confidence=0.90,
                    agent_type=self.agent_type,
                    title="订单状态与支付记录不一致",
                    detail=f"订单状态为{order_state.value}但无任何支付记录",
                    evidence=[
                        Evidence(source="order", field="state", actual=order_state.value),
                        Evidence(source="order", field="payments_count", expected=">=1", actual="0"),
                    ],
                ))
            return findings

        for payment in order.payments:
            if not self._is_valid_pair(order_state, payment.state):
                findings.append(Finding.create(
                    finding_type=FindingType.STATE_INCONSISTENCY,
                    severity=Severity.HIGH if payment.state in (PaymentState.TIMEOUT, PaymentState.FAILED) else Severity.MEDIUM,
                    confidence=0.88,
                    agent_type=self.agent_type,
                    title=f"订单-支付状态组合异常: {order_state.value} + {payment.state.value}",
                    detail=f"订单状态{order_state.value}与支付状态{payment.state.value}不匹配",
                    evidence=[
                        Evidence(source="order", field="state", actual=order_state.value),
                        Evidence(source="payment", field="state", actual=payment.state.value),
                    ],
                    metadata={"payment_id": payment.payment_id},
                ))

        return findings

    def _is_valid_pair(self, order_state: OrderState, payment_state: PaymentState) -> bool:
        valid = {
            (OrderState.CREATED, PaymentState.PENDING),
            (OrderState.CREATED, PaymentState.PROCESSING),
            (OrderState.PAID, PaymentState.SUCCESS),
            (OrderState.PROCESSING, PaymentState.SUCCESS),
            (OrderState.SHIPPED, PaymentState.SUCCESS),
            (OrderState.COMPLETED, PaymentState.SUCCESS),
            (OrderState.CANCELLED, PaymentState.REFUNDED),
            (OrderState.REFUNDED, PaymentState.REFUNDED),
        }
        return (order_state, payment_state) in valid

    # ------------------------------------------------------------------
    # 跨字段
    # ------------------------------------------------------------------

    def _check_cross_field(self, order: MockOrder) -> List[Finding]:
        findings = []
        meta = order.metadata
        gap = meta.get("gap_minutes", 0)

        if gap > 60:
            findings.append(Finding.create(
                finding_type=FindingType.CALLBACK_MISSING,
                severity=Severity.HIGH,
                confidence=0.78,
                agent_type=self.agent_type,
                title=f"支付回调延迟{gap}分钟",
                detail="支付成功后长时间未收到回调，疑似掉单",
                suggestion="排查回调链路并手动补单",
            ))

        # 字段缺失
        if not order.order.user_id:
            findings.append(Finding.create(
                finding_type=FindingType.FIELD_MISSING,
                severity=Severity.HIGH,
                confidence=0.99,
                agent_type=self.agent_type,
                title="缺少用户ID",
                detail="订单未关联用户",
                evidence=[Evidence(source="order", field="user_id", expected="non-empty", actual="empty")],
            ))

        if order.order.order_amount <= 0:
            findings.append(Finding.create(
                finding_type=FindingType.FIELD_INVALID,
                severity=Severity.CRITICAL,
                confidence=0.99,
                agent_type=self.agent_type,
                title="订单金额无效",
                detail=f"订单金额为{order.order.order_amount}",
                evidence=[Evidence(source="order", field="order_amount", actual=str(order.order.order_amount))],
            ))

        return findings
