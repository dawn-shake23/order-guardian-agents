# main.py
import uuid
from memory.memory_hub import MemoryHub
from tools.tool_lifecycle import ToolLifeCycleManager
from MCP.mcp_gateway import MCPGateway
from agents.coordinator import Coordinator
from agents import (
    OrderAgent,
    PaymentAgent,
    RiskAgent,
    ReconciliationAgent,
    OperationAgent
)
from core.tracing import init_tracing
from core.logger import get_logger
from core.errors import OrderGuardianError, SystemError, BusinessError, AgentError, ToolError, InputOutputError

# 初始化日志
logger = get_logger()

def init_system():
    """系统全局初始化"""
    logger.info("开始初始化系统")
    
    # 0. 初始化追踪系统
    logger.info("初始化追踪系统")
    init_tracing()
    
    # 1. 初始化记忆中心
    logger.info("初始化记忆中心")
    memory_hub = MemoryHub()

    # 2. 初始化工具体系（注册 + 生命周期 + 权限）
    logger.info("初始化工具体系")
    ToolLifeCycleManager.global_init(memory_hub)

    # 3. 初始化 MCP 控制平面
    logger.info("初始化 MCP 控制平面")
    mcp = MCPGateway(memory_hub)

    # 4. 初始化 Coordinator
    logger.info("初始化 Coordinator")
    coordinator = Coordinator(mcp, memory_hub)

    # 5. 注册所有专家 Agent
    logger.info("注册专家 Agent")
    agent_map = {
        "order": OrderAgent(memory_hub),
        "payment": PaymentAgent(memory_hub),
        "risk": RiskAgent(memory_hub),
        "reconciliation": ReconciliationAgent(memory_hub),
        "operation": OperationAgent(memory_hub),
    }
    
    logger.info("系统初始化完成")
    return coordinator, mcp, memory_hub, agent_map

def run_demo_task():
    """运行一条完整任务流程"""
    coordinator, mcp, memory_hub, agent_map = init_system()

    # 模拟任务信息
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    order_id = f"ORD{uuid.uuid4().int % 100000000:08d}"

    # 模拟执行计划（Plan 层输出结构）
    execution_plan = {
        "session_id": session_id,
        "order_id": order_id,
        "intent": {
            "raw_query": "查询订单支付状态",
            "rewritten_query": "查询订单支付状态并进行风险排查",
            "intent_type": "payment_check",
            "constraints": []
        },
        "global_analysis": {
            "order_state_analysis": "订单已创建，支付待确认",
            "risk_prejudgment": "低风险",
            "abnormal_level": "low",
            "complexity": "low",
            "data_dependencies": ["order_info", "payment_info"]
        },
        "data_requirements": {
            "order_data": ["order_id", "status", "amount"],
            "payment_data": ["payment_id", "status", "amount"],
            "risk_data": [],
            "reconciliation_data": []
        },
        "knowledge_demand": {
            "retrieval_queries": ["支付异常处理", "风险评估标准"],
            "retrieval_scenes": ["payment", "risk"],
            "knowledge_type": ["rule", "process"]
        },
        "steps": [
            {
                "step_id": 1, "expert_type": "order", "goal": "查询订单基础信息",
                "data_used": ["order_id", "status", "amount"],
                "retrieval_used": False,
                "validation_criteria": {},
                "expected_output": "订单基础信息"
            },
            {
                "step_id": 2, "expert_type": "payment", "goal": "核查支付渠道状态",
                "data_used": ["payment_id", "status", "amount"],
                "retrieval_used": True,
                "validation_criteria": {},
                "expected_output": "支付状态信息"
            },
            {
                "step_id": 3, "expert_type": "risk", "goal": "风险评估与权限校验",
                "data_used": ["order_id", "payment_status"],
                "retrieval_used": True,
                "validation_criteria": {},
                "expected_output": "风险评估结果"
            },
            {
                "step_id": 4, "expert_type": "reconciliation", "goal": "账实核对",
                "data_used": ["order_amount", "payment_amount"],
                "retrieval_used": False,
                "validation_criteria": {},
                "expected_output": "对账结果"
            },
            {
                "step_id": 5, "expert_type": "operation", "goal": "给出运营建议",
                "data_used": ["order_status", "payment_status", "risk_level"],
                "retrieval_used": False,
                "validation_criteria": {},
                "expected_output": "运营建议"
            },
        ],
        "final_goal": "完成订单异常排查并给出处理建议",
        "success_criteria": {
            "order_info_obtained": True,
            "payment_status_confirmed": True,
            "risk_assessment_completed": True,
            "reconciliation_done": True,
            "operation_suggestion_given": True
        }
    }

    logger.info("开始执行多专家协同任务", extra={"session_id": session_id, "order_id": order_id})
    print("===== 开始执行多专家协同任务 =====")
    print(f"session_id: {session_id}")
    print(f"order_id: {order_id}\n")

    # 启动 Coordinator 调度
    logger.info("启动 Coordinator 调度", extra={"session_id": session_id})
    final_report = coordinator.execute(execution_plan, agent_map)

    # 输出最终结果
    logger.info("任务执行完成，生成最终报告", extra={"session_id": session_id, "plan_success": final_report.get('plan_success', False)})
    print("\n===== 最终会诊报告 =====")
    print(f"状态: {'成功' if final_report['plan_success'] else '失败'}")
    print(f"风险等级: {final_report['risk_level']}")
    print(f"根因: {final_report['abnormal_root_cause']}")
    print(f"解决方案: {final_report['solution']}")
    print(f"总结: {final_report['final_summary']}")

