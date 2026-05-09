"""
Coordinator — 多 Agent 协同调度中心 v2

流程:
  意图分类 → 向量检索 → MCP 鉴权 → Agent 调度 → 聚合 → 路由决策

集成点:
  - IntentClassifier: 小模型意图分类（Mock）
  - VectorRetriever: 小模型向量检索（Mock）
  - MCP Gateway: 权限/上下文/工具鉴权（预留）
  - Sandbox: Agent 隔离执行（预留）
  - MemoryHub: 双层存储 + 断点（预留）

路由规则:
  - CRITICAL 风险 → 强制人工审核
  - 重复支付 → 人工审核
  - 综合置信度 >= 0.80 → 自动放行
  - 综合置信度 0.50-0.80 → 自动修复
  - 综合置信度 < 0.50 → 人工差错池
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field

from core.tracing import traceable, trace_agent_run
from core.logger import get_logger

from models.mock_orders import MockOrder
from models.finding import Finding, Severity, AgentReport
from models.intent import IntentClassifier, IntentResult, VectorRetriever, VectorRetrievalResult

from agents.payment_integrity_agent import PaymentIntegrityAgent
from agents.reconciliation_agent import ReconciliationAgent
from agents.risk_agent import RiskAgent


class RoutingDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_FIX = "auto_fix"
    MANUAL_REVIEW = "manual_review"


class AggregatedReport(BaseModel):
    """最终会诊报告"""
    session_id: str
    order_id: str
    anomaly_type: str
    description: str

    # 意图与检索
    intent: Optional[Dict[str, Any]] = None
    vector_retrieval: Optional[Dict[str, Any]] = None

    # Agent 报告
    agent_reports: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    agents_dispatched: List[str] = Field(default_factory=list)

    # 综合
    overall_confidence: float = Field(ge=0.0, le=1.0, description="综合置信度")
    overall_risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: str = "none"

    # 路由
    routing: str = ""
    routing_reason: str = ""

    # 汇总
    all_findings: List[Dict[str, Any]] = Field(default_factory=list)
    aggregated_suggestions: List[str] = Field(default_factory=list)
    total_issues: int = 0


class Coordinator:
    """调度中心 — 集成控制平面 + Agent 编排"""

    def __init__(self):
        self.logger = get_logger("coordinator")

        # ── 控制平面组件 ──
        self.intent_classifier = IntentClassifier()
        self.vector_retriever = VectorRetriever()

        # 预留: MCP Gateway / Sandbox / MemoryHub
        self.mcp_gateway = None   # MCPGateway(memory_hub)
        self.memory_hub = None    # MemoryHub()

        # ── Agent 延迟初始化 ──
        self._agents: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Agent 工厂
    # ------------------------------------------------------------------

    def _get_agent(self, name: str):
        if name not in self._agents:
            if name == "payment_integrity":
                self._agents[name] = PaymentIntegrityAgent()
            elif name == "reconciliation":
                self._agents[name] = ReconciliationAgent()
            elif name == "risk":
                self._agents[name] = RiskAgent()
        return self._agents[name]

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    @traceable(name="coordinator:execute", run_type="chain", tags=["coordinator", "orchestration"])
    def execute(self, order: MockOrder, session_id: str) -> AggregatedReport:
        self.logger.info("Coordinator 开始调度", extra={
            "session_id": session_id, "order_id": order.order.order_id, "type": order.anomaly_type.value,
        })

        # ---- Step 0: 意图分类 ----
        intent = self.intent_classifier.classify(order)

        # ---- Step 1: 向量检索（基于重写后的查询） ----
        retrieval = self.vector_retriever.search(intent.rewritten_query, top_k=3)

        # ---- Step 2: MCP 鉴权（预留） ----
        # if self.mcp_gateway:
        #     auth = self.mcp_gateway.authorize(session_id, intent.dispatched_agents)
        #     if not auth.passed:
        #         return _denied_report(session_id, order, auth)

        # ---- Step 3: 按意图调度 Agent ----
        agent_reports: Dict[str, AgentReport] = {}
        for agent_name in intent.dispatched_agents:
            agent_reports[agent_name] = self._dispatch_agent(
                agent_name, order, session_id, intent, retrieval,
            )

        # ---- Step 4: 聚合 ----
        report = self._aggregate(session_id, order, intent, retrieval, agent_reports)

        self.logger.info("Coordinator 调度完成", extra={
            "session_id": session_id, "order_id": order.order.order_id,
            "routing": report.routing, "confidence": report.overall_confidence,
        })

        return report

    # ------------------------------------------------------------------
    # Agent 调度
    # ------------------------------------------------------------------

    def _dispatch_agent(
        self,
        agent_name: str,
        order: MockOrder,
        session_id: str,
        intent: IntentResult,
        retrieval: VectorRetrievalResult,
    ) -> AgentReport:
        """调度单个 Agent，经 MCP 鉴权和 Sandbox 隔离（预留）"""

        agent = self._get_agent(agent_name)
        context = {
            "session_id": session_id,
            "order_id": order.order.order_id,
            "intent": intent.model_dump(),
            "retrieved_rules": retrieval.relevant_rules,
            "retrieved_cases": [c.model_dump() for c in retrieval.cases],
        }

        # 预留: Sandbox 隔离
        # sandbox = self.memory_hub.create_sandbox(session_id, 0, agent_name)
        # with sandbox:

        with trace_agent_run(
            agent_type=agent_name,
            session_id=session_id,
            inputs={
                "order_id": order.order.order_id,
                "anomaly_type": order.anomaly_type.value,
                "intent": intent.primary_intent.value,
            },
        ) as span:
            if agent_name == "payment_integrity":
                report = agent.check(order, context)
            elif agent_name == "reconciliation":
                report = agent.reconcile(order, context)
            elif agent_name == "risk":
                report = agent.assess(order, context)
            else:
                report = AgentReport(agent_type=agent_name, passed=True, overall_confidence=1.0)
            span.end(outputs=report.model_dump())
            return report

    # ------------------------------------------------------------------
    # 聚合 & 路由
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        session_id: str,
        order: MockOrder,
        intent: IntentResult,
        retrieval: VectorRetrievalResult,
        agent_reports: Dict[str, AgentReport],
    ) -> AggregatedReport:
        """聚合各 Agent 的 Finding，计算综合评分和路由"""

        # ---- 收集所有 Finding ----
        all_findings: List[Finding] = []
        for report in agent_reports.values():
            all_findings.extend(report.findings)

        # ---- 提取修复建议 ----
        suggestions: List[str] = []
        for f in all_findings:
            if f.suggestion:
                suggestions.append(f.suggestion)

        # ---- 综合置信度 ----
        if agent_reports:
            overall_confidence = sum(
                r.overall_confidence for r in agent_reports.values()
            ) / len(agent_reports)
        else:
            overall_confidence = 0.98

        # ---- 综合风险评分 ----
        risk_findings = [f for f in all_findings if f.agent_type == "risk"]
        if risk_findings:
            severities = {Severity.CRITICAL: 1.0, Severity.HIGH: 0.75, Severity.MEDIUM: 0.45, Severity.LOW: 0.15, Severity.NONE: 0}
            risk_score = max(severities.get(f.severity, 0) for f in risk_findings)
        else:
            risk_score = 0.0

        # ---- 风险等级 ----
        if any(f.severity == Severity.CRITICAL for f in all_findings):
            risk_level = "critical"
        elif any(f.severity == Severity.HIGH for f in all_findings):
            risk_level = "high"
        elif any(f.severity == Severity.MEDIUM for f in all_findings):
            risk_level = "medium"
        elif any(f.severity == Severity.LOW for f in all_findings):
            risk_level = "low"
        else:
            risk_level = "none"

        # ---- 路由决策 ----
        routing, routing_reason = self._decide_routing(
            overall_confidence=overall_confidence,
            risk_level=risk_level,
            all_findings=all_findings,
            agent_reports=agent_reports,
        )

        return AggregatedReport(
            session_id=session_id,
            order_id=order.order.order_id,
            anomaly_type=order.anomaly_type.value,
            description=order.description,
            intent=intent.model_dump(),
            vector_retrieval=retrieval.model_dump(),
            agent_reports={k: v.model_dump() for k, v in agent_reports.items()},
            agents_dispatched=list(agent_reports.keys()),
            overall_confidence=round(overall_confidence, 4),
            overall_risk_score=round(risk_score, 4),
            risk_level=risk_level,
            routing=routing.value,
            routing_reason=routing_reason,
            all_findings=[f.model_dump() for f in all_findings],
            aggregated_suggestions=suggestions,
            total_issues=len([f for f in all_findings if f.finding_type != "normal"]),
        )

    def _decide_routing(
        self,
        overall_confidence: float,
        risk_level: str,
        all_findings: List[Finding],
        agent_reports: Dict[str, AgentReport],
    ) -> tuple:
        """三级路由决策"""

        # 1. CRITICAL → 强制人工
        if risk_level == "critical":
            critical_findings = [f for f in all_findings if f.severity == Severity.CRITICAL]
            return RoutingDecision.MANUAL_REVIEW, (
                f"存在{len(critical_findings)}个CRITICAL级问题，必须人工审核。"
                f"问题: {'; '.join(f.title for f in critical_findings[:3])}"
            )

        # 2. 重复支付 → 人工
        has_duplicate = any(
            f.finding_type.value == "duplicate_payment" for f in all_findings
        )
        if has_duplicate:
            return RoutingDecision.MANUAL_REVIEW, "存在重复支付/多渠道扣款，需人工确认退款"

        # 3. 置信度路由
        if overall_confidence >= 0.80:
            return RoutingDecision.AUTO_APPROVE, (
                f"综合置信度{overall_confidence:.2%}，指标良好，自动放行"
            )
        elif overall_confidence >= 0.50:
            return RoutingDecision.AUTO_FIX, (
                f"综合置信度{overall_confidence:.2%}，存在可自动修复的问题"
            )
        else:
            return RoutingDecision.MANUAL_REVIEW, (
                f"综合置信度{overall_confidence:.2%}，问题复杂无法自动判定，转入人工差错池"
            )
