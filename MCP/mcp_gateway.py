from MCP.prompt_manager.prompts import PROMPTS
from MCP.context_manager.slicer import ContextSlicer
from MCP.memory_manager.memory_acl import MemoryACL
from MCP.tool_guard.tool_acl import ToolACL
from MCP.validator.step_validator import StepValidator

class MCPGateway:
    def __init__(self):
        self.prompts = PROMPTS

    def build_agent_request(self, expert_type: str, full_context: dict) -> dict:
        # 1. 权限：上下文切片
        sliced = ContextSlicer.slice(expert_type, full_context)

        # 2. 权限：记忆读写判断
        can_read_mem = MemoryACL.can_read(expert_type)

        # 3. 权限：工具白名单
        tools = ToolACL.allowed_tools(expert_type)

        # 4. 注入专属 Prompt
        prompt = self.prompts[expert_type].format(context=sliced)

        return {
            "expert_type": expert_type,
            "prompt": prompt,
            "context": sliced,
            "allowed_tools": tools,
            "can_read_memory": can_read_mem
        }

    def validate_agent_result(self, expert_type: str, result: dict):
        StepValidator.validate_output(expert_type, result)
        return result