def run_rag_demo(memory_hub: MemoryHub):
    """运行RAG增强功能演示"""
    import numpy as np
    from memory.storage.sync_manager import DataSyncManager, SyncOperation
    from tools.DeepSearch.deep_search import DeepSearchEngine, DeepSearchQuery
    from tools.DeepSearch.rag_pipeline import RAGPipeline
    from agents.rag_orchestrator import AgentRAGOrchestrator, ToolDecision

    print("\n" + "=" * 60)
    print("  RAG 增强功能演示")
    print("=" * 60)

    # ---- 1. 双库一致性演示 ----
    print("\n--- 1. 双库一致性：DataSyncManager ---")
    sync = memory_hub.sync()

    mock_embedding = np.random.rand(128).tolist()
    record = sync.insert(
        table="documents",
        doc_id="DOC001",
        data={"title": "支付掉单处理规范", "content": "当支付回调未到达时...", "biz_domain": "payment"},
        embedding=mock_embedding,
        metadata={"doc_id": "DOC001", "table": "documents"}
    )
    print(f"  插入同步结果: status={record.status.value}, record_id={record.record_id}")

    record = sync.soft_delete(table="documents", doc_id="DOC001", data={"title": "支付掉单处理规范", "content": "已过期"})
    print(f"  软删同步结果: status={record.status.value}")

    comp_status = sync.get_compensation_status()
    print(f"  补偿队列状态: pending={comp_status['pending_count']}")

    # ---- 2. 混合检索演示 ----
    print("\n--- 2. 混合检索：业务字段预过滤 + 向量检索 ---")
    hybrid = memory_hub.hybrid()

    memory_hub.struct_mysql.save("documents", "DOC002", {
        "doc_id": "DOC002", "title": "订单超时处理", "content": "订单超过30分钟未支付自动关闭",
        "biz_domain": "order", "is_deleted": False, "is_archived": False
    })
    memory_hub.vector_store.add(np.random.rand(128).tolist(), {
        "doc_id": "DOC002", "title": "订单超时处理", "content": "订单超过30分钟未支付自动关闭",
        "biz_domain": "order"
    })

    results = hybrid.search_with_filter(
        query_embedding=np.random.rand(128).tolist(),
        biz_domain="order",
        top_k=3
    )
    print(f"  混合检索结果数: {len(results)}")
    for r in results:
        print(f"    - {r.get('metadata', {}).get('title', 'N/A')} (distance={r.get('distance', 'N/A')})")

    # ---- 3. DeepSearch演示 ----
    print("\n--- 3. DeepSearch：多路召回 + RRF融合 + 粗排精排 ---")
    deep_search = DeepSearchEngine(hybrid)

    ds_query = DeepSearchQuery(
        raw_query="过去30天支付域掉单案例",
        biz_domain="payment",
        require_cross_validation=True,
        top_k=3
    )
    ds_results = deep_search.search(ds_query)
    print(f"  DeepSearch结果数: {len(ds_results)}")
    for r in ds_results:
        print(f"    - [{r.doc_id}] {r.title} (score={r.score:.4f}, validated={r.validated}, routes={r.source_route})")

    # ---- 4. RAG流水线演示 ----
    print("\n--- 4. RAG增强：噪声过滤 + 上下文压缩 + 结构化Prompt ---")
    rag = RAGPipeline(max_context_tokens=4000)

    mock_search_results = [
        {"metadata": {"doc_id": "D1", "title": "支付掉单处理", "content": "当支付回调未到达时，需要手动查询渠道状态并补偿", "biz_domain": "payment"}, "score": 0.8},
        {"metadata": {"doc_id": "D2", "title": "订单超时规则", "content": "订单超过30分钟未支付自动关闭", "biz_domain": "order"}, "score": 0.3},
        {"metadata": {"doc_id": "D3", "title": "风控评分标准", "content": "高风险订单需要人工审核", "biz_domain": "risk"}, "score": 0.1},
    ]
    rag_prompt = rag.process(mock_search_results, "支付掉单怎么处理", biz_domain="payment")
    print(f"  RAG Prompt长度: {len(rag_prompt)} 字符")
    print(f"  Prompt前200字: {rag_prompt[:200]}...")

    # ---- 5. Agent+RAG联动演示 ----
    print("\n--- 5. Agent+RAG联动：工具调用决策 + 记忆路由 ---")
    orchestrator = AgentRAGOrchestrator(
        memory_hub,
        deep_search_engine=deep_search,
        rag_pipeline=rag
    )

    test_queries = [
        ("payment", "过去30天支付域掉单案例"),
        ("order", "查询订单状态"),
        ("risk", "是"),
    ]

    for agent_type, query in test_queries:
        result = orchestrator.orchestrate(
            agent_type=agent_type,
            query=query,
            session_id="demo_session",
            order_id="ORD00001"
        )
        print(f"  [{agent_type}] '{query}' → action={result['action']}, reason={result['reason']}")

    print("\n" + "=" * 60)
    print("  RAG 增强功能演示完成")
    print("=" * 60)

if __name__ == "__main__":
    try:
        coordinator, mcp, memory_hub, agent_map = init_system()
        run_demo_task()
        run_rag_demo(memory_hub)
    except OrderGuardianError as e:
        logger.error(f"OrderGuardianError: {e.error_code.value} - {e.message}", extra=e.extra)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)