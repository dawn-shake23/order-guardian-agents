import uuid
import time
import json
from memory.memory_hub import MemoryHub
from memory.embedding import EmbeddingProvider
from memory.chunking import ChunkConfig
from infrastructure.kb_loader import KnowledgeBaseLoader
from infrastructure.fake_data import init_mock_data, KNOWLEDGE_BASE, EXPERT_CASES
from tools.tool_lifecycle import ToolLifeCycleManager
from MCP.mcp_gateway import MCPGateway
from agents.coordinator import Coordinator
from agents.plan_agent import PlanAgent
from agents import (
    OrderAgent,
    PaymentAgent,
    RiskAgent,
    ReconciliationAgent,
    OperationAgent,
)
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics, MockMQ, MockRedis
from infrastructure.resilience import (
    CircuitBreaker, RateLimiter, HeartbeatMonitor, ConcurrencyController
)
from infrastructure.decision_engine import DecisionEngine, RuleEngine
from infrastructure.approval import ApprovalEngine
from infrastructure.state_persistence import StatePersistence, CheckpointManager
from infrastructure.agent_pool import AgentPool
from core.tracing import init_tracing
from core.logger import get_logger
from core.errors import OrderGuardianError

logger = get_logger("main")


def init_system():
    logger.info("=" * 60)
    logger.info("Order Guardian Agents - 工业级订单异常治理系统")
    logger.info("=" * 60)

    logger.info("[1/10] 初始化追踪系统")
    init_tracing()

    logger.info("[2/10] 初始化记忆中心")
    memory_hub = MemoryHub()

    logger.info("[3/10] 初始化Mock基础设施")
    mock_db = MockDB(persist_path="./data/mock_db.json")
    mock_rag = MockRAG()
    mock_mq = MockMQ()
    mock_metrics = MockMetrics()

    logger.info("[4/10] 初始化Fake数据（结构化库）")
    init_mock_data(mock_db, mock_rag)
    logger.info(f"  订单数: {mock_db.count('orders')}")
    logger.info(f"  支付数: {mock_db.count('payments')}")
    logger.info(f"  风控数: {mock_db.count('risks')}")
    logger.info(f"  对账数: {mock_db.count('reconciliations')}")

    logger.info("[4.5/10] 初始化Embedding与向量知识库")
    embedding_provider = EmbeddingProvider(dim=1024)
    logger.info(f"  Embedding后端: {embedding_provider.backend}")

    kb_loader = KnowledgeBaseLoader(
        memory_hub=memory_hub,
        embedding_provider=embedding_provider,
        enable_chunking=False  # 小知识库不分块，直接用全文embedding
    )
    kb_result = kb_loader.load(KNOWLEDGE_BASE, EXPERT_CASES)
    logger.info(f"  知识库文档: {kb_result['total_documents']}条")
    logger.info(f"  专家案例: {kb_result['total_cases']}条")
    logger.info(f"  向量库大小: {kb_result['vector_store_size']}条")
    logger.info(f"  跳过去重: {kb_result['skipped_duplicate']}条")
    logger.info(f"  加载耗时: {kb_result['duration_ms']:.1f}ms")

    logger.info("[5/10] 初始化韧性系统")
    circuit_breakers = {
        "order": CircuitBreaker("order", failure_threshold=3, recovery_timeout=10),
        "payment": CircuitBreaker("payment", failure_threshold=3, recovery_timeout=10),
        "risk": CircuitBreaker("risk", failure_threshold=3, recovery_timeout=10),
        "reconciliation": CircuitBreaker("reconciliation", failure_threshold=3, recovery_timeout=10),
        "operation": CircuitBreaker("operation", failure_threshold=3, recovery_timeout=10),
    }
    rate_limiters = {
        "order": RateLimiter("order", max_requests=50, window_seconds=60),
        "payment": RateLimiter("payment", max_requests=50, window_seconds=60),
        "risk": RateLimiter("risk", max_requests=30, window_seconds=60),
        "reconciliation": RateLimiter("reconciliation", max_requests=30, window_seconds=60),
        "operation": RateLimiter("operation", max_requests=30, window_seconds=60),
    }
    heartbeat = HeartbeatMonitor(interval_seconds=10)
    concurrency = ConcurrencyController(max_concurrent=5)

    logger.info("[6/10] 初始化决策引擎与审批流")
    rule_engine = RuleEngine()
    decision_engine = DecisionEngine(rule_engine)
    approval_engine = ApprovalEngine()

    logger.info("[7/10] 初始化状态持久化")
    state_persistence = StatePersistence(persist_dir="./state_checkpoints")
    checkpoint_manager = CheckpointManager(state_persistence)

    logger.info("[8/10] 初始化Agent池")
    agent_pool = AgentPool(max_per_type=3)

    logger.info("[9/10] 初始化工具体系与MCP")
    ToolLifeCycleManager.global_init(memory_hub)
    mcp = MCPGateway(memory_hub)

    logger.info("[10/10] 初始化专家Agent（DI注入）")
    agent_map = {
        "order": OrderAgent(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers["order"],
            rate_limiter=rate_limiters["order"]
        ),
        "payment": PaymentAgent(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers["payment"],
            rate_limiter=rate_limiters["payment"]
        ),
        "risk": RiskAgent(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers["risk"],
            rate_limiter=rate_limiters["risk"]
        ),
        "reconciliation": ReconciliationAgent(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers["reconciliation"],
            rate_limiter=rate_limiters["reconciliation"]
        ),
        "operation": OperationAgent(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers["operation"],
            rate_limiter=rate_limiters["operation"]
        ),
    }

    for agent_type, agent in agent_map.items():
        agent_pool.register(agent_type, agent)

    plan_agent = PlanAgent(
        memory_hub=memory_hub,
        metrics=mock_metrics,
        circuit_breaker=CircuitBreaker("plan", failure_threshold=3),
        rate_limiter=RateLimiter("plan", max_requests=20, window_seconds=60)
    )

    coordinator = Coordinator(
        mcp=mcp,
        memory_hub=memory_hub,
        mock_db=mock_db,
        mock_rag=mock_rag,
        metrics=mock_metrics,
        mock_mq=mock_mq,
        decision_engine=decision_engine,
        approval_engine=approval_engine,
        state_persistence=state_persistence,
        agent_pool=agent_pool,
        concurrency_controller=concurrency
    )

    heartbeat.register("coordinator")
    heartbeat.register("order_agent")
    heartbeat.register("payment_agent")
    heartbeat.register("risk_agent")
    for name in ["coordinator", "order_agent", "payment_agent", "risk_agent",
                  "reconciliation_agent", "operation_agent"]:
        heartbeat.beat(name)
    heartbeat.start(on_unhealthy=lambda n, i: logger.warning("心跳异常", extra={"component": n, "info": i}))

    logger.info("系统初始化完成！所有组件就绪。")

    return {
        "coordinator": coordinator,
        "plan_agent": plan_agent,
        "mcp": mcp,
        "memory_hub": memory_hub,
        "agent_map": agent_map,
        "mock_db": mock_db,
        "mock_rag": mock_rag,
        "mock_mq": mock_mq,
        "mock_metrics": mock_metrics,
        "heartbeat": heartbeat,
        "circuit_breakers": circuit_breakers,
        "rate_limiters": rate_limiters,
        "decision_engine": decision_engine,
        "approval_engine": approval_engine,
        "state_persistence": state_persistence,
        "checkpoint_manager": checkpoint_manager,
        "agent_pool": agent_pool,
        "concurrency": concurrency,
        "embedding_provider": embedding_provider,
        "kb_loader": kb_loader,
    }


