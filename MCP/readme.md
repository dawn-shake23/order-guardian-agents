MCP/
├── __init__.py
├── acl/                  # 权限矩阵
├── prompt_manager/       # 专家 Prompt 模板
├── context_manager/      # 上下文切片
├── memory_manager/       # 记忆读写权限
├── tool_guard/           # 工具白名单
├── validator/            # 出入参校验
└── mcp_gateway.py        # 统一入口：Coordinator ↔ Worker 唯一通道