"""
FAISS vector store with disk persistence.
Restart does not lose the index; no rebuild needed.
"""
import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

_HAS_FAISS = False
try:
    import faiss
    _HAS_FAISS = True
except ImportError:
    pass


class VectorMemoryStore:
    def __init__(self, dimension: int = 1024):
        self.embeddings: List[List[float]] = []
        self.metadata: List[Dict[str, Any]] = []
        self.dimension = dimension
        if _HAS_FAISS:
            self.index = faiss.IndexFlatL2(self.dimension)
        else:
            self.index = None

    def add(self, embedding: List[float], metadata: Dict[str, Any]) -> bool:
        self.embeddings.append(embedding)
        self.metadata.append(metadata)
        if _HAS_FAISS and self.index is not None:
            self.index.add(np.array([embedding], dtype=np.float32))
        return True

    def add_batch(self, items: List[tuple]) -> bool:
        """items: [(embedding, metadata), ...]"""
        if not items:
            return True
        embs = []
        metas = []
        for e, m in items:
            self.embeddings.append(e)
            self.metadata.append(m)
            embs.append(e)
            metas.append(m)
        if _HAS_FAISS and self.index is not None:
            self.index.add(np.array(embs, dtype=np.float32))
        return True

    def search(self, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        if not self.embeddings:
            return []
        if _HAS_FAISS and self.index is not None:
            query = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.index.search(query, min(k, len(self.embeddings)))
            results = []
            for i, idx in enumerate(indices[0]):
                if 0 <= idx < len(self.metadata):
                    results.append({
                        "metadata": self.metadata[idx],
                        "distance": float(distances[0][i]),
                        "score": float(1.0 / (1.0 + distances[0][i])),
                    })
            return results
        return []

    def delete(self, index: int) -> bool:
        if 0 <= index < len(self.embeddings):
            del self.embeddings[index]
            del self.metadata[index]
            if _HAS_FAISS and self.index is not None:
                self.index = faiss.IndexFlatL2(self.dimension)
                if self.embeddings:
                    self.index.add(np.array(self.embeddings, dtype=np.float32))
            return True
        return False

    def clear(self):
        self.embeddings = []
        self.metadata = []
        if _HAS_FAISS and self.index is not None:
            self.index = faiss.IndexFlatL2(self.dimension)

    def save(self, index_dir: str = "./data/faiss_index",
             index_file: str = "kb.index", metadata_file: str = "kb_metadata.json"):
        """Persist FAISS index + metadata to disk."""
        os.makedirs(index_dir, exist_ok=True)
        index_path = os.path.join(index_dir, index_file)
        meta_path = os.path.join(index_dir, metadata_file)

        if _HAS_FAISS and self.index is not None and self.embeddings:
            faiss.write_index(self.index, index_path)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"dimension": self.dimension, "count": len(self.metadata),
                        "metadata": self.metadata}, f, ensure_ascii=False)

    def load(self, index_dir: str = "./data/faiss_index",
             index_file: str = "kb.index", metadata_file: str = "kb_metadata.json"):
        """Load FAISS index + metadata from disk."""
        index_path = os.path.join(index_dir, index_file)
        meta_path = os.path.join(index_dir, metadata_file)

        if not os.path.exists(meta_path):
            return False

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.dimension = data.get("dimension", self.dimension)
        self.metadata = data.get("metadata", [])

        if _HAS_FAISS and os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
        elif _HAS_FAISS:
            self.index = faiss.IndexFlatL2(self.dimension)

        self.embeddings = [[] for _ in self.metadata]
        return True

    def __len__(self):
        return len(self.metadata)