def run_task(system, order_id, abnormal_detail="支付超时"):
    coordinator = system["coordinator"]
    plan_agent = system["plan_agent"]
    agent_map = system["agent_map"]
    heartbeat = system["heartbeat"]
    mock_metrics = system["mock_metrics"]

    session_id = f"sess_{uuid.uuid4().hex[:8]}"

    heartbeat.beat("coordinator")

    plan_result = plan_agent.run({
        "session_id": session_id,
        "order_id": order_id,
        "abnormal_detail": abnormal_detail
    })

    plan_result["session_id"] = session_id
    plan_result["order_id"] = order_id

    print(f"\n{'='*60}")
    print(f"  订单异常治理任务")
    print(f"{'='*60}")
    print(f"  Session: {session_id}")
    print(f"  Order:   {order_id}")
    print(f"  异常描述: {abnormal_detail}")
    print(f"  规划步骤: {len(plan_result.get('steps', []))}步")
    for step in plan_result.get("steps", []):
        deps = step.get("depends_on", [])
        print(f"    Step {step['step_id']}: [{step['expert_type']}] {step['goal']}"
              + (f" (依赖: {deps})" if deps else ""))

    final_report = coordinator.execute(plan_result, agent_map)

    heartbeat.beat("coordinator")

    print(f"\n{'='*60}")
    print(f"  最终会诊报告")
    print(f"{'='*60}")
    print(f"  执行状态: {'成功' if final_report['plan_success'] else '失败'}")
    print(f"  风险等级: {final_report['risk_level']}")
    print(f"  决策类型: {final_report.get('decision_type', 'N/A')}")
    print(f"  决策置信度: {final_report.get('decision_confidence', 0):.0%}")
    print(f"  需要审批: {'是' if final_report.get('needs_approval') else '否'}")
    print(f"  根因分析: {final_report['abnormal_root_cause']}")
    print(f"  解决方案: {final_report['solution']}")
    print(f"  总耗时: {final_report.get('total_duration_ms', 0):.1f}ms")

    print(f"\n  --- 专家步骤详情 ---")
    for step in final_report.get("expert_steps", []):
        status_icon = "OK" if step.get("status") == "completed" else "FAIL"
        duration = step.get("duration_ms", 0)
        print(f"  [{status_icon}] Step {step.get('step_id', '?')} "
              f"[{step.get('expert_type', '?')}] {step.get('goal', '?')}"
              f" ({duration:.1f}ms)")
        if step.get("retried"):
            print(f"       (重试成功)")
        if step.get("degraded_from"):
            print(f"       (降级自: {step['degraded_from']})")
        result = step.get("result", {})
        if isinstance(result, dict):
            for k, v in result.items():
                if k not in ("rule_ref", "all_payments") and v is not None:
                    val_str = str(v)
                    if len(val_str) > 100:
                        val_str = val_str[:100] + "..."
                    print(f"       {k}: {val_str}")

    print(f"\n  总结: {final_report['final_summary']}")

    return final_report


