Tools/
├── __init__.py
├── BaseTool/                # 工具基类：统一规范、元数据、生命周期
│   ├── __init__.py
│   └── base_tool.py
├── DataCarry/               # 数据搬运类工具：记忆/沙盒/缓存/数据读写
│   ├── __init__.py
│   ├── memory_rw.py         # 结构化记忆读写
│   ├── sandbox_rw.py        # 沙盒隔离读写
│   ├── cache_manage.py      # 缓存断点续传
│   └── data_sync.py         # 跨模块数据同步
├── DeepSearch/              # 深度检索类工具：向量+结构化混合检索
│   ├── __init__.py
│   ├── vector_search.py     # 业务向量库检索
│   ├── struct_search.py     # 结构化数据检索
│   └── hybrid_search.py     # 混合检索
├── RuleCheck/               # 规则校验类工具：业务/权限/数据校验
│   ├── __init__.py
│   ├── acl_check.py         # 权限校验
│   ├── biz_rule_check.py    # 业务规则校验
│   ├── data_format_check.py # 数据格式校验
│   └── sandbox_isolate_check.py # 沙盒隔离校验
├── tool_registry.py         # 工具注册中心：MCP统一调度
└── tool_lifecycle.py        # 工具全局生命周期管控

统一元数据：所有工具携带唯一标识、权限、版本、输入输出 Schema、适用 Agent 范围
完整生命周期：初始化→权限校验→执行→后置处理→异常处理→资源清理
MCP 全权管控：工具调用、权限、资源均由 MCP 拦截管控，禁止直接调用
沙盒隔离：工具操作严格绑定 Agent 沙盒，禁止越权访问
标准化交互：输入输出统一格式，支持 Agent 间、Tool 间无歧义交互
熔断限流：内置超时、重试、熔断机制，防止系统打爆