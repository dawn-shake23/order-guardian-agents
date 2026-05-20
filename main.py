# Load .env before anything else
import os as _os
from pathlib import Path as _Path
_env = _Path(__file__).resolve().parent / ".env"
if _env.exists():
    with open(_env, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip())

import sys
import uuid
import time
import json

from config import SystemConfig, ChunkConfig
from memory.memory_hub import MemoryHub
from memory.embedding import EmbeddingProvider
from memory.chunking import DocumentChunker
from infrastructure.kb_loader import KnowledgeBaseLoader
from infrastructure.fake_data import init_mock_data, KNOWLEDGE_BASE, EXPERT_CASES
from tools.tool_lifecycle import ToolLifeCycleManager
from MCP.mcp_gateway import MCPGateway
from agents.coordinator import Coordinator
from agents.plan_agent import PlanAgent
from agents import (
    OrderAgent, PaymentAgent, RiskAgent, ReconciliationAgent, OperationAgent,
)
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics, MockMQ
from infrastructure.resilience import (
    CircuitBreaker, RateLimiter, HeartbeatMonitor, ConcurrencyController,
)
from infrastructure.decision_engine import DecisionEngine, RuleEngine
from infrastructure.approval import ApprovalEngine
from infrastructure.state_persistence import StatePersistence, CheckpointManager
from infrastructure.agent_pool import AgentPool
from core.tracing import init_tracing
from core.logger import get_logger
from core.errors import OrderGuardianError

logger = get_logger("main")
CFG = SystemConfig()


def _load_business_data(mock_db, mock_rag):
    data_dir = CFG.data_dir
    files = {"orders": "orders.json", "payments": "payments.json",
             "risks": "risks.json", "reconciliations": "reconciliations.json"}
    for table, fname in files.items():
        path = _os.path.join(data_dir, fname)
        if _os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                records = json.load(f)
            for pk, record in records.items():
                mock_db.insert(table, pk, record)
            logger.info(f"  {table}: {len(records)} records")
    if not _os.path.exists(_os.path.join(data_dir, "orders.json")):
        init_mock_data(mock_db, mock_rag)
    logger.info(f"  totals: orders={mock_db.count('orders')} payments={mock_db.count('payments')} "
                f"risks={mock_db.count('risks')} reconciliations={mock_db.count('reconciliations')}")


def _load_knowledge_base(kb_loader):
    kb_path = _os.path.join(CFG.knowledge_base_dir, "knowledge_base.json")
    if _os.path.exists(kb_path):
        with open(kb_path, "r", encoding="utf-8") as f:
            kb_records = json.load(f)
        kb_docs = list(kb_records.values()) if isinstance(kb_records, dict) else kb_records
        return kb_loader.load(kb_docs, cases=None)
    return kb_loader.load(KNOWLEDGE_BASE, EXPERT_CASES)


def _try_load_faiss(memory_hub):
    """Attempt to load persisted FAISS index; returns True if loaded."""
    p = CFG.persistence
    if memory_hub.vector_store.load(index_dir=p.vector_index_dir,
                                     index_file=p.vector_index_file,
                                     metadata_file=p.metadata_file):
        logger.info(f"  FAISS loaded from disk: {len(memory_hub.vector_store)} vectors")
        return True
    return False


def _save_faiss(memory_hub):
    p = CFG.persistence
    memory_hub.vector_store.save(index_dir=p.vector_index_dir,
                                  index_file=p.vector_index_file,
                                  metadata_file=p.metadata_file)
    logger.info(f"  FAISS saved to disk: {len(memory_hub.vector_store)} vectors")


