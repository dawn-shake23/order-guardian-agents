from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
from .plan_agent import ExecutionPlan
from models.llm_client import LLMClient, ModelType
from core.order_state_machine import OrderStateMachine, OrderState, OrderEvent
from core.logger import get_logger
from core.errors import AgentError, ToolError, BusinessError, ErrorCode

# -----------------------------------------------------------------------------
# 最终会诊报告（强校验，全局唯一出口）
# -----------------------------------------------------------------------------
class FinalConsultReport(BaseModel):
    session_id: str
    order_id: str
    plan_success: bool
    abnormal_root_cause: str
    solution: str
    risk_level: str
    expert_steps: List[Dict[str, Any]]
    final_summary: str

# -----------------------------------------------------------------------------
# Coordinator 元数据 & 权限定义
# -----------------------------------------------------------------------------
COORDINATOR_META = AgentMeta(
    agent_type="coordinator",
    version="1.0.0",
    timeout_seconds=45,
    required_fields=["execution_plan"],
    acl_scopes=["plan:read", "step:schedule", "result:aggregate", "decision:make"]
)

# -----------------------------------------------------------------------------
# Coordinator 核心：只做调度、决策、汇总
# 权限/Prompt/隔离/工具 全部交给 MCP
# -----------------------------------------------------------------------------
class Coordinator(BaseWorkerAgent):
    def __init__(self, mcp, memory_hub):
        super().__init__(COORDINATOR_META)
        self.mcp = mcp
        self.memory_hub = memory_hub
        self.llm = LLMClient(model_type=ModelType.QWEN_14B)
        self.state_machine = OrderStateMachine()
        self.logger = get_logger("coordinator")
    
    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        实现BaseAgent的抽象方法run
        """
        # 这里可以实现Coordinator的run逻辑
        # 但由于我们已经有了execute方法，这里可以简单调用execute方法
        # 或者返回一个默认值
        return {"status": "ok", "message": "Coordinator run method called"}

    def execute(self, execution_plan, agent_map) -> Dict[str, Any]:
        # 1. 解析并强校验 Plan
        self.logger.info("开始执行任务", extra={"execution_plan": execution_plan})
        plan = ExecutionPlan(**execution_plan)

        # 2. 构建全局上下文
        global_context = {
            "session_id": plan.session_id,
            "order_id": plan.order_id,
            "intent": plan.intent.model_dump(),
            "global_analysis": plan.global_analysis.model_dump()
        }
        self.logger.info("构建全局上下文", extra={"session_id": plan.session_id, "order_id": plan.order_id})

        # 3. 按步骤分发（MCP 负责权限、Prompt、上下文、工具）
        step_results = []
        for step in plan.steps:
            self.logger.info("执行步骤", extra={"step_id": step.step_id, "expert_type": step.expert_type, "goal": step.goal})
            # 获取对应的Agent
            agent = agent_map.get(step.expert_type)
            if agent:
                # 执行Agent任务
                agent.initialize(plan.session_id, step.step_id)
                try:
                    result = agent.run({
                        "step": step,
                        "context": global_context
                    })
                    step_results.append({
                        "step_id": step.step_id,
                        "expert_type": step.expert_type,
                        "goal": step.goal,
                        "status": "completed",
                        "result": result
                    })
                    self.logger.info("步骤执行完成", extra={"step_id": step.step_id, "expert_type": step.expert_type})
                except AgentError as e:
                    self.logger.error("Agent执行错误", extra={"step_id": step.step_id, "expert_type": step.expert_type, "error_code": e.error_code.value, "message": e.message})
                    step_results.append({
                        "step_id": step.step_id,
                        "expert_type": step.expert_type,
                        "goal": step.goal,
                        "status": "failed",
                        "error": f"AgentError: {e.error_code.value} - {e.message}"
                    })
                except ToolError as e:
                    self.logger.error("工具执行错误", extra={"step_id": step.step_id, "expert_type": step.expert_type, "error_code": e.error_code.value, "message": e.message})
                    step_results.append({
                        "step_id": step.step_id,
                        "expert_type": step.expert_type,
                        "goal": step.goal,
                        "status": "failed",
                        "error": f"ToolError: {e.error_code.value} - {e.message}"
                    })
                except Exception as e:
                    self.logger.error("步骤执行异常", extra={"step_id": step.step_id, "expert_type": step.expert_type, "error": str(e)}, exc_info=True)
                    step_results.append({
                        "step_id": step.step_id,
                        "expert_type": step.expert_type,
                        "goal": step.goal,
                        "status": "failed",
                        "error": f"Unexpected error: {str(e)}"
                    })
                finally:
                    agent.destroy()
            else:
                error_msg = f"Agent {step.expert_type} not found"
                step_results.append({
                    "step_id": step.step_id,
                    "expert_type": step.expert_type,
                    "goal": step.goal,
                    "status": "failed",
                    "error": error_msg
                })
                self.logger.error("步骤执行失败", extra={"step_id": step.step_id, "expert_type": step.expert_type, "error": error_msg})

        # 4. 强模型生成最终决策
        self.logger.info("生成最终决策", extra={"session_id": plan.session_id})
        final_report = self._make_final_decision(global_context, step_results, plan)

        self.logger.info("任务执行完成", extra={"session_id": plan.session_id, "plan_success": final_report.plan_success})
        return final_report.model_dump()

    def _make_final_decision(self, context: Dict, steps: List[Dict], plan: ExecutionPlan) -> FinalConsultReport:
        prompt = f"""
会话：{context['session_id']}
订单：{context['order_id']}
意图：{plan.intent.rewritten_query}
全局分析：{plan.global_analysis.order_state_analysis}
专家步骤结果：{steps}

请输出根因、方案、风险等级、最终总结。
"""
        raw = self.llm.generate(prompt, output_schema=FinalConsultReport)
        return FinalConsultReport(**raw["data"])