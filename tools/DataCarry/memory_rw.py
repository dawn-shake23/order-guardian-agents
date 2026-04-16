from typing import Dict, Any, Optional
from Tools.BaseTool import BaseTool, ToolMeta
from Memory.memory_hub import MemoryHub

class MemoryReadWriteTool(BaseTool):
    def __init__(self, memory_hub: MemoryHub):
        meta = ToolMeta(
            tool_name="memory_read_write",
            tool_description="结构化记忆读写，支持会话/步骤数据存取",
            input_schema={
                "action": "read/write",
                "session_id": "str",
                "step_id": "Optional[int]",
                "data": "Optional[Dict]"
            },
            output_schema={
                "data": "Optional[Dict]",
                "operate_result": "bool"
            },
            allowed_agent_types=["coordinator", "order", "payment", "risk", "reconciliation"],
            need_memory=True,
            need_sandbox=False
        )
        self.memory_hub = memory_hub
        super().__init__(meta)

    def _on_initialize(self) -> None:
        pass

    def _pre_check_logic(self, agent_type: str, params: Dict[str, Any]) -> bool:
        return "action" in params and "session_id" in params

    def _execute_logic(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any]) -> Dict[str, Any]:
        action = params["action"]
        session_id = params["session_id"]
        if action == "read":
            data = self.memory_hub.struct().get_session_memory(session_id)
            return {"operate_result": True, "data": data}
        elif action == "write":
            self.memory_hub.struct().set_session_memory(params["data"])
            return {"operate_result": True}
        return {"operate_result": False, "error": "不支持的操作"}

    def _on_destroy(self) -> None:
        pass