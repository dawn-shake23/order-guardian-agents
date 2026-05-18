"""
Async Pipeline — 异步任务管道
借鉴 Java AbstractStreamProducer / AbstractStreamConsumer 模板方法模式：
- Producer: 投递任务到队列
- Consumer: 消费任务并执行
- 支持：重试、状态追踪、批量处理、优雅关闭

默认使用内存队列，可选 Redis Stream 作为后端
"""
import time
import threading
import queue
import json
import hashlib
from typing import Dict, Any, Optional, List, TypeVar, Generic, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
from core.logger import get_logger

T = TypeVar("T")


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class AsyncTask(Generic[T]):
    """异步任务"""
    task_id: str
    payload: T
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: Optional[str] = None
    result: Optional[Any] = None

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class TaskQueue(Generic[T]):
    """任务队列 — 支持内存队列和 Redis Stream 两种后端"""

    def __init__(self, name: str, maxsize: int = 1000):
        self.name = name
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._dead_letter: List[AsyncTask] = []
        self.logger = get_logger(f"task_queue.{name}")

    def put(self, task: AsyncTask[T]) -> bool:
        try:
            self._queue.put_nowait(task)
            return True
        except queue.Full:
            self.logger.warning("任务队列已满", extra={"queue": self.name})
            return False

    def get(self, timeout: float = 1.0) -> Optional[AsyncTask[T]]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def to_dead_letter(self, task: AsyncTask[T]):
        self._dead_letter.append(task)

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def dead_letter_count(self) -> int:
        return len(self._dead_letter)


class AbstractProducer(Generic[T], ABC):
    """
    抽象生产者 — 借鉴 Java AbstractStreamProducer<T>
    负责将任务投递到队列
    """

    def __init__(self, task_queue: TaskQueue[T]):
        self.queue = task_queue
        self.logger = get_logger(f"producer.{task_queue.name}")

    def submit(self, payload: T, task_id: Optional[str] = None) -> Optional[str]:
        """提交任务"""
        task_id = task_id or self._generate_task_id(payload)

        task = AsyncTask(
            task_id=task_id,
            payload=payload,
            status=TaskStatus.PENDING,
            max_retries=self.max_retries(),
        )

        if self.queue.put(task):
            self.logger.info("任务已提交", extra={
                "task_id": task_id, "queue": self.queue.name
            })
            self._on_submit(task)
            return task_id

        return None

    def _generate_task_id(self, payload: T) -> str:
        raw = f"{self.queue.name}:{hashlib.md5(str(payload).encode()).hexdigest()[:8]}"
        return raw

    @abstractmethod
    def max_retries(self) -> int:
        pass

    def _on_submit(self, task: AsyncTask[T]):
        """提交后的回调（子类可覆盖）"""
        pass


