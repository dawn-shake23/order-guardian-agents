import time
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from .base_worker import AgentMeta, BaseWorkerAgent, AgentInput, AgentOutput
from .plan_agent import ExecutionPlan, PlanStep
from models.llm_client import LLMClient, ModelType
from memory.memory_hub import MemoryHub
from core.order_state_machine import OrderStateMachine, OrderState, OrderEvent
from core.errors import AgentError, ToolError, BusinessError, ErrorCode
from core.logger import get_logger
from infrastructure.mock_infra import MockDB, MockRAG, MockMetrics, MockMQ
from infrastructure.resilience import CircuitBreaker, RateLimiter, ConcurrencyController
from infrastructure.decision_engine import DecisionEngine, DecisionResult
from infrastructure.approval import ApprovalEngine
from infrastructure.state_persistence import StatePersistence, SessionState, StepState, StepStatus
from infrastructure.agent_pool import AgentPool


class FinalConsultReport(BaseModel):
    session_id: str
    order_id: str
    plan_success: bool
    abnormal_root_cause: str
    solution: str
    risk_level: str
    expert_steps: List[Dict[str, Any]]
    final_summary: str
    decision_type: str = "auto_resolve"
    decision_confidence: float = 0.0
    needs_approval: bool = False
    fallback_used: bool = False
    total_duration_ms: float = 0.0


COORDINATOR_META = AgentMeta(
    agent_type="coordinator",
    version="2.0.0",
    timeout_seconds=60,
    required_fields=["execution_plan"],
    acl_scopes=["plan:read", "step:schedule", "result:aggregate", "decision:make"]
)


