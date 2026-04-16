
# Memory Layer —— 多Agent系统记忆中心
## 定位
统一的记忆与上下文管理层，严格遵循：隔离、权限、生命周期、可观测、防过载。

## 分层
1. models          统一强校验模型
2. core            生命周期、隔离、配额
3. store           结构化(Redis/MySQL) + 向量库
4. sandbox         SubAgent 独立沙盒（强隔离）
5. cache           TTL 缓存、断点续传
6. tools           ToC 工具接口（查询/导出/鉴权）
7. memory_hub      唯一对外入口

1. 设计核心原则
严格遵循权限隔离、全生命周期管控、沙盒内存隔绝、双层存储分离、MCP 统一管控、层间解耦、防过载、ToC 兼容工程标准，杜绝越权、内存泄漏、数据污染，贴合风控级多 Agent 调度架构。
2. 整体架构分层
Memory/
├── README.md               # 本架构说明
├── models/                 # 统一Pydantic数据模型（全字段定义）
│   ├── struct_memory.py    # 结构化记忆模型（Redis/MySQL）
│   ├── vector_memory.py    # 向量记忆模型（向量数据库）
│   ├── sandbox_memory.py   # 沙盒隔离内存模型
│   └── cache_memory.py     # 缓存模型（含TTL）
├── core/                   # 核心管控逻辑
│   ├── lifecycle.py        # 全生命周期管理（创建/使用/销毁/GC）
│   ├── isolation.py        # 沙盒强隔离、权限校验
│   └── quota_manager.py    # 内存配额、防打爆管控
├── store/                  # 双层存储实现
│   ├── structured/         # 结构化存储（Redis+MySQL）
│   │   ├── redis_client.py # 会话/断点/缓存（带TTL）
│   │   └── mysql_repo.py   # 持久化结构化数据
│   └── vector/             # 向量存储（业务知识库）
│       └── vector_store.py # 向量检索（仅提供接口，MCP管控）
├── sandbox/                # SubAgent独立沙盒
│   ├── sandbox_pool.py     # 沙盒池化管理
│   └── isolation_sandbox.py# 独立隔离内存空间
├── cache/                  # 缓存层
│   ├── cache_ttl.py        # 分级TTL管控
│   └── breakpoint.py       # 断点续传、异常恢复
├── tools/                  # ToC/Agent工具接口
│   ├── memory_query.py     # 记忆查询
│   ├── memory_export.py    # 数据导出
│   └── memory_auth.py      # 工具权限校验
└── memory_hub.py           # 统一入口（仅对外暴露，MCP全权管控）

3. 核心职责界定
双层存储分离
结构化存储：Redis（缓存、断点、会话、临时数据，带 TTL）+ MySQL（持久化订单 / 步骤 / 会话数据）
向量存储：业务手册、规则、流程向量库，仅做检索数据存储
沙盒隔离：每个 SubAgent 拥有独立内存空间，互不渗透、权限隔绝、自动销毁
全生命周期：统一创建、配额限制、TTL 过期、主动 GC、用完即销毁
权限管控：Memory 不做权限判断，仅提供数据接口，所有读写 / 检索由 MCP 鉴权
缓存设计：分级 TTL、内存配额、防重复计算、断点续传
工具兼容：预留 ToC 工具、Agent 间交互接口，全权限校验
4. 层间交互规范
Coordinator：仅通过 MCP 调用 Memory，不直接操作存储
MCP：Memory 唯一管控方，负责权限校验、沙盒分配、检索授权、生命周期调度
Memory：仅提供数据读写 / 存储 / 检索接口，无业务逻辑、无权限判断
SubAgent：仅能访问 MCP 分配的专属沙盒，无全局内存访问权
5. 关键管控点
内存配额：单沙盒字段数 / 内存大小限制，防止打爆
分级 TTL：沙盒（5 分钟）、步骤缓存（30 分钟）、会话（1 小时）、向量（永久）
隔离校验：Agent 只能访问自身沙盒，禁止跨 Agent 读写
生命周期：沙盒创建→分配→使用→过期→GC 销毁，全程闭环
检索管控：向量检索必须经 MCP 按 Agent 业务域鉴权