def print_system_status(system):
    print(f"\n{'='*60}")
    print(f"  系统状态监控")
    print(f"{'='*60}")

    metrics = system["mock_metrics"]
    snapshot = metrics.snapshot()
    print(f"\n  --- 监控指标 ---")
    print(f"  Counters:")
    for k, v in sorted(snapshot["counters"].items()):
        print(f"    {k}: {v:.0f}")
    print(f"  Histograms:")
    for k, v in sorted(snapshot["histograms"].items()):
        print(f"    {k}: avg={v['avg']:.1f}ms, max={v['max']:.1f}ms, count={v['count']}")

    print(f"\n  --- 熔断器状态 ---")
    for name, cb in system["circuit_breakers"].items():
        state = cb.get_state()
        print(f"  {name}: {state['state']} (failures={state['failure_count']})")

    print(f"\n  --- 限流器状态 ---")
    for name, rl in system["rate_limiters"].items():
        status = rl.get_status()
        print(f"  {name}: {status['current_requests']}/{status['max_requests']} in {status['window_seconds']}s")

    print(f"\n  --- Agent池状态 ---")
    pool_status = system["agent_pool"].get_status()
    for name, info in pool_status.items():
        print(f"  {name}: total={info['total']}, available={info['available']}, in_use={info['in_use']}")

    print(f"\n  --- 并发控制 ---")
    conc = system["concurrency"].get_status()
    print(f"  max={conc['max_concurrent']}, active={conc['active_count']}, available={conc['available']}")

    print(f"\n  --- 心跳状态 ---")
    health = system["heartbeat"].check_health()
    for name, info in health.items():
        print(f"  {name}: {info['status']} (last beat {info['last_beat_ago']}s ago)")

    print(f"\n  --- 持久化会话 ---")
    sessions = system["state_persistence"].list_sessions()
    print(f"  已保存会话数: {len(sessions)}")
    for sid in sessions[:5]:
        state = system["state_persistence"].load(sid)
        if state:
            print(f"    {sid}: order={state.order_id}, success={state.plan_success}")


def main():
    system = init_system()

    print(f"\n{'#'*60}")
    print(f"  场景1: 支付超时订单 (ORD00001)")
    print(f"{'#'*60}")
    run_task(system, "ORD00001", "支付超时，回调未到达")

    print(f"\n{'#'*60}")
    print(f"  场景2: 风控拦截订单 (ORD00003)")
    print(f"{'#'*60}")
    run_task(system, "ORD00003", "高风险风控拦截，黑名单用户")

    print(f"\n{'#'*60}")
    print(f"  场景3: 正常订单 (ORD00002)")
    print(f"{'#'*60}")
    run_task(system, "ORD00002", "订单状态确认")

    print(f"\n{'#'*60}")
    print(f"  场景4: PlanAgent缓存测试 (10秒内复用)")
    print(f"{'#'*60}")
    plan1 = system["plan_agent"].run({
        "session_id": "cache_test_1", "order_id": "ORD00001",
        "abnormal_detail": "支付超时"
    })
    plan2 = system["plan_agent"].run({
        "session_id": "cache_test_2", "order_id": "ORD00001",
        "abnormal_detail": "支付超时"
    })
    print(f"  同order_id两次规划: {'命中缓存' if plan1 == plan2 else '重新规划'}")

    print_system_status(system)

    system["heartbeat"].stop()

    print(f"\n{'='*60}")
    print(f"  Order Guardian Agents 运行完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        main()
    except OrderGuardianError as e:
        logger.error(f"OrderGuardianError: {e.error_code.value} - {e.message}", extra=e.extra)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
