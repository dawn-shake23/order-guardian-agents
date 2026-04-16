MCP/
├── __init__.py
├── acl/                  # 权限矩阵
├── prompt_manager/       # 专家 Prompt 模板
├── context_manager/      # 上下文切片
├── memory_manager/       # 记忆读写权限
├── tool_guard/           # 工具白名单
├── validator/            # 出入参校验
└── mcp_gateway.py        # 统一入口：Coordinator ↔ Worker 唯一通道

MCP 不存储记忆，只做 ** Memory 访问控制 **：
哪个 Agent 可以读 Memory
哪个 Agent 可以写 Memory
每个 Agent 能读到哪些字段（上下文切片）
哪些步骤可以把结果写入记忆
哪些信息禁止进入记忆（脱敏、风控）
记忆过期策略、隔离策略
MCP = Memory 的门卫 + 路由器 + 过滤器