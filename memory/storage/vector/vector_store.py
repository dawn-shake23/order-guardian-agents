from typing import List, Dict, Any, Optional
import faiss
import numpy as np

class VectorMemoryStore:
    def __init__(self):
        # 实际项目中这里应该初始化真实的向量存储
        self.embeddings = []
        self.metadata = []
        self.dimension = 128  # 假设向量维度为128
        self.index = faiss.IndexFlatL2(self.dimension)
    
    def add(self, embedding: List[float], metadata: Dict[str, Any]) -> bool:
        """
        添加向量和元数据
        """
        self.embeddings.append(embedding)
        self.metadata.append(metadata)
        self.index.add(np.array([embedding], dtype=np.float32))
        return True
    
    def search(self, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索相似向量
        """
        query = np.array([query_embedding], dtype=np.float32)
        distances, indices = self.index.search(query, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):
                result = {
                    "metadata": self.metadata[idx],
                    "distance": float(distances[0][i])
                }
                results.append(result)
        
        return results
    
    def delete(self, index: int) -> bool:
        """
        删除向量
        """
        if 0 <= index < len(self.embeddings):
            del self.embeddings[index]
            del self.metadata[index]
            # 重建索引
            self.index = faiss.IndexFlatL2(self.dimension)
            if self.embeddings:
                self.index.add(np.array(self.embeddings, dtype=np.float32))
            return True
        return False
    
    def clear(self):
        """
        清空向量存储
        """
        self.embeddings = []
        self.metadata = []
        self.index = faiss.IndexFlatL2(self.dimension)