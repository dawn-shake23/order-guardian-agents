from typing import List, Dict, Any, Optional

try:
    import faiss
    import numpy as np
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False


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

    def search(self, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        if _HAS_FAISS and self.index is not None and len(self.embeddings) > 0:
            query = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.index.search(query, min(k, len(self.embeddings)))
            results = []
            for i, idx in enumerate(indices[0]):
                if 0 <= idx < len(self.metadata):
                    results.append({
                        "metadata": self.metadata[idx],
                        "distance": float(distances[0][i])
                    })
            return results
        results = []
        for i, meta in enumerate(self.metadata[:k]):
            results.append({"metadata": meta, "distance": 0.0})
        return results

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
