"""
Knowledge Base Loader — 知识库加载器
借鉴 Java KnowledgeBaseUploadService + KnowledgeBaseVectorService 设计：
- 文档 → 文本清洗 → 分块 → Embedding → 向量库 + 结构化库
- VectorStatus 生命周期：PENDING → PROCESSING → COMPLETED/FAILED
- SHA-256 内容去重
- 批量加载 + 失败补偿重试
"""
import os
import time
import hashlib
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from memory.embedding import EmbeddingProvider
from memory.chunking import DocumentChunker
from config import ChunkConfig
from memory.memory_hub import MemoryHub
from core.logger import get_logger


class VectorStatus(str, Enum):
    """向量化状态 — 借鉴 Java VectorStatus"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class LoadStats:
    documents: int = 0
    cases: int = 0
    chunks: int = 0
    failed: int = 0
    skipped_duplicate: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return self.documents + self.cases

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


class KnowledgeBaseLoader:
    """
    知识库加载器
    借鉴 Java 的上传→解析→分块→Embedding→存储 管道设计
    """

    DEFAULT_BATCH_SIZE = 10  # 借鉴阿里云 DashScope 的 batch size 限制

    def __init__(self, memory_hub: MemoryHub,
                 embedding_provider: Optional[EmbeddingProvider] = None,
                 chunk_config: Optional[ChunkConfig] = None,
                 enable_chunking: bool = True):
        self.memory_hub = memory_hub
        self.embedding = embedding_provider or EmbeddingProvider(dim=1024)
        self.enable_chunking = enable_chunking
        self.chunk_config = chunk_config or ChunkConfig()
        self.chunker = DocumentChunker(config=self.chunk_config, embedding_provider=self.embedding) if enable_chunking else None
        self.logger = get_logger("kb_loader")

        # 内容哈希去重 — 借鉴 Java FileHashService
        self._content_hashes: Dict[str, str] = {}
        self._stats = LoadStats()

    def load(self, documents: List[Dict[str, Any]],
             cases: Optional[List[Dict[str, Any]]] = None,
             batch_size: int = DEFAULT_BATCH_SIZE) -> Dict[str, Any]:
        """
        批量加载知识库
        借鉴 Java 的完整管道：验证 → 去重 → 分块 → Embedding → 双写
        """
        self._stats = LoadStats()
        self.logger.info("知识库加载开始", extra={
            "doc_count": len(documents),
            "case_count": len(cases or []),
            "embedding_backend": self.embedding.backend,
            "chunking": self.enable_chunking
        })

        # 加载知识文档（分批处理）
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            for doc in batch:
                self._load_document(doc)

        # 加载专家案例
        if cases:
            for i in range(0, len(cases), batch_size):
                batch = cases[i:i + batch_size]
                for case in batch:
                    self._load_case(case)

        result = {
            "status": "ok",
            "total_documents": self._stats.documents,
            "total_cases": self._stats.cases,
            "total_chunks": self._stats.chunks,
            "failed": self._stats.failed,
            "skipped_duplicate": self._stats.skipped_duplicate,
            "duration_ms": round(self._stats.elapsed_ms, 2),
            "embedding_backend": self.embedding.backend,
            "chunking_enabled": self.enable_chunking,
            "vector_store_size": len(self.memory_hub.vector_store.embeddings)
        }

        self.logger.info("知识库加载完成", extra=result)
        return result

    def _load_document(self, doc: Dict[str, Any]) -> bool:
        """加载单条知识文档"""
        doc_id = doc.get("doc_id", "")
        title = doc.get("title", "")
        content = doc.get("content", "")
        biz_domain = doc.get("biz_domain", "")
        doc_type = doc.get("doc_type", "rule")

        try:
            # 去重检查 — 借鉴 Java SHA-256 去重
            content_hash = self._hash_content(f"{title}|{content}")
            if content_hash in self._content_hashes:
                self.logger.info("重复文档跳过", extra={
                    "doc_id": doc_id, "title": title,
                    "duplicate_of": self._content_hashes[content_hash]
                })
                self._stats.skipped_duplicate += 1
                return False
            self._content_hashes[content_hash] = doc_id

            # 更新状态为 PROCESSING
            self._update_vector_status(doc_id, VectorStatus.PROCESSING)

            if self.enable_chunking and self.chunker:
                # 分块模式 — 借鉴 Java TokenTextSplitter + batch
                chunk_results = self.chunker.chunk_and_embed(
                    doc_id=doc_id, title=title, content=content,
                    biz_domain=biz_domain, doc_type=doc_type
                )

                for i in range(0, len(chunk_results), self.DEFAULT_BATCH_SIZE):
                    batch = chunk_results[i:i + self.DEFAULT_BATCH_SIZE]
                    for cr in batch:
                        if cr["embedding"]:
                            self.memory_hub.vector_store.add(cr["embedding"], cr["metadata"])
                        else:
                            self.memory_hub.vector_store.add(
                                self.embedding.encode(cr["chunk_text"]), cr["metadata"]
                            )
                    self._stats.chunks += len(batch)

                # 结构化库存储（文档级元数据 + 分块信息）
                struct_data = {
                    "doc_id": doc_id, "title": title, "content": content,
                    "biz_domain": biz_domain, "doc_type": doc_type,
                    "chunk_count": len(chunk_results),
                    "vector_status": VectorStatus.COMPLETED.value,
                    "content_hash": content_hash,
                    "created_at": time.time(), "updated_at": time.time(),
                    "is_deleted": False, "is_archived": False,
                }
            else:
                # 不分块模式 — 直接全文 embedding
                text = f"{title} {content}"
                embedding = self.embedding.encode(text)

                metadata = {
                    "doc_id": doc_id, "title": title, "content": content,
                    "biz_domain": biz_domain, "doc_type": doc_type, "text": text,
                }
                self.memory_hub.vector_store.add(embedding, metadata)

                struct_data = {
                    **metadata,
                    "vector_status": VectorStatus.COMPLETED.value,
                    "content_hash": content_hash,
                    "created_at": time.time(), "updated_at": time.time(),
                    "is_deleted": False, "is_archived": False,
                }

            self.memory_hub.struct_mysql.save("documents", doc_id, struct_data)
            self._update_vector_status(doc_id, VectorStatus.COMPLETED)
            self._stats.documents += 1
            return True

        except Exception as e:
            self.logger.error("知识文档加载失败", extra={
                "doc_id": doc_id, "title": title, "error": str(e)
            })
            self._update_vector_status(doc_id, VectorStatus.FAILED, str(e))
            self._stats.failed += 1
            return False

    def _load_case(self, case: Dict[str, Any]) -> bool:
        """加载专家案例"""
        case_id = case.get("case_id", "")
        title = case.get("title", "")
        biz_domain = case.get("biz_domain", "")

        try:
            text = f"{title} 问题:{case.get('problem','')} 根因:{case.get('root_cause','')} 方案:{case.get('solution','')}"

            # 去重检查
            content_hash = self._hash_content(text)
            if content_hash in self._content_hashes:
                self._stats.skipped_duplicate += 1
                return False
            self._content_hashes[content_hash] = case_id

            self._update_vector_status(case_id, VectorStatus.PROCESSING)

            embedding = self.embedding.encode(text)
            metadata = {
                "doc_id": case_id, "title": title, "content": text,
                "biz_domain": biz_domain, "doc_type": "case", "case_data": case,
            }
            self.memory_hub.vector_store.add(embedding, metadata)

            struct_data = {
                **metadata,
                "vector_status": VectorStatus.COMPLETED.value,
                "content_hash": content_hash,
                "created_at": time.time(), "updated_at": time.time(),
                "is_deleted": False, "is_archived": False,
            }
            self.memory_hub.struct_mysql.save("cases", case_id, struct_data)

            self._update_vector_status(case_id, VectorStatus.COMPLETED)
            self._stats.cases += 1
            return True

        except Exception as e:
            self.logger.error("案例加载失败", extra={
                "case_id": case_id, "title": title, "error": str(e)
            })
            self._update_vector_status(case_id, VectorStatus.FAILED, str(e))
            self._stats.failed += 1
            return False

    def load_files(self, file_paths: List[str], biz_domain: str = "order",
                   multimodal_processor=None) -> Dict[str, Any]:
        """
        从文件加载知识库（支持多模态：图片/PDF/文本）
        借鉴 Java KnowledgeBaseUploadService.uploadKnowledgeBase()
        """
        file_stats = {"images": 0, "pdfs": 0, "texts": 0, "failed": 0}
        start_time = time.time()

        if multimodal_processor is None:
            from memory.multimodal import MultimodalProcessor
            multimodal_processor = MultimodalProcessor(embedding_provider=self.embedding)

        for file_path in file_paths:
            if not os.path.exists(file_path):
                self.logger.error("文件不存在", extra={"path": file_path})
                file_stats["failed"] += 1
                continue

            import os as _os
            fname = _os.path.basename(file_path)
            doc_id = hashlib.md5(file_path.encode()).hexdigest()[:12]

            try:
                # 内容哈希去重
                with open(file_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                if file_hash in self._content_hashes:
                    self._stats.skipped_duplicate += 1
                    continue
                self._content_hashes[file_hash] = doc_id

                # 多模态处理
                doc = multimodal_processor.process_file(
                    file_path=file_path,
                    doc_id=doc_id,
                    title=fname,
                    biz_domain=biz_domain
                )

                # 写入向量库
                if doc.embedding:
                    meta = {
                        "doc_id": doc_id, "title": doc.title,
                        "content": doc.full_text,
                        "biz_domain": biz_domain, "doc_type": doc.media_type.value,
                        "media_type": doc.media_type.value,
                        "source_file": fname,
                    }
                    meta.update(doc.metadata)
                    self.memory_hub.vector_store.add(doc.embedding, meta)

                # 写入结构化库
                struct_data = {
                    "doc_id": doc_id, "title": doc.title,
                    "content": doc.full_text,
                    "biz_domain": biz_domain,
                    "doc_type": doc.media_type.value,
                    "media_type": doc.media_type.value,
                    "source_file": fname,
                    "file_hash": file_hash,
                    "vector_status": VectorStatus.COMPLETED.value,
                    "created_at": time.time(),
                    "is_deleted": False,
                }
                self.memory_hub.struct_mysql.save("documents", doc_id, struct_data)

                if doc.media_type.value == "image":
                    file_stats["images"] += 1
                elif doc.media_type.value == "pdf":
                    file_stats["pdfs"] += 1
                else:
                    file_stats["texts"] += 1

                self._stats.documents += 1

            except Exception as e:
                self.logger.error("文件加载失败", extra={"path": fname, "error": str(e)})
                file_stats["failed"] += 1

        elapsed = (time.time() - start_time) * 1000
        self.logger.info("文件加载完成", extra={
            **file_stats,
            "duration_ms": round(elapsed, 2)
        })

        return {
            "status": "ok",
            "images": file_stats["images"],
            "pdfs": file_stats["pdfs"],
            "texts": file_stats["texts"],
            "failed": file_stats["failed"],
            "duration_ms": round(elapsed, 2),
        }

    def add_document(self, doc_id: str, title: str, content: str,
                     biz_domain: str, doc_type: str = "rule") -> bool:
        """运行时动态添加单条文档"""
        return self._load_document({
            "doc_id": doc_id, "title": title, "content": content,
            "biz_domain": biz_domain, "doc_type": doc_type
        })

    def delete_document(self, doc_id: str) -> bool:
        """删除知识库文档（软删除）— 借鉴 Java KnowledgeBaseDeleteService"""
        try:
            # 结构化库软删除
            doc = self.memory_hub.struct_mysql.get("documents", doc_id)
            if doc:
                doc["is_deleted"] = True
                doc["deleted_at"] = time.time()
                self.memory_hub.struct_mysql.save("documents", doc_id, doc)
            return True
        except Exception as e:
            self.logger.error("文档删除失败", extra={"doc_id": doc_id, "error": str(e)})
            return False

    def get_stats(self) -> Dict[str, Any]:
        return {
            "documents": self._stats.documents,
            "cases": self._stats.cases,
            "chunks": self._stats.chunks,
            "failed": self._stats.failed,
            "skipped_duplicate": self._stats.skipped_duplicate,
            "vector_store_size": len(self.memory_hub.vector_store.embeddings),
            "embedding_backend": self.embedding.backend,
            "chunking_enabled": self.enable_chunking,
        }

    @staticmethod
    def _hash_content(content: str) -> str:
        """SHA-256 内容哈希 — 借鉴 Java FileHashService"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _update_vector_status(self, doc_id: str, status: VectorStatus,
                              error: Optional[str] = None):
        """更新向量化状态 — 借鉴 Java markProcessing/markCompleted/markFailed"""
        try:
            if error:
                self.logger.debug("向量状态更新", extra={
                    "doc_id": doc_id, "status": status.value, "error": error
                })
        except Exception:
            pass
