from MCP.acl.acl_matrix import AGENT_ACL
from MCP.prompt_manager.prompts import PROMPTS
from MCP.memory_manager.memory_acl import MemoryACL
from MCP.context_manager.slicer import ContextSlicer
from Memory.core.context_memory import ContextMemory

class MCPGateway:
    def __init__(self):
        self.prompt_tpl = PROMPTS

    def build_agent_exec_context(
        self,
        agent_type: str,
        global_context: dict,
        context_memory: ContextMemory
    ) -> dict:
        """
        MCP 核心：
        1. 做权限判断
        2. 做上下文切片
        3. 组装专属 Prompt
        4. 不操作 Memory，只告诉别人能不能读
        """
        # 1. 权限：是否允许读全局上下文
        if not MemoryACL.can_read_global(agent_type):
            raise PermissionError(f"{agent_type} 无全局上下文权限")

        # 2. 字段白名单
        allowed_fields = AGENT_ACL[agent_type]["fields"]

        # 3. 上下文切片（MCP 控制，Memory 只存结果）
        sliced_ctx = ContextSlicer.slice_by_acl(
            agent_type, global_context, allowed_fields
        )
        context_memory.set_sliced(agent_type, sliced_ctx)

        # 4. 生成该专家专属 Prompt
        prompt = self.prompt_tpl[agent_type].format(context=sliced_ctx)

        # 5. 工具权限
        allowed_tools = AGENT_ACL[agent_type]["tools"]

        return {
            "agent_type": agent_type,
            "prompt": prompt,
            "sliced_context": sliced_ctx,
            "allowed_tools": allowed_tools,
            "can_read_memory": MemoryACL.can_read_global(agent_type),
            "can_write_memory": MemoryACL.can_write_global(agent_type)
        }