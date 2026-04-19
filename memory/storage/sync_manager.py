import time
import hashlib
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from memory.storage.structured.mysql_repo import MySQLMemoryRepo
from memory.storage.vector.vector_store import VectorMemoryStore
from core.logger import get_logger


class SyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"


class SyncOperation(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    SOFT_DELETE = "soft_delete"
    ARCHIVE = "archive"


@dataclass
class SyncRecord:
    record_id: str
    operation: SyncOperation
    table: str
    doc_id: str
    data: Dict[str, Any]
    embedding: Optional[List[float]] = None
    status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    error_msg: Optional[str] = None

    @property
    def is_idempotent(self) -> bool:
        return self.operation in (SyncOperation.INSERT, SyncOperation.UPDATE, SyncOperation.SOFT_DELETE)


class DataSyncManager:
    """
    双库一致性管理器
    保证 MySQL（结构化） + 向量库（FAISS/Qdrant） 数据同步
    核心策略：写时双写 + 失败补偿 + 幂等重试
    """

    def __init__(self, mysql_repo: MySQLMemoryRepo, vector_store: VectorMemoryStore):
        self.mysql = mysql_repo
        self.vector = vector_store
        self.logger = get_logger("data_sync")
        self._sync_queue: List[SyncRecord] = []
        self._compensation_log: List[SyncRecord] = []

    def _generate_record_id(self, operation: SyncOperation, table: str, doc_id: str) -> str:
        raw = f"{operation.value}:{table}:{doc_id}:{time.time()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def insert(self, table: str, doc_id: str, data: Dict[str, Any],
               embedding: Optional[List[float]] = None, metadata: Optional[Dict] = None) -> SyncRecord:
        record = SyncRecord(
            record_id=self._generate_record_id(SyncOperation.INSERT, table, doc_id),
            operation=SyncOperation.INSERT,
            table=table,
            doc_id=doc_id,
            data=data,
            embedding=embedding
        )
        return self._execute_sync(record, metadata)

    def update(self, table: str, doc_id: str, data: Dict[str, Any],
               embedding: Optional[List[float]] = None, metadata: Optional[Dict] = None) -> SyncRecord:
        record = SyncRecord(
            record_id=self._generate_record_id(SyncOperation.UPDATE, table, doc_id),
            operation=SyncOperation.UPDATE,
            table=table,
            doc_id=doc_id,
            data=data,
            embedding=embedding
        )
        return self._execute_sync(record, metadata)

    def delete(self, table: str, doc_id: str, vector_index: Optional[int] = None) -> SyncRecord:
        record = SyncRecord(
            record_id=self._generate_record_id(SyncOperation.DELETE, table, doc_id),
            operation=SyncOperation.DELETE,
            table=table,
            doc_id=doc_id,
            data={},
        )
        record._vector_index = vector_index
        return self._execute_sync(record)

    def soft_delete(self, table: str, doc_id: str, data: Dict[str, Any]) -> SyncRecord:
        data_copy = dict(data)
        data_copy["is_deleted"] = True
        data_copy["deleted_at"] = time.time()
        record = SyncRecord(
            record_id=self._generate_record_id(SyncOperation.SOFT_DELETE, table, doc_id),
            operation=SyncOperation.SOFT_DELETE,
            table=table,
            doc_id=doc_id,
            data=data_copy,
        )
        return self._execute_sync(record)

    def archive(self, table: str, doc_id: str, data: Dict[str, Any]) -> SyncRecord:
        data_copy = dict(data)
        data_copy["is_archived"] = True
        data_copy["archived_at"] = time.time()
        record = SyncRecord(
            record_id=self._generate_record_id(SyncOperation.ARCHIVE, table, doc_id),
            operation=SyncOperation.ARCHIVE,
            table=table,
            doc_id=doc_id,
            data=data_copy,
        )
        return self._execute_sync(record)

    def _execute_sync(self, record: SyncRecord, metadata: Optional[Dict] = None) -> SyncRecord:
        """
        核心同步逻辑：先写结构化库（主），再写向量库（从）
        失败时进入补偿队列，保证最终一致性
        """
        self.logger.info("双库同步开始", extra={
            "record_id": record.record_id,
            "operation": record.operation.value,
            "table": record.table,
            "doc_id": record.doc_id
        })

        # Step 1: 写结构化库（主库）
        struct_ok = self._sync_structured(record)
        if not struct_ok:
            record.status = SyncStatus.FAILED
            record.error_msg = "结构化库写入失败"
            self._compensation_log.append(record)
            self.logger.error("结构化库写入失败，进入补偿队列", extra={"record_id": record.record_id})
            return record

        # Step 2: 写向量库（从库）
        vector_ok = self._sync_vector(record, metadata)
        if not vector_ok:
            record.status = SyncStatus.FAILED
            record.error_msg = "向量库写入失败，结构化库已写入"
            self._compensation_log.append(record)
            self.logger.error("向量库写入失败，进入补偿队列", extra={"record_id": record.record_id})
            return record

        record.status = SyncStatus.SYNCED
        self.logger.info("双库同步完成", extra={"record_id": record.record_id})
        return record

    def _sync_structured(self, record: SyncRecord) -> bool:
        try:
            if record.operation == SyncOperation.INSERT:
                return self.mysql.save(record.table, record.doc_id, record.data)
            elif record.operation == SyncOperation.UPDATE:
                return self.mysql.save(record.table, record.doc_id, record.data)
            elif record.operation == SyncOperation.DELETE:
                return self.mysql.delete(record.table, record.doc_id)
            elif record.operation == SyncOperation.SOFT_DELETE:
                return self.mysql.save(record.table, record.doc_id, record.data)
            elif record.operation == SyncOperation.ARCHIVE:
                return self.mysql.save(record.table, record.doc_id, record.data)
            return False
        except Exception as e:
            self.logger.error("结构化库同步异常", extra={"error": str(e)})
            return False

    def _sync_vector(self, record: SyncRecord, metadata: Optional[Dict] = None) -> bool:
        try:
            if record.operation in (SyncOperation.INSERT, SyncOperation.UPDATE):
                if record.embedding is None:
                    self.logger.info("无embedding，跳过向量库同步", extra={"doc_id": record.doc_id})
                    return True
                meta = metadata or {"doc_id": record.doc_id, "table": record.table}
                meta.update(record.data)
                self.vector.add(record.embedding, meta)
                return True
            elif record.operation == SyncOperation.DELETE:
                vector_idx = getattr(record, '_vector_index', None)
                if vector_idx is not None:
                    self.vector.delete(vector_idx)
                return True
            elif record.operation in (SyncOperation.SOFT_DELETE, SyncOperation.ARCHIVE):
                return True
            return True
        except Exception as e:
            self.logger.error("向量库同步异常", extra={"error": str(e)})
            return False

    def retry_failed(self) -> int:
        """
        补偿重试：对失败记录进行幂等重试
        """
        retried = 0
        remaining = []
        for record in self._compensation_log:
            if record.retry_count >= record.max_retries:
                self.logger.error("超过最大重试次数，放弃同步", extra={"record_id": record.record_id})
                continue
            record.retry_count += 1
            result = self._execute_sync(record)
            if result.status == SyncStatus.SYNCED:
                retried += 1
            else:
                remaining.append(record)
        self._compensation_log = remaining
        self.logger.info("补偿重试完成", extra={"retried": retried, "remaining": len(remaining)})
        return retried

    def get_compensation_status(self) -> Dict[str, Any]:
        return {
            "pending_count": len(self._compensation_log),
            "records": [
                {"record_id": r.record_id, "operation": r.operation.value,
                 "doc_id": r.doc_id, "retry_count": r.retry_count, "error": r.error_msg}
                for r in self._compensation_log
            ]
        }
