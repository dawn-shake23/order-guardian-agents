from typing import List
from models.vector_memory import VectorDocument

class VectorMemoryStore:
    def __init__(self):
        # 对接Chroma/Pinecone等向量库
        self.vector_db = {}

    # 存储向量文档
    def add_vector_doc(self, doc: VectorDocument) -> None:
        self.vector_db[doc.doc_id] = doc

    # 向量检索（仅接口，MCP管控权限）
    def search_by_domain(self, query: str, biz_domain: str, top_k: int = 3) -> List[VectorDocument]:
        # 实际业务中执行向量相似度检索
        result = [doc for doc in self.vector_db.values() if doc.biz_domain == biz_domain]
        return result[:top_k]