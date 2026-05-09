"""
order-guardian — 支付域多 Agent 协同订单守护系统

流程:
  Mock 订单 → 意图分类 → 向量检索 → 按意图调度 Agent → 聚合 → 路由决策

Agent 调度（按意图按需执行，非全量:
  payment_integrity  — 支付完整性（掉单/丢单/回调/状态一致性）
  reconciliation    — 对账（金额核算/重复支付/渠道异常）
  risk              — 风控（IP/设备/时间/金额/频率/退款）

路由规则:
  CRITICAL           → MANUAL_REVIEW 强制人工
  confidence >= 0.80 → AUTO_APPROVE
  confidence 0.5-0.8 → AUTO_FIX
  confidence < 0.50  → MANUAL_REVIEW

预留组件 (Mock 占位，接口一致):
  IntentClassifier   → 小模型意图分类
  VectorRetriever     → 小模型向量检索
  MCP Gateway         → 权限/上下文/工具鉴权
  Sandbox             → Agent 隔离执行
  MemoryHub           → 双层存储 + 断点
"""
import uuid

from dotenv import load_dotenv

load_dotenv(override=False)

from core.tracing import init_tracing, trace_coordinator
from core.logger import get_logger
from core.errors import OrderGuardianError

from models.mock_orders import ALL_MOCK_ORDERS, get_dataset_summary
from agents.coordinator import Coordinator, RoutingDecision

logger = get_logger("main")


def init_system() -> Coordinator:
    logger.info("初始化追踪系统")
    init_tracing()
    logger.info("初始化 Coordinator（含 IntentClassifier + VectorRetriever + 3 Agent）")
    return Coordinator()


def sep(title: str, ch: str = "=", w: int = 70) -> None:
    print(f"\n{ch * w}\n  {title}\n{ch * w}\n")


def run_single(coordinator: Coordinator, order, session_id: str):
    with trace_coordinator(session_id, order.order.order_id, plan_steps=3) as root:
        report = coordinator.execute(order, session_id)
        root.end(outputs={
            "order_id": report.order_id,
            "routing": report.routing,
            "confidence": report.overall_confidence,
        })
    return report


def run_all(coordinator: Coordinator) -> dict:
    total = len(ALL_MOCK_ORDERS)
    counts = {r.value: 0 for r in RoutingDecision}
    detail = {r.value: [] for r in RoutingDecision}

    sep("order-guardian 支付域多 Agent 协同订单守护系统")
    print(f"  测试数据集: {total} 条 | 分布: {get_dataset_summary()}")
    print(f"  流程: 意图分类 → 向量检索 → Agent 调度 → 聚合 → 路由")
    sep("逐条处理", "-")

    for idx, order in enumerate(ALL_MOCK_ORDERS, 1):
        sid = f"session_{uuid.uuid4().hex[:8]}"

        print(f"[{idx:2d}/{total}] {order.order.order_id}")
        print(f"  类型: {order.anomaly_type.value:20s} | {order.description[:50]}")
        print(f"  金额: {order.order.order_amount:>10.2f} | 状态: {order.order.state.value:10s} | 支付: {len(order.payments)}笔")

        report = run_single(coordinator, order, sid)

        # 意图
        intent = report.intent or {}
        print(f"  意图: {intent.get('primary_intent', '?'):20s} → 调度: {report.agents_dispatched}")

        # Agent 结果
        for name, ar in (report.agent_reports or {}).items():
            passed = ar.get("passed", False)
            conf = ar.get("overall_confidence", 0)
            findings_count = len(ar.get("findings", []))
            issues = sum(1 for f in ar.get("findings", []) if f.get("finding_type") != "normal")
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name:25s} conf={conf:.2%}  findings={findings_count}  issues={issues}")

        # 路由
        routing = RoutingDecision(report.routing)
        label = {"auto_approve": "[自动放行]", "auto_fix": "[自动修复]", "manual_review": "[人工差错池]"}[routing.value]
        print(f"  >>> {label}  risk={report.risk_level:8s}  conf={report.overall_confidence:.2%}")
        print(f"  >>> {report.routing_reason[:120]}")

        # 修复建议
        if report.aggregated_suggestions:
            for s in report.aggregated_suggestions[:2]:
                print(f"      → {s[:100]}")

        counts[report.routing] += 1
        detail[report.routing].append({
            "order_id": report.order_id,
            "type": report.anomaly_type,
            "confidence": report.overall_confidence,
            "risk": report.risk_level,
        })
        print()

    return {"total": total, "counts": counts, "detail": detail}


def print_summary(stats: dict) -> None:
    sep("全量处理完成 — 统计摘要")
    t = stats["total"]
    c = stats["counts"]
    for r in RoutingDecision:
        n = c.get(r.value, 0)
        print(f"  {r.value:20s} {n:>4}  ({n/t*100:.1f}%)")

    mr = stats["detail"].get("manual_review", [])
    if mr:
        print(f"\n  人工差错池明细:")
        for item in mr:
            print(f"    {item['order_id']}  {item['type']:20s}  conf={item['confidence']:.2%}  risk={item['risk']}")


if __name__ == "__main__":
    try:
        coordinator = init_system()
        stats = run_all(coordinator)
        print_summary(stats)
    except OrderGuardianError as e:
        logger.error(f"OrderGuardianError: {e.error_code.value} - {e.message}", extra=e.extra)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
