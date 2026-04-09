# memory/storage/engine.py
class ShortTermStorage:
    def __init__(self, window_size: int = 32):
        self.window_size = window_size
        self.buffer = []

    def add(self, item):
        self.buffer.append(item)
        if len(self.buffer) > self.window_size:
            self.buffer.pop(0)

class MidTermStorage:
    def __init__(self):
        self.db = {}  # 可替换为 Redis

    def set(self, session_id, data):
        self.db[session_id] = data

    def get(self, session_id):
        return self.db.get(session_id)

class LongTermStorage:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    async def insert(self, text, metadata):
        await self.vector_store.insert(text, metadata)

    async def search(self, query, top_k=5):
        return await self.vector_store.search(query, top_k)