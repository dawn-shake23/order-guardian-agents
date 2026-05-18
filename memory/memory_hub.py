from memory.storage.structured.redis_client import RedisMemoryClient
from memory.storage.structured.mysql_repo import MySQLMemoryRepo
from memory.storage.vector.vector_store import VectorMemoryStore
from memory.storage.sync_manager import DataSyncManager
from memory.storage.hybrid_search import HybridSearchEngine
from memory.sandbox.isolation_sandbox import IsolatedAgentSandbox
from memory.sandbox.sandbox_pool import SandboxPool
from memory.cache.breakpoint import BreakpointManager
from memory.core.lifecycle import MemoryLifeCycle

class MemoryHub:
    def __init__(self):
        # 双层存储
        self.struct_redis = RedisMemoryClient()
        self.struct_mysql = MySQLMemoryRepo()
        self.vector_store = VectorMemoryStore(dimension=1024)

        # 双库一致性管理器
        self.sync_manager = DataSyncManager(self.struct_mysql, self.vector_store)

        # 混合检索引擎
        self.hybrid_search = HybridSearchEngine(self.vector_store, self.struct_mysql)

        # 沙盒与缓存
        self.sandbox_pool = SandboxPool()
        self.breakpoint_mgr = BreakpointManager(self.struct_redis)

        # 工具接口 - 延迟导入避免循环依赖
        self._query_tool = None
        self._export_tool = None

    # 沙盒生命周期
    def create_sandbox(self, session_id: str, step_id: int, agent_type: str) -> IsolatedAgentSandbox:
        meta = MemoryLifeCycle.create_sandbox(session_id, step_id, agent_type)
        sandbox = IsolatedAgentSandbox(meta)
        key = f"{session_id}:{step_id}:{agent_type}"
        self.sandbox_pool.acquire(key, sandbox)
        return sandbox

    def destroy_sandbox(self, session_id: str, step_id: int, agent_type: str):
        key = f"{session_id}:{step_id}:{agent_type}"
        self.sandbox_pool.release(key)

    # 存储出口
    def struct(self) -> RedisMemoryClient:
        return self.struct_redis

    def vector(self) -> VectorMemoryStore:
        return self.vector_store

    # 双库一致性出口
    def sync(self) -> DataSyncManager:
        return self.sync_manager

    # 混合检索出口
    def hybrid(self) -> HybridSearchEngine:
        return self.hybrid_search

    # 断点与缓存
    def breakpoint(self) -> BreakpointManager:
        return self.breakpoint_mgr

    # 工具出口 - 延迟导入避免循环依赖
    def query(self):
        if self._query_tool is None:
            from tools.memory_query import MemoryQueryTool
            self._query_tool = MemoryQueryTool(self)
        return self._query_tool

    def export(self):
        if self._export_tool is None:
            from tools.memory_export import MemoryExporter
            self._export_tool = MemoryExporter(self)
        return self._export_tool