def init_system():
    logger.info("=" * 60)
    logger.info("Order Guardian Agents - starting")
    logger.info("=" * 60)

    logger.info("[1/10] tracing")
    init_tracing()

    logger.info("[2/10] memory hub")
    memory_hub = MemoryHub()

    logger.info("[3/10] mock infrastructure")
    mock_db = MockDB(persist_path=CFG.persistence.db_path)
    mock_rag = MockRAG()
    mock_mq = MockMQ()
    mock_metrics = MockMetrics()

    logger.info("[4/10] embedding")
    embedding_provider = EmbeddingProvider(dim=CFG.embedding.dim)
    logger.info(f"  backend: {embedding_provider.backend}")

    logger.info("[4.1/10] business data")
    _load_business_data(mock_db, mock_rag)

    logger.info("[4.5/10] knowledge base")
    kb_loader = KnowledgeBaseLoader(
        memory_hub=memory_hub,
        embedding_provider=embedding_provider,
        enable_chunking=True,
        chunk_config=ChunkConfig(chunk_size=CFG.chunk.chunk_size,
                                 chunk_overlap=CFG.chunk.chunk_overlap),
    )

    if _try_load_faiss(memory_hub):
        logger.info("  skipping rebuild (loaded from disk)")
    else:
        kb_result = _load_knowledge_base(kb_loader)
        logger.info(f"  docs={kb_result['total_documents']} chunks={kb_result['total_chunks']} "
                    f"vectors={kb_result['vector_store_size']} failed={kb_result['failed']} "
                    f"time={kb_result['duration_ms']:.0f}ms")
        _save_faiss(memory_hub)

    logger.info("[5/10] resilience")
    circuit_breakers = {}
    rate_limiters = {}
    for name in ["order", "payment", "risk", "reconciliation", "operation"]:
        circuit_breakers[name] = CircuitBreaker(name, failure_threshold=3, recovery_timeout=10)
        rate_limiters[name] = RateLimiter(name, max_requests=50, window_seconds=60)
    heartbeat = HeartbeatMonitor(interval_seconds=10)
    concurrency = ConcurrencyController(max_concurrent=5)

    logger.info("[6/10] decision engine")
    rule_engine = RuleEngine()
    decision_engine = DecisionEngine(rule_engine)
    approval_engine = ApprovalEngine()

    logger.info("[7/10] state persistence")
    state_persistence = StatePersistence(persist_dir=CFG.persistence.state_dir)
    checkpoint_manager = CheckpointManager(state_persistence)

    logger.info("[8/10] agent pool")
    agent_pool = AgentPool(max_per_type=3)

    logger.info("[9/10] tools + MCP")
    ToolLifeCycleManager.global_init(memory_hub)
    mcp = MCPGateway(memory_hub)

    logger.info("[10/10] expert agents")
    agent_map = {}
    for name, cls in [("order", OrderAgent), ("payment", PaymentAgent),
                       ("risk", RiskAgent), ("reconciliation", ReconciliationAgent),
                       ("operation", OperationAgent)]:
        agent_map[name] = cls(
            memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
            metrics=mock_metrics,
            circuit_breaker=circuit_breakers[name],
            rate_limiter=rate_limiters[name],
        )
        agent_pool.register(name, agent_map[name])

    plan_agent = PlanAgent(
        memory_hub=memory_hub, metrics=mock_metrics,
        circuit_breaker=CircuitBreaker("plan", failure_threshold=3),
        rate_limiter=RateLimiter("plan", max_requests=20, window_seconds=60),
    )

    coordinator = Coordinator(
        mcp=mcp, memory_hub=memory_hub, mock_db=mock_db, mock_rag=mock_rag,
        metrics=mock_metrics, mock_mq=mock_mq,
        decision_engine=decision_engine, approval_engine=approval_engine,
        state_persistence=state_persistence, agent_pool=agent_pool,
        concurrency_controller=concurrency,
    )

    for name in ["coordinator", "order_agent", "payment_agent", "risk_agent",
                 "reconciliation_agent", "operation_agent"]:
        heartbeat.register(name)
        heartbeat.beat(name)
    heartbeat.start(on_unhealthy=lambda n, i: logger.warning("heartbeat", extra={"c": n}))

    logger.info("init complete")
    return {
        "coordinator": coordinator, "plan_agent": plan_agent, "mcp": mcp,
        "memory_hub": memory_hub, "agent_map": agent_map,
        "mock_db": mock_db, "mock_rag": mock_rag, "mock_mq": mock_mq,
        "mock_metrics": mock_metrics, "heartbeat": heartbeat,
        "circuit_breakers": circuit_breakers, "rate_limiters": rate_limiters,
        "decision_engine": decision_engine, "approval_engine": approval_engine,
        "state_persistence": state_persistence, "checkpoint_manager": checkpoint_manager,
        "agent_pool": agent_pool, "concurrency": concurrency,
        "embedding_provider": embedding_provider, "kb_loader": kb_loader,
    }