class Coordinator(BaseWorkerAgent):
    def __init__(self, mcp, memory_hub: MemoryHub, mock_db: MockDB, mock_rag: MockRAG,
                 metrics: Optional[MockMetrics] = None, mock_mq: Optional[MockMQ] = None,
                 decision_engine: Optional[DecisionEngine] = None,
                 approval_engine: Optional[ApprovalEngine] = None,
                 state_persistence: Optional[StatePersistence] = None,
                 agent_pool: Optional[AgentPool] = None,
                 concurrency_controller: Optional[ConcurrencyController] = None):
        super().__init__(COORDINATOR_META, memory_hub, metrics)
        self.mcp = mcp
        self.mock_db = mock_db
        self.mock_rag = mock_rag
        self.mock_mq = mock_mq or MockMQ()
        self.llm = LLMClient(model_type=ModelType.QWEN_14B)
        self.state_machine = OrderStateMachine()
        self.decision_engine = decision_engine or DecisionEngine()
        self.approval_engine = approval_engine or ApprovalEngine()
        self.state_persistence = state_persistence or StatePersistence()
        self.agent_pool = agent_pool or AgentPool()
        self.concurrency = concurrency_controller or ConcurrencyController(max_concurrent=5)
        self.logger = get_logger("coordinator")

    def run(self, input_context: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "message": "Coordinator run method called"}

    def execute(self, execution_plan, agent_map) -> Dict[str, Any]:
        overall_start = time.time()
        plan = ExecutionPlan(**execution_plan)

        self.logger.info("开始执行任务", extra={
            "session_id": plan.session_id, "order_id": plan.order_id
        })

        session_state = SessionState(
            session_id=plan.session_id,
            order_id=plan.order_id,
            steps=[StepState(step_id=s.step_id, expert_type=s.expert_type, goal=s.goal)
                   for s in plan.steps]
        )
        self.state_persistence.save(session_state)

        global_context = {
            "session_id": plan.session_id,
            "order_id": plan.order_id,
            "intent": plan.intent.model_dump(),
            "global_analysis": plan.global_analysis.model_dump()
        }

        pruned_steps = self._prune_steps(plan.steps)
        pruned_steps = self._detect_conflicts(pruned_steps)
        pruned_steps = self._detect_loops(pruned_steps)

        self.logger.info("步骤优化完成", extra={
            "original_steps": len(plan.steps),
            "pruned_steps": len(pruned_steps)
        })

        step_results = []
        has_failed_step = False

        loop = asyncio.new_event_loop()
        try:
            step_results = loop.run_until_complete(
                self._execute_steps_async(pruned_steps, agent_map, plan, global_context, session_state)
            )
        finally:
            loop.close()

        for sr in step_results:
            if sr.get("status") == "failed":
                has_failed_step = True

        plan_success = not has_failed_step

        self._update_order_state(plan, step_results)

        final_report = self._make_final_decision(
            global_context, step_results, plan, plan_success
        )

        total_duration = (time.time() - overall_start) * 1000
        final_report.total_duration_ms = round(total_duration, 2)

        session_state.plan_success = plan_success
        self.state_persistence.save(session_state)

        if self.mock_mq:
            self.mock_mq.publish("task.completed", {
                "session_id": plan.session_id,
                "order_id": plan.order_id,
                "success": plan_success
            })

        if self.metrics:
            self.metrics.inc_counter("coordinator.tasks.completed")
            self.metrics.record_histogram("coordinator.task.duration", total_duration)

        self.logger.info("任务执行完成", extra={
            "session_id": plan.session_id,
            "plan_success": final_report.plan_success,
            "duration_ms": round(total_duration, 2)
        })

        return final_report.model_dump()

    async def _execute_steps_async(self, steps, agent_map, plan, global_context, session_state):
        results = []
        completed_expert_types = set()

        for step in steps:
            if step.expert_type in completed_expert_types and step.depends_on:
                pass

            agent = agent_map.get(step.expert_type)
            if not agent:
                degraded_result = self._try_degrade_agent(step.expert_type, agent_map, step)
                if degraded_result:
                    results.append(degraded_result)
                    continue
                results.append({
                    "step_id": step.step_id, "expert_type": step.expert_type,
                    "goal": step.goal, "status": "failed",
                    "error": f"Agent {step.expert_type} 不可用且无降级方案"
                })
                continue

            if self.concurrency:
                self.concurrency.acquire()

            try:
                agent.initialize(plan.session_id, step.step_id)
                session_state.steps[step.step_id - 1].status = StepStatus.RUNNING
                session_state.steps[step.step_id - 1].started_at = time.time()
                self.state_persistence.checkpoint(session_state)

                start = time.time()
                try:
                    result = agent.run({
                        "session_id": plan.session_id,
                        "order_id": plan.order_id,
                        "step": step.model_dump(),
                        "context": global_context
                    })
                    duration = (time.time() - start) * 1000

                    results.append({
                        "step_id": step.step_id, "expert_type": step.expert_type,
                        "goal": step.goal, "status": "completed",
                        "result": result, "duration_ms": round(duration, 2)
                    })

                    session_state.steps[step.step_id - 1].status = StepStatus.COMPLETED
                    session_state.steps[step.step_id - 1].result = result
                    session_state.steps[step.step_id - 1].duration_ms = round(duration, 2)
                    completed_expert_types.add(step.expert_type)

                    if self.metrics:
                        self.metrics.inc_counter(f"step.{step.expert_type}.success")

                except AgentError as e:
                    duration = (time.time() - start) * 1000
                    retry_result = self._retry_step(step, agent, plan, global_context)
                    if retry_result:
                        results.append(retry_result)
                        completed_expert_types.add(step.expert_type)
                    else:
                        results.append({
                            "step_id": step.step_id, "expert_type": step.expert_type,
                            "goal": step.goal, "status": "failed",
                            "error": f"AgentError: {e.error_code.value} - {e.message}",
                            "duration_ms": round(duration, 2)
                        })
                        session_state.steps[step.step_id - 1].status = StepStatus.FAILED
                        session_state.steps[step.step_id - 1].error = str(e)

                except Exception as e:
                    duration = (time.time() - start) * 1000
                    results.append({
                        "step_id": step.step_id, "expert_type": step.expert_type,
                        "goal": step.goal, "status": "failed",
                        "error": f"Unexpected: {str(e)}", "duration_ms": round(duration, 2)
                    })
                    session_state.steps[step.step_id - 1].status = StepStatus.FAILED
                    session_state.steps[step.step_id - 1].error = str(e)

                finally:
                    session_state.steps[step.step_id - 1].completed_at = time.time()
                    self.state_persistence.checkpoint(session_state)
                    agent.destroy()

            finally:
                if self.concurrency:
                    self.concurrency.release()

            await asyncio.sleep(0.01)

        return results

    def _retry_step(self, step, agent, plan, context, max_retries=1):
        for attempt in range(max_retries):
            try:
                self.logger.info("步骤重试", extra={
                    "step_id": step.step_id, "attempt": attempt + 1
                })
                result = agent.run({
                    "session_id": plan.session_id,
                    "order_id": plan.order_id,
                    "step": step.model_dump(),
                    "context": context
                })
                return {
                    "step_id": step.step_id, "expert_type": step.expert_type,
                    "goal": step.goal, "status": "completed",
                    "result": result, "retried": True
                }
            except Exception:
                time.sleep(0.5)
        return None

    def _try_degrade_agent(self, failed_type, agent_map, step):
        DEGRADE_MAP = {
            "payment": "order",
            "risk": "payment",
            "reconciliation": "order",
            "operation": "reconciliation",
        }
        fallback_type = DEGRADE_MAP.get(failed_type)
        if fallback_type and fallback_type in agent_map:
            self.logger.info("Agent降级", extra={
                "from": failed_type, "to": fallback_type
            })
            agent = agent_map[fallback_type]
            try:
                result = agent.run({
                    "session_id": step.step_id,
                    "order_id": "",
                    "step": step.model_dump(),
                    "context": {}
                })
                return {
                    "step_id": step.step_id, "expert_type": fallback_type,
                    "goal": step.goal, "status": "completed",
                    "result": result, "degraded_from": failed_type
                }
            except Exception:
                pass
        return None

    def _prune_steps(self, steps: List[PlanStep]) -> List[PlanStep]:
        seen = set()
        pruned = []
        for step in steps:
            key = f"{step.expert_type}:{step.goal}"
            if key not in seen:
                seen.add(key)
                pruned.append(step)
        return pruned

    def _detect_conflicts(self, steps: List[PlanStep]) -> List[PlanStep]:
        return steps

    def _detect_loops(self, steps: List[PlanStep]) -> List[PlanStep]:
        visited = set()
        result = []
        for step in steps:
            if step.step_id not in visited:
                visited.add(step.step_id)
                result.append(step)
        return result

    def _update_order_state(self, plan, step_results):
        try:
            current = OrderState.CREATED
            for sr in step_results:
                if sr.get("status") == "completed":
                    result = sr.get("result", {})
                    if isinstance(result, dict):
                        status = result.get("payment_status") or result.get("order_info", {}).get("status")
                        if status == "paid":
                            event = OrderEvent.PAY
                            new_state = self.state_machine.transition(current, event)
                            if new_state:
                                current = new_state
        except Exception:
            pass

    def _make_final_decision(self, context, steps, plan, plan_success) -> FinalConsultReport:
        decision: DecisionResult = self.decision_engine.decide(steps, context)

        if decision.needs_approval and self.approval_engine:
            approval = self.approval_engine.submit(
                order_id=plan.order_id,
                agent_type="coordinator",
                action="final_decision",
                reason=decision.root_cause,
                risk_level=decision.risk_level
            )
            if approval.status.value == "pending":
                self.approval_engine.auto_resolve_pending()

        raw = self.llm.generate("", output_schema=FinalConsultReport)
        raw_data = raw.get("data", {})

        report = FinalConsultReport(
            session_id=plan.session_id,
            order_id=plan.order_id,
            plan_success=plan_success,
            abnormal_root_cause=decision.root_cause or raw_data.get("abnormal_root_cause", "自动分析"),
            solution=decision.solution or raw_data.get("solution", "自动方案"),
            risk_level=decision.risk_level or raw_data.get("risk_level", plan.global_analysis.abnormal_level),
            expert_steps=steps,
            final_summary=self._build_summary(steps, decision, plan_success),
            decision_type=decision.decision_type.value,
            decision_confidence=decision.confidence,
            needs_approval=decision.needs_approval,
        )
        return report

    def _build_summary(self, steps, decision, plan_success) -> str:
        completed = sum(1 for s in steps if s.get("status") == "completed")
        failed = sum(1 for s in steps if s.get("status") == "failed")
        summary = f"共{len(steps)}个步骤，{completed}个成功，{failed}个失败。"
        summary += f"决策类型：{decision.decision_type.value}，置信度：{decision.confidence:.0%}。"
        summary += f"根因：{decision.root_cause}。方案：{decision.solution}"
        return summary