class AbstractConsumer(Generic[T], ABC):
    """
    抽象消费者 — 借鉴 Java AbstractStreamConsumer<T>
    负责从队列消费任务并执行

    生命周期：poll → mark_processing → process → mark_completed / mark_failed
    """

    def __init__(self, task_queue: TaskQueue[T], batch_size: int = 10,
                 poll_interval: float = 1.0):
        self.queue = task_queue
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_count = 0
        self._failed_count = 0
        self.logger = get_logger(f"consumer.{task_queue.name}")

    def start(self):
        """启动消费者线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True,
            name=f"consumer-{self.queue.name}"
        )
        self._thread.start()
        self.logger.info("消费者已启动", extra={
            "queue": self.queue.name,
            "batch_size": self.batch_size
        })

    def stop(self):
        """停止消费者"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        self.logger.info("消费者已停止", extra={
            "queue": self.queue.name,
            "processed": self._processed_count,
            "failed": self._failed_count
        })

    def _loop(self):
        """主消费循环"""
        while self._running:
            try:
                task = self.queue.get(timeout=self.poll_interval)
                if task is None:
                    continue

                self._process_one(task)

            except Exception as e:
                self.logger.error("消费循环异常", extra={"error": str(e)})

    def _process_one(self, task: AsyncTask[T]):
        """处理单个任务"""
        try:
            # Step 1: 标记处理中 — 借鉴 markProcessing()
            task.status = TaskStatus.PROCESSING
            task.updated_at = time.time()
            self._on_status_change(task, TaskStatus.PROCESSING)

            # Step 2: 执行业务逻辑 — 借鉴 processBusiness()
            self.process(task.payload)

            # Step 3: 标记完成 — 借鉴 markCompleted()
            task.status = TaskStatus.COMPLETED
            task.updated_at = time.time()
            self._on_status_change(task, TaskStatus.COMPLETED)
            self._processed_count += 1

        except Exception as e:
            task.error = str(e)
            task.retry_count += 1

            if task.can_retry:
                # 重试 — 借鉴 retryMessage()
                task.status = TaskStatus.RETRYING
                task.updated_at = time.time()
                self.logger.info("任务重试", extra={
                    "task_id": task.task_id,
                    "retry": task.retry_count,
                    "max": task.max_retries
                })
                self.queue.put(task)
            else:
                # 失败 — 借鉴 markFailed()
                task.status = TaskStatus.FAILED
                task.updated_at = time.time()
                self._on_status_change(task, TaskStatus.FAILED)
                self.queue.to_dead_letter(task)
                self._failed_count += 1
                self.logger.error("任务失败", extra={
                    "task_id": task.task_id,
                    "error": str(e),
                    "retries": task.retry_count
                })

    @abstractmethod
    def process(self, payload: T):
        """业务处理逻辑（子类实现）"""
        pass

    def _on_status_change(self, task: AsyncTask[T], status: TaskStatus):
        """状态变更回调（子类可覆盖）"""
        pass

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "processed": self._processed_count,
            "failed": self._failed_count,
            "queue_size": self.queue.size,
            "dead_letter": self.queue.dead_letter_count,
            "running": self._running,
        }


# ============================================================
# 具体实现：知识库向量化管道
# ============================================================

@dataclass
class VectorizePayload:
    """向量化任务载荷 — 借鉴 Java VectorizePayload"""
    kb_id: str
    content: str
    biz_domain: str = "order"


class VectorizeProducer(AbstractProducer[VectorizePayload]):
    """向量化任务生产者 — 借鉴 Java VectorizeStreamProducer"""

    def max_retries(self) -> int:
        return 3


class VectorizeConsumer(AbstractConsumer[VectorizePayload]):
    """向量化任务消费者 — 借鉴 Java VectorizeStreamConsumer"""

    def __init__(self, task_queue: TaskQueue, kb_loader=None, batch_size: int = 10):
        super().__init__(task_queue, batch_size=batch_size, poll_interval=1.0)
        self.kb_loader = kb_loader

    def process(self, payload: VectorizePayload):
        """执行向量化 — 借鉴 Java processBusiness()"""
        if self.kb_loader:
            self.kb_loader.add_document(
                doc_id=payload.kb_id,
                title=payload.kb_id,
                content=payload.content,
                biz_domain=payload.biz_domain
            )
        else:
            self.logger.info("模拟向量化", extra={
                "kb_id": payload.kb_id,
                "content_length": len(payload.content)
            })


class AsyncPipelineManager:
    """
    异步管道管理器 — 统一管理生产者和消费者
    借鉴 Java 的 Stream 架构
    """

    def __init__(self):
        self._queues: Dict[str, TaskQueue] = {}
        self._producers: Dict[str, AbstractProducer] = {}
        self._consumers: Dict[str, AbstractConsumer] = {}
        self.logger = get_logger("async_pipeline")

    def create_pipeline(self, name: str, payload_type: type,
                        producer_cls: type, consumer_cls: type,
                        producer_kwargs: Optional[Dict] = None,
                        consumer_kwargs: Optional[Dict] = None) -> tuple:
        """创建一条完整的管道：队列 + 生产者 + 消费者"""
        task_queue = TaskQueue(name)
        self._queues[name] = task_queue

        producer = producer_cls(task_queue, **(producer_kwargs or {}))
        consumer = consumer_cls(task_queue, **(consumer_kwargs or {}))

        self._producers[name] = producer
        self._consumers[name] = consumer

        self.logger.info("管道创建完成", extra={"pipeline_name": name})
        return producer, consumer

    def start_all_consumers(self):
        """启动所有消费者"""
        for name, consumer in self._consumers.items():
            consumer.start()

    def stop_all_consumers(self):
        """停止所有消费者"""
        for name, consumer in self._consumers.items():
            consumer.stop()

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        return {name: c.stats for name, c in self._consumers.items()}
