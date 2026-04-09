# memory/engine.py
from memory.cache.ca_cache import CACache
from memory.performer.worker import MemoryPerformer
from memory.storage.engine import ShortTermStorage, MidTermStorage, LongTermStorage

class MemoryEngine:
    """
    对标：
    - 字节 DeerFlow 2.0 MemorySystem
    - 阿里 AgentScope MemoryManager
    完整底层，无任何黑盒
    """
    def __init__(self, llm, embedding, vector_store):
        # 缓存层
        self.ca_cache = CACache()

        # 执行层
        self.performer = MemoryPerformer(worker_count=4)
        self.performer.llm = llm
        self.performer.embedding = embedding

        # 存储层
        self.short = ShortTermStorage(window_size=32)
        self.mid = MidTermStorage()
        self.long = LongTermStorage(vector_store)

        # 策略
        self.compress_threshold = 0.7
        self.performer.start()

    # ------------------------------
    # 短期记忆 + CA Cache
    # ------------------------------
    async def add_short(self, session_id, text):
        self.short.add(text)
        # 达到阈值自动压缩（丢给 Performer）
        if len(self.short.buffer) > self.short.window_size * self.compress_threshold:
            await self.performer.submit(
                "summarize",
                {"text": "\n".join(self.short.buffer)},
                callback=lambda sum_text: self.short.buffer.clear() or self.short.add(sum_text)
            )

    # ------------------------------
    # 中期任务记忆（会话状态）
    # ------------------------------
    def set_mid(self, session_id, data):
        self.mid.set(session_id, data)

    def get_mid(self, session_id):
        return self.mid.get(session_id)

    # ------------------------------
    # 长期向量记忆
    # ------------------------------
    async def add_long(self, session_id, text, metadata):
        await self.performer.submit(
            "embed",
            {"text": text},
            callback=lambda vec: self.long.vector_store.insert(vec, metadata)
        )

    async def search_long(self, query, top_k=5):
        return await self.long.search(query, top_k)