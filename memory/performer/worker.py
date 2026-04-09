# memory/performer/worker.py
import asyncio
from typing import Callable, Dict, Any
from pydantic import BaseModel
from enum import Enum

class MemoryTaskType(str, Enum):
    SUMMARIZE = "summarize"
    COMPRESS = "compress"
    EMBED = "embed"
    PERSIST = "persist"
    EVICT = "evict"

class MemoryPerformer:
    """
    对标 DeerFlow 2.0 MemoryPerformer
    所有记忆 heavy 操作全部异步丢这里，不阻塞 Agent 主线程
    """
    def __init__(self, worker_count: int = 4):
        self.queue = asyncio.Queue(maxsize=100)
        self.worker_count = worker_count
        self.workers = []
        self.llm = None  # 外部注入
        self.embedding = None

    def start(self):
        for _ in range(self.worker_count):
            task = asyncio.create_task(self._worker_loop())
            self.workers.append(task)

    async def submit(self, task_type: MemoryTaskType, data: Dict[str, Any], callback: Callable):
        await self.queue.put({
            "type": task_type,
            "data": data,
            "callback": callback
        })

    async def _worker_loop(self):
        while True:
            task = await self.queue.get()
            try:
                if task["type"] == MemoryTaskType.SUMMARIZE:
                    await self._do_summarize(task)
                elif task["type"] == MemoryTaskType.EMBED:
                    await self._do_embed(task)
                elif task["type"] == MemoryTaskType.PERSIST:
                    await self._do_persist(task)
            except Exception as e:
                print(f"Performer error: {e}")
            finally:
                self.queue.task_done()

    async def _do_summarize(self, task):
        text = task["data"]["text"]
        # 真实 LLM 摘要
        summary = await self.llm.summarize(text)
        await task["callback"](sslocal://flow/file_open?url=summary&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)

    async def _do_embed(self, task):
        text = task["data"]["text"]
        vec = await self.embedding.embed(text)
        await task["callback"](sslocal://flow/file_open?url=vec&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)