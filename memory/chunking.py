"""
Text chunking via langchain RecursiveCharacterTextSplitter.
Optimized for short business texts: payment SOPs, risk rules, reconciliation guides.
"""
from typing import Dict, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import ChunkConfig
from core.logger import get_logger


class DocumentChunker:
    """Chunk documents using RecursiveCharacterTextSplitter, then embed each chunk."""

    def __init__(self, config: Optional[ChunkConfig] = None, embedding_provider=None):
        self.config = config or ChunkConfig()
        self.embedding = embedding_provider
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            separators=self.config.separators,
        )
        self.logger = get_logger("document_chunker")

    def chunk_and_embed(self, doc_id: str, title: str, content: str,
                        biz_domain: str, doc_type: str = "rule",
                        extra_meta: Optional[Dict] = None) -> List[Dict]:
        """Split document into chunks, generate embedding for each chunk."""
        base_meta = {
            "doc_id": doc_id,
            "title": title,
            "biz_domain": biz_domain,
            "doc_type": doc_type,
            **(extra_meta or {}),
        }

        full_text = f"{title}\n{content}"
        chunk_texts = self.splitter.split_text(full_text)
        results: List[Dict] = []
        for i, chunk_text in enumerate(chunk_texts):
            chunk_meta = dict(base_meta)
            chunk_meta["chunk_id"] = f"{doc_id}_chunk_{i}"
            chunk_meta["chunk_index"] = i
            chunk_meta["total_chunks"] = len(chunk_texts)
            chunk_meta["content"] = chunk_text

            embedding = None
            if self.embedding:
                embedding = self.embedding.encode(chunk_text)

            results.append({
                "embedding": embedding,
                "metadata": chunk_meta,
                "chunk_text": chunk_text,
            })

        self.logger.info("chunking_done", extra={
            "doc_id": doc_id,
            "chunks": len(results),
            "chunk_size": self.config.chunk_size,
            "overlap": self.config.chunk_overlap,
        })
        return results
