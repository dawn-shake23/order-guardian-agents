"""
Interactive dialogue mode.

Only this module accepts user input.
All other code paths execute without blocking.
"""
from typing import Any, Dict, List, Optional

from config import RAGConfig
from core.logger import get_logger


class InteractiveSession:
    """Interactive RAG dialogue for order diagnostics."""

    def __init__(self, memory_hub, embedding_provider,
                 config: Optional[RAGConfig] = None,
                 hybrid_engine=None):
        self.memory_hub = memory_hub
        self.embedding = embedding_provider
        self.config = config or RAGConfig()
        self.hybrid_engine = hybrid_engine
        self.logger = get_logger("interactive")
        self.history: List[Dict[str, str]] = []
        self._pipeline = None
        self._preprocessor = None
        self._intent = None

    def _lazy_init(self):
        if self._pipeline is not None:
            return
        from tools.preprocessing import QueryPreprocessor
        from tools.intent_recognizer import RuleIntentRecognizer
        from tools.DeepSearch.rag_pipeline import RAGPipeline
        self._preprocessor = QueryPreprocessor(config=self.config.preprocess)
        self._intent = RuleIntentRecognizer(config=self.config.intent)
        self._pipeline = RAGPipeline(
            config=self.config,
            hybrid_engine=self.hybrid_engine,
            embedding_provider=self.embedding,
            preprocessor=self._preprocessor,
            intent_recognizer=self._intent,
        )

    def start(self):
        """Enter dialogue loop. Only this method blocks on input()."""
        self._lazy_init()
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
        """Single round: jieba -> intent -> embed -> FAISS -> context -> output."""
        self._lazy_init()
        result = self._pipeline.process_query(query)
        self.history.append({"role": "user", "content": query})
        return result

    def _print_response(self, result: Dict[str, Any]):
        print(f"\n  domain   : {result.get('domain', '?')}")
        print(f"  keywords : {result.get('keywords', [])}")
        print(f"  rules    : {result.get('matched_rules', [])} "
              f"(confidence={result.get('intent_confidence', 0):.2f})")
        print(f"  results  : {result.get('result_count', 0)} chunks")
        print(f"  duration : {result.get('duration_ms', 0):.1f} ms")
        print()


def run_interactive(system: Dict[str, Any]):
    """Launch interactive session from initialized system dict."""
    session = InteractiveSession(
        memory_hub=system["memory_hub"],
        embedding_provider=system.get("embedding_provider"),
        hybrid_engine=system["memory_hub"].hybrid_search,
    )
    session.start()
