import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class DecisionType(str, Enum):
    AUTO_RESOLVE = "auto_resolve"
    MANUAL_REVIEW = "manual_review"
    ESCALATE = "escalate"
    COMPENSATE = "compensate"
    REFUND = "refund"
    RETRY = "retry"


class DecisionResult(BaseModel):
    decision_type: DecisionType
    confidence: float = Field(ge=0, le=1)
    root_cause: str
    solution: str
    risk_level: str
    needs_approval: bool = False
    fallback_rule: Optional[str] = None
    reasoning: List[str] = Field(default_factory=list)


class RuleEngine:
    RULES = {
        "E2001": {
            "decision": DecisionType.COMPENSATE,
            "root_cause": "支付超时，回调未到达",
            "solution": "1.查询渠道确认支付状态；2.已扣款则补单；3.未扣款则关闭订单",
            "risk_level": "medium",
            "needs_approval": False,
        },
        "E2002": {
            "decision": DecisionType.AUTO_RESOLVE,
            "root_cause": "用户余额不足",
            "solution": "1.标记支付失败；2.通知用户更换支付方式；3.保留订单24小时",
            "risk_level": "low",
            "needs_approval": False,
        },
        "E2003": {
            "decision": DecisionType.ESCALATE,
            "root_cause": "支付渠道异常",
            "solution": "1.切换备用渠道；2.上报渠道异常；3.触发健康检查",
            "risk_level": "high",
            "needs_approval": True,
        },
        "E2004": {
            "decision": DecisionType.RETRY,
            "root_cause": "支付已退回",
            "solution": "1.更新订单状态为待支付；2.通知用户重新支付；3.30分钟未支付则关闭",
            "risk_level": "medium",
            "needs_approval": False,
        },
        "E2005": {
            "decision": DecisionType.COMPENSATE,
            "root_cause": "支付回调丢失",
            "solution": "1.主动查询渠道；2.已成功则补发回调；3.未成功则标记失败",
            "risk_level": "medium",
            "needs_approval": False,
        },
        "E3001": {
            "decision": DecisionType.MANUAL_REVIEW,
            "root_cause": "风控拦截-高风险",
            "solution": "1.冻结订单；2.人工审核；3.审核通过后放行",
            "risk_level": "high",
            "needs_approval": True,
        },
        "E3002": {
            "decision": DecisionType.REFUND,
            "root_cause": "风控拦截-黑名单",
            "solution": "1.直接拒绝交易；2.如已扣款则退款；3.记录黑名单事件",
            "risk_level": "high",
            "needs_approval": True,
        },
        "E3004": {
            "decision": DecisionType.MANUAL_REVIEW,
            "root_cause": "对账不一致-金额差异",
            "solution": "1.标记差异记录；2.重试对账3次；3.仍不一致则人工介入",
            "risk_level": "medium",
            "needs_approval": True,
        },
        "E3005": {
            "decision": DecisionType.COMPENSATE,
            "root_cause": "对账不一致-状态差异",
            "solution": "1.核实支付状态；2.修正订单状态；3.记录差异日志",
            "risk_level": "low",
            "needs_approval": False,
        },
    }

    def match(self, error_code: str) -> Optional[Dict[str, Any]]:
        return self.RULES.get(error_code)


class DecisionEngine:
    def __init__(self, rule_engine: Optional[RuleEngine] = None):
        self.rule_engine = rule_engine or RuleEngine()

    def decide(self, step_results: List[Dict[str, Any]], context: Dict[str, Any]) -> DecisionResult:
        reasoning = []
        error_code = self._extract_error_code(step_results)
        risk_level = self._extract_risk_level(step_results)
        root_cause = self._extract_root_cause(step_results)

        rule_match = self.rule_engine.match(error_code) if error_code else None

        if rule_match:
            reasoning.append(f"规则引擎匹配: error_code={error_code}")
            return DecisionResult(
                decision_type=rule_match["decision"],
                confidence=0.9,
                root_cause=rule_match["root_cause"],
                solution=rule_match["solution"],
                risk_level=rule_match["risk_level"],
                needs_approval=rule_match["needs_approval"],
                fallback_rule=error_code,
                reasoning=reasoning,
            )

        reasoning.append("无精确规则匹配，走综合决策逻辑")

        if risk_level == "high":
            reasoning.append("高风险 → 人工审核")
            return DecisionResult(
                decision_type=DecisionType.MANUAL_REVIEW,
                confidence=0.6,
                root_cause=root_cause or "未知根因(高风险)",
                solution="建议人工审核确认",
                risk_level="high",
                needs_approval=True,
                reasoning=reasoning,
            )

        if risk_level == "medium":
            reasoning.append("中风险 → 补偿处理")
            return DecisionResult(
                decision_type=DecisionType.COMPENSATE,
                confidence=0.7,
                root_cause=root_cause or "未知根因(中风险)",
                solution="自动补偿处理，需后续观察",
                risk_level="medium",
                needs_approval=False,
                reasoning=reasoning,
            )

        reasoning.append("低风险 → 自动解决")
        return DecisionResult(
            decision_type=DecisionType.AUTO_RESOLVE,
            confidence=0.85,
            root_cause=root_cause or "轻微异常",
            solution="常规处理流程",
            risk_level="low",
            needs_approval=False,
            reasoning=reasoning,
        )

    def _extract_error_code(self, steps: List[Dict]) -> Optional[str]:
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                ec = result.get("error_code") or result.get("data", {}).get("error_code")
                if ec:
                    return ec
        return None

    def _extract_risk_level(self, steps: List[Dict]) -> str:
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                rl = result.get("risk_level") or result.get("data", {}).get("risk_level")
                if rl:
                    return rl
        return "low"

    def _extract_root_cause(self, steps: List[Dict]) -> Optional[str]:
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                rc = result.get("root_cause") or result.get("data", {}).get("root_cause")
                if rc:
                    return rc
        return None
