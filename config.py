"""
Global configuration hub.
All tunable parameters live here. No hardcoded magic numbers elsewhere.
"""
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ChunkConfig:
    """Text chunking parameters for langchain RecursiveCharacterTextSplitter."""
    chunk_size: int = 300
    chunk_overlap: int = 50
    separators: List[str] = field(default_factory=lambda: [
        "\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""
    ])


@dataclass
class RetrievalConfig:
    """FAISS retrieval parameters."""
    top_k: int = 5
    similarity_threshold: float = 0.0
    query_expansion_top_k: int = 3


@dataclass
class IntentConfig:
    """Rule-based intent recognition parameters."""
    domain_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        "payment": ["payment", "timeout", "callback", "channel", "refund", "pay", "paid", "unpaid"],
        "order": ["order", "status", "create", "cancel", "close", "amount", "product"],
        "risk": ["risk", "fraud", "blacklist", "score", "block", "freeze", "intercept"],
        "reconciliation": ["reconciliation", "reconcile", "diff", "mismatch", "ledger", "balance"],
        "operation": ["sop", "operation", "manual", "approval", "process", "handle", "escalate"],
    })
    default_domain: str = "order"


@dataclass
class PreprocessConfig:
    """jieba preprocessing parameters."""
    stopwords_file: str = ""
    max_keywords: int = 8
    min_keyword_len: int = 2


@dataclass
class RAGConfig:
    """RAG pipeline configuration."""
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    intent: IntentConfig = field(default_factory=IntentConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    max_context_tokens: int = 4000
    reserved_for_prompt: int = 1000
    relevance_threshold: float = 0.1
    domain_match_bonus: float = 0.3


@dataclass
class SystemConfig:
    """Top-level system configuration."""
    rag: RAGConfig = field(default_factory=RAGConfig)
    embedding_dim: int = 1024
    data_dir: str = "./data"
    kb_chunking_enabled: bool = True
