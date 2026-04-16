from typing import Dict, Any, List
from Tools.BaseTool import BaseTool, ToolMeta
from Memory.memory_hub import MemoryHub

class VectorSearchTool(BaseTool):
    def __init__(self, memory_hub: MemoryHub):
        meta = ToolMeta(
            tool_name="vector_search",
            tool_description="业务手册向量库检索，按Agent业务域隔离检索",
            input_schema={
                "query": "str",
                "biz_domain": "str",
                "top_k": "int"
            },
            output_schema={
                "search_result": "List[Dict]",
                "total": "int"
            },
            allowed_agent_types=["order", "payment", "risk", "reconciliation"],
            need_memory=True
        )
        self.memory_hub = memory_hub
        super().__init__(meta)

    def _on_initialize(self) -> None:
        pass

    def _pre_check_logic(self, agent_type: str, params: Dict[str, Any]) -> bool:
        return "query" in params and "biz_domain" in params

    def _execute_logic(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any]) -> Dict[str, Any]:
        query = params["query"]
        biz_domain = params["biz_domain"]
        top_k = params.get("top_k", 3)
        result = self.memory_hub.vector().search_by_domain(query, biz_domain, top_k)
        return {
            "search_result": [item.model_dump() for item in result],
            "total": len(result)
        }