from typing import Dict, Any, Optional
from pydantic import BaseModel

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    error_msg: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    agent_type: Optional[str] = None

class BaseTool:
    def __init__(self):
        self.name = self.__class__.__name__
    
    def execute(self, agent_type: str, params: Dict[str, Any], sandbox: Optional[Any] = None) -> ToolResult:
        """
        执行工具操作
        """
        try:
            result = self._run(params, sandbox)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result,
                agent_type=agent_type
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error_msg=str(e),
                agent_type=agent_type
            )
    
    def _run(self, params: Dict[str, Any], sandbox: Optional[Any] = None) -> Dict[str, Any]:
        """
        工具具体实现
        """
        raise NotImplementedError