def run_task(system, order_id, abnormal_detail=""):
    coordinator = system["coordinator"]
    plan_agent = system["plan_agent"]
    agent_map = system["agent_map"]
    heartbeat = system["heartbeat"]
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    heartbeat.beat("coordinator")

    plan_result = plan_agent.run({
        "session_id": session_id, "order_id": order_id,
        "abnormal_detail": abnormal_detail,
    })
    plan_result["session_id"] = session_id
    plan_result["order_id"] = order_id

    print(f"\n{'='*60}")
    print(f"  Task: {order_id} - {abnormal_detail}")
    print(f"{'='*60}")
    print(f"  session: {session_id}")
    for step in plan_result.get("steps", []):
        deps = step.get("depends_on", [])
        print(f"    step {step['step_id']}: [{step['expert_type']}] {step['goal']}"
              + (f" (deps: {deps})" if deps else ""))

    final_report = coordinator.execute(plan_result, agent_map)
    heartbeat.beat("coordinator")

    print(f"\n  Result:")
    print(f"    success : {final_report['plan_success']}")
    print(f"    risk    : {final_report['risk_level']}")
    print(f"    decision: {final_report.get('decision_type', 'N/A')}")
    print(f"    conf    : {final_report.get('decision_confidence', 0):.0%}")
    print(f"    root    : {final_report['abnormal_root_cause']}")
    print(f"    solution: {final_report['solution']}")
    print(f"    time    : {final_report.get('total_duration_ms', 0):.1f}ms")

    for step in final_report.get("expert_steps", []):
        icon = "OK" if step.get("status") == "completed" else "FAIL"
        print(f"    [{icon}] step {step.get('step_id', '?')} [{step.get('expert_type', '?')}] "
              f"{step.get('goal', '?')} ({step.get('duration_ms', 0):.1f}ms)")
        result = step.get("result", {})
        if isinstance(result, dict):
            for k, v in result.items():
                if k in ("rule_ref", "all_payments"):
                    continue
                if v is not None:
                    vs = str(v)
                    if len(vs) > 100:
                        vs = vs[:100] + "..."
                    print(f"         {k}: {vs}")

    return final_report


def _run_preset_scenarios(system):
    scenarios = [
        ("ORD00001", "payment timeout, callback not received"),
        ("ORD00003", "high risk block, blacklist user"),
        ("ORD00002", "order status verification"),
    ]
    for order_id, detail in scenarios:
        run_task(system, order_id, detail)
    _print_status(system)
    system["heartbeat"].stop()
    print(f"\n{'='*60}")
    print(f"  auto-run complete.")
    print(f"{'='*60}")


def _print_status(system):
    print(f"\n{'='*60}")
    print(f"  System Status")
    print(f"{'='*60}")
    metrics = system["mock_metrics"]
    snap = metrics.snapshot()
    for k, v in sorted(snap["counters"].items()):
        print(f"  counter.{k}: {v:.0f}")
    for name, cb in system["circuit_breakers"].items():
        st = cb.get_state()
        print(f"  breaker.{name}: {st['state']} (fails={st['failure_count']})")
    health = system["heartbeat"].check_health()
    for name, info in health.items():
        print(f"  heartbeat.{name}: {info['status']}")


def main():
    interactive_mode = "--interactive" in sys.argv
    system = init_system()

    if interactive_mode:
        print(f"\n{'='*60}")
        print(f"  System initialized. Ready for interaction.")
        print(f"{'='*60}")
        from tools.interactive import run_interactive
        run_interactive(system)
    else:
        _run_preset_scenarios(system)


if __name__ == "__main__":
    try:
        main()
    except OrderGuardianError as e:
        logger.error(f"OrderGuardianError: {e.error_code.value} - {e.message}", extra=e.extra)
    except Exception as e:
        logger.error(f"Unexpected: {e}", exc_info=True)
