from store.structured.redis_client import RedisMemoryClient
from store.structured.mysql_repo import MySQLMemoryRepo
from store.vector.vector_store import VectorMemoryStore
from sandbox.isolation_sandbox import IsolatedAgentSandbox
from sandbox.sandbox_pool import SandboxPool
from cache.breakpoint import BreakpointManager
from core.lifecycle import MemoryLifeCycle
from tools.memory_query import MemoryQueryTool
from tools.memory_export import MemoryExporter

class MemoryHub:
    def __init__(self):
        # 双层存储
        self.struct_redis = RedisMemoryClient()
        self.struct_mysql = MySQLMemoryRepo()
        self.vector_store = VectorMemoryStore()

        # 沙盒与缓存
        self.sandbox_pool = SandboxPool()
        self.breakpoint_mgr = BreakpointManager(self.struct_redis)

        # 工具接口
        self.query_tool = MemoryQueryTool(self)
        self.export_tool = MemoryExporter(self)

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

    # 断点与缓存
    def breakpoint(self) -> BreakpointManager:
        return self.breakpoint_mgr

    # 工具出口
    def query(self) -> MemoryQueryTool:
        return self.query_tool

    def export(self) -> MemoryExporter:
        return self.export_tool