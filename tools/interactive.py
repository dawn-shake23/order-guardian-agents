"""
Interactive dialogue mode with command routing.
Only this module accepts user input().
"""
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from config import SystemConfig
from core.logger import get_logger


class InteractiveSession:
    """Interactive mode: order diagnosis + RAG QA + system status."""

    def __init__(self, memory_hub, embedding_provider,
                 config: Optional[SystemConfig] = None,
                 hybrid_engine=None, system: Optional[Dict] = None):
        self.memory_hub = memory_hub
        self.embedding = embedding_provider
        self.cfg = config or SystemConfig()
        self.hybrid_engine = hybrid_engine
        self.system = system or {}
        self.logger_obj = get_logger("interactive")
        self._pipeline = None
        self._llm = None
        self._preprocessor = None
        self._intent = None
        self._task_count = 0

    def _init(self):
        if self._pipeline is not None:
            return
        from tools.preprocessing import QueryPreprocessor
        from tools.intent_recognizer import RuleIntentRecognizer
        from tools.DeepSearch.rag_pipeline import RAGPipeline
        from models.llm_client import LLMClient
        self._preprocessor = QueryPreprocessor()
        self._intent = RuleIntentRecognizer(config=self.cfg.intent)
        self._llm = LLMClient(config=self.cfg.llm)
        self._pipeline = RAGPipeline(
            config=self.cfg,
            hybrid_engine=self.hybrid_engine,
            embedding_provider=self.embedding,
            llm_client=self._llm,
            preprocessor=self._preprocessor,
            intent_recognizer=self._intent,
        )

    def start(self):
        self._init()
        print("\n" + "=" * 60)
        print("  Order Guardian - Interactive Mode")
        print("=" * 60)
        print("  ORD00001        full diagnosis for that order")
        print("  run ORD00001     same as above")
        print("  status           system status snapshot")
        print("  clear            clear screen")
        print("  <any question>   RAG knowledge base query")
        print("  exit             quit")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSession ended.")
                break

            if not user_input:
                continue

            lower = user_input.lower()

            # --- exit ---
            if lower in ("exit", "quit", "q"):
                print("Session ended.")
                break

            # --- clear ---
            if lower == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                continue

            # --- status ---
            if lower == "status":
                self._cmd_status()
                continue

            # --- order diagnosis: ORDxxxxx or run ORDxxxxx ---
            order_match = re.match(r'(?:run\s+)?(ORD\d{5,})', user_input, re.IGNORECASE)
            if order_match:
                order_id = order_match.group(1).upper()
                self._cmd_diagnose(order_id)
                continue

            # --- help ---
            if lower in ("help", "?"):
                self._cmd_help()
                continue

            # --- default: RAG query ---
            self._cmd_rag(user_input)

    def _cmd_diagnose(self, order_id: str):
        """Run full 5-agent diagnostic pipeline for an order."""
        coordinator = self.system.get("coordinator")
        plan_agent = self.system.get("plan_agent")
        agent_map = self.system.get("agent_map")
        heartbeat = self.system.get("heartbeat")

        if not coordinator or not plan_agent or not agent_map:
            print("  System not fully initialized. Cannot run diagnosis.")
            return

        self._task_count += 1
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        if heartbeat:
            heartbeat.beat("coordinator")

        print(f"\n  [{self._task_count}] Diagnosing {order_id} ...")
        start = time.time()

        try:
            plan_result = plan_agent.run({
                "session_id": session_id,
                "order_id": order_id,
                "abnormal_detail": "order anomaly diagnosis",
            })
            plan_result["session_id"] = session_id
            plan_result["order_id"] = order_id

            for step in plan_result.get("steps", []):
                deps = step.get("depends_on", [])
                dep_str = f" (deps: {deps})" if deps else ""
                print(f"    step {step['step_id']}: [{step['expert_type']}] {step['goal']}{dep_str}")

            final_report = coordinator.execute(plan_result, agent_map)
            if heartbeat:
                heartbeat.beat("coordinator")

            elapsed = (time.time() - start) * 1000

            print(f"\n  {'='*50}")
            print(f"  Diagnosis Report: {order_id}")
            print(f"  {'='*50}")
            print(f"  session    : {session_id}")
            print(f"  success    : {final_report['plan_success']}")
            print(f"  risk_level : {final_report['risk_level']}")
            print(f"  decision   : {final_report.get('decision_type', 'N/A')}")
            print(f"  confidence : {final_report.get('decision_confidence', 0):.0%}")
            print(f"  root_cause : {final_report['abnormal_root_cause']}")
            print(f"  solution   : {final_report['solution']}")
            print(f"  duration   : {elapsed:.0f}ms")

            for step in final_report.get("expert_steps", []):
                icon = "OK" if step.get("status") == "completed" else "FAIL"
                dur = step.get("duration_ms", 0)
                print(f"    [{icon}] {step.get('expert_type', '?')} | "
                      f"{step.get('goal', '?')} ({dur:.0f}ms)")
                result = step.get("result", {})
                if isinstance(result, dict):
                    for k, v in result.items():
                        if k in ("rule_ref", "all_payments", "rule_guide", "case_ref", "sop_ref"):
                            if isinstance(v, list):
                                print(f"           {k}: [{len(v)} items]")
                            continue
                        if v is not None:
                            vs = str(v)
                            if len(vs) > 100:
                                vs = vs[:100] + "..."
                            print(f"           {k}: {vs}")

        except Exception as e:
            print(f"  Diagnosis failed: {e}")

    def _cmd_status(self):
        """Print system status snapshot."""
        print(f"\n  {'='*50}")
        print(f"  System Status")
        print(f"  {'='*50}")
        print(f"  tasks run    : {self._task_count}")
        print(f"  vector store : {len(self.memory_hub.vector_store)} vectors")

        metrics = self.system.get("mock_metrics")
        if metrics:
            snap = metrics.snapshot()
            for k, v in sorted(snap["counters"].items()):
                print(f"  counter.{k} : {v:.0f}")

        circuit_breakers = self.system.get("circuit_breakers", {})
        for name, cb in circuit_breakers.items():
            st = cb.get_state()
            print(f"  breaker.{name}: {st['state']} (fails={st['failure_count']})")

        rate_limiters = self.system.get("rate_limiters", {})
        for name, rl in rate_limiters.items():
            s = rl.get_status()
            print(f"  limiter.{name}: {s['current_requests']}/{s['max_requests']}")

        heartbeat = self.system.get("heartbeat")
        if heartbeat:
            health = heartbeat.check_health()
            for name, info in health.items():
                print(f"  heartbeat.{name}: {info['status']}")

    def _cmd_rag(self, query: str):
        """Run RAG query on knowledge base."""
        self._init()
        result = self._pipeline.process_query(query)
        if result.get("answer"):
            print(f"\n{result['answer']}")
        print(f"\n  [domain={result.get('domain', '?')}, "
              f"hits={result.get('result_count', 0)}, "
              f"time={result.get('duration_ms', 0):.0f}ms]")

    def _cmd_help(self):
        print("\n  Commands:")
        print("    ORD00001          run full diagnosis for order")
        print("    run ORD00001      same as above")
        print("    status            system status + counters + breakers")
        print("    clear             clear screen")
        print("    <question>        RAG knowledge base query")
        print("    exit              quit")


def run_interactive(system: Dict[str, Any]):
    session = InteractiveSession(
        memory_hub=system["memory_hub"],
        embedding_provider=system.get("embedding_provider"),
        hybrid_engine=system["memory_hub"].hybrid_search,
        system=system,
    )
    session.start()
