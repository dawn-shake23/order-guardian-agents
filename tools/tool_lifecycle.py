from Tools.tool_registry import tool_registry

class ToolLifeCycleManager:
    @staticmethod
    def global_init(memory_hub):
        """全局初始化所有工具"""
        # 注册并初始化DataCarry工具
        from Tools.DataCarry.memory_rw import MemoryReadWriteTool
        from Tools.DataCarry.sandbox_rw import SandboxReadWriteTool
        tool_registry.register_tool("memory_read_write", MemoryReadWriteTool)
        tool_registry.register_tool("sandbox_read_write", SandboxReadWriteTool)

        # 注册并初始化DeepSearch工具
        from Tools.DeepSearch.vector_search import VectorSearchTool
        tool_registry.register_tool("vector_search", VectorSearchTool)

        # 注册并初始化RuleCheck工具
        from Tools.RuleCheck.acl_check import AgentAclCheckTool
        tool_registry.register_tool("agent_acl_check", AgentAclCheckTool)

        # 初始化实例
        tool_registry.init_tool_instance("memory_read_write", memory_hub)
        tool_registry.init_tool_instance("sandbox_read_write")
        tool_registry.init_tool_instance("vector_search", memory_hub)
        tool_registry.init_tool_instance("agent_acl_check")

    @staticmethod
    def global_destroy():
        """全局销毁所有工具，释放资源"""
        tool_registry.destroy_all()