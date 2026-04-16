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

if __name__ == "__main__":
    try:
        run_demo_task()
    except OrderGuardianError as e:
        logger.error(f"OrderGuardianError: {e.error_code.value} - {e.message}", extra=e.extra)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)