"""
Global configuration hub.
All tunable parameters live here. No hardcoded magic numbers elsewhere.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ChunkConfig:
    chunk_size: int = 300
    chunk_overlap: int = 50
    separators: List[str] = field(default_factory=lambda: [
        "\n\n", "\n", "。。", "！", "？", "；", ".", "!", "?", ";", " ", ""
    ])


@dataclass
class RetrievalConfig:
    top_k: int = 5
    similarity_threshold: float = 0.0


@dataclass
class IntentConfig:
    domain_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        "payment": ["payment", "timeout", "callback", "channel", "refund", "pay", "E2001", "E2002", "E2003", "E2004", "E2005"],
        "order": ["order", "status", "create", "cancel", "close", "amount", "E1001", "E1002", "E1003", "E1004"],
        "risk": ["risk", "fraud", "blacklist", "score", "block", "freeze", "E3001", "E3002", "E3003"],
        "reconciliation": ["reconciliation", "reconcile", "diff", "mismatch", "ledger", "E4001", "E4002"],
        "operation": ["sop", "operation", "manual", "approval", "process", "handle"],
    })
    default_domain: str = "order"


@dataclass
class PreprocessConfig:
    stopwords_file: str = ""
    max_keywords: int = 8
    min_keyword_len: int = 2
    stopwords: List[str] = field(default_factory=lambda: [
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "but", "not", "no", "this", "that", "it", "its",
        "how", "what", "when", "where", "which", "who", "why",
    ])


@dataclass
class LLMConfig:
    model: str = "qwen-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_tokens: int = 1024
    temperature: float = 0.1


@dataclass
class EmbeddingConfig:
    model: str = "text-embedding-v3"
    dim: int = 1024
    batch_size: int = 10
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class PersistenceConfig:
    vector_index_dir: str = "./data/faiss_index"
    vector_index_file: str = "kb.index"
    metadata_file: str = "kb_metadata.json"
    state_dir: str = "./state_checkpoints"
    db_path: str = "./data/mock_db.json"


@dataclass
class SystemConfig:
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    intent: IntentConfig = field(default_factory=IntentConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    max_context_tokens: int = 4000
    knowledge_base_dir: str = "./data"
    data_dir: str = "./data"
