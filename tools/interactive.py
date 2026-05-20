"""
Interactive dialogue mode.
Only this module accepts user input().
All other code paths auto-execute without blocking.
"""
from typing import Any, Dict, List, Optional

from config import SystemConfig
from core.logger import get_logger


class InteractiveSession:
    """Interactive RAG dialogue for order diagnostics."""

    def __init__(self, memory_hub, embedding_provider,
                 config: Optional[SystemConfig] = None,
                 hybrid_engine=None):
        self.memory_hub = memory_hub
        self.embedding = embedding_provider
        self.cfg = config or SystemConfig()
        self.hybrid_engine = hybrid_engine
        self.logger = get_logger("interactive")
        self._pipeline = None
        self._llm = None
        self._preprocessor = None
        self._intent = None

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
        """Enter dialogue loop. Only this method blocks on input()."""
        self._init()
        print("\n" + "=" * 60)
        print("  Order Guardian - Interactive Mode")
        print("  Domains: payment / order / risk / reconciliation / operation")
        print("  Type 'exit' to quit")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSession ended.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Session ended.")
                break

            response = self.ask(user_input)
            self._print_response(response)

    def ask(self, query: str) -> Dict[str, Any]:
        """Single round: jieba -> intent -> embed -> FAISS -> LLM answer."""
        self._init()
        return self._pipeline.process_query(query)

    def _print_response(self, result: Dict[str, Any]):
        if result.get("answer"):
            print(f"\n{result['answer']}")
        print(f"\n  domain: {result.get('domain', '?')} | "
              f"keywords: {result.get('keywords', [])} | "
              f"time: {result.get('duration_ms', 0):.1f}ms\n")


def run_interactive(system: Dict[str, Any]):
    session = InteractiveSession(
        memory_hub=system["memory_hub"],
        embedding_provider=system.get("embedding_provider"),
        hybrid_engine=system["memory_hub"].hybrid_search,
    )
    session.start()
