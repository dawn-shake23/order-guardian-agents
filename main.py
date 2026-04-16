# main.py
import uuid
from Memory.memory_hub import MemoryHub
from Tools.tool_lifecycle import ToolLifeCycleManager
from MCP.mcp_gateway import MCPGateway
from Coordinator.coordinator import Coordinator
from Agents import (
    OrderAgent,
    PaymentAgent,
    RiskAgent,
    ReconciliationAgent,
    OperationAgent
)

def init_system():
    """系统全局初始化"""
    # 1. 初始化记忆中心
    memory_hub = MemoryHub()

    # 2. 初始化工具体系（注册 + 生命周期 + 权限）
    ToolLifeCycleManager.global_init(memory_hub)

    # 3. 初始化 MCP 控制平面
    mcp = MCPGateway(memory_hub)

    # 4. 初始化 Coordinator
    coordinator = Coordinator(mcp, memory_hub)

    # 5. 注册所有专家 Agent
    agent_map = {
        "order": OrderAgent(memory_hub),
        "payment": PaymentAgent(memory_hub),
        "risk": RiskAgent(memory_hub),
        "reconciliation": ReconciliationAgent(memory_hub),
        "operation": OperationAgent(memory_hub),
    }
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
        "intent": {"rewritten_query": "查询订单支付状态并进行风险排查"},
        "global_analysis": {"order_state_analysis": "订单已创建，支付待确认"},
        "steps": [
            {"step_id": 1, "expert_type": "order", "goal": "查询订单基础信息"},
            {"step_id": 2, "expert_type": "payment", "goal": "核查支付渠道状态"},
            {"step_id": 3, "expert_type": "risk", "goal": "风险评估与权限校验"},
            {"step_id": 4, "expert_type": "reconciliation", "goal": "账实核对"},
            {"step_id": 5, "expert_type": "operation", "goal": "给出运营建议"},
        ]
    }

    print("===== 开始执行多专家协同任务 =====")
    print(f"session_id: {session_id}")
    print(f"order_id: {order_id}\n")

    # 启动 Coordinator 调度
    final_report = coordinator.execute(execution_plan, agent_map)

    # 输出最终结果
    print("\n===== 最终会诊报告 =====")
    print(f"状态: {'成功' if final_report['plan_success'] else '失败'}")
    print(f"风险等级: {final_report['risk_level']}")
    print(f"根因: {final_report['abnormal_root_cause']}")
    print(f"解决方案: {final_report['solution']}")
    print(f"总结: {final_report['final_summary']}")

if __name__ == "__main__":
    run_demo_task()