# Order Guardian Agents

基于多智能体协作（Multi-Agent）+ 深度检索（RAG）的支付风控智能诊断分析系统。

---

## 快速开始

```bash
pip install -r requirements.txt
python main.py                  # 全自动运行3个诊断场景
python main.py --interactive    # 交互式诊断 + RAG问答模式
python test_rag.py              # RAG 10步全链路验证
```

---

## 技术栈

### 向量生成与检索

| 组件 | 技术 | 说明 |
|------|------|------|
| 主方案 | 千问 DashScope `text-embedding-v3` | 1024维，OpenAI兼容API，批量上限10条 |
| 回退方案 | 确定性哈希 Embedding | 零依赖，n-gram + MD5哈希 + TF-IDF加权 |
| 向量数据库 | FAISS (faiss-cpu 1.7.4+) | IndexFlatL2，L2欧氏距离精确搜索，磁盘持久化 |
| 混合检索 | 三路召回 + RRF融合 | Vector(语义) + BM25(关键词) + Rule(业务规则过滤) |
| 深度检索 | DeepSearch 多级排序 | 查询分解→多路召回→RRF融合→粗排→精排→交叉验证 |

### 大模型与语言处理

| 组件 | 技术 | 说明 |
|------|------|------|
| 对话模型 | 千问 DashScope `qwen-plus` | 自然语言回答生成 |
| 向量化 | 千问 DashScope `text-embedding-v3` | 1024维向量 |
| 视觉理解 | 千问 DashScope `qwen-vl-plus` | 图片分析/OCR |
| 中文分词 | jieba | 分词 + 关键词提取 + 停用词过滤 |
| 意图识别 | 规则关键词匹配 | 预留ERNIE/BERT升级接口 |
| 文本分块 | LangChain RecursiveCharacterTextSplitter | chunk_size=300, chunk_overlap=50 |

### 智能体架构

| 组件 | 技术 | 说明 |
|------|------|------|
| 协作协议 | 自研MCP (Multi-Agent Cooperation Protocol) | ACL权限矩阵、上下文切片、Memory访问控制 |
| 任务调度 | Harness编排引擎 | DAG依赖执行、并行/串行调配、优先级调度 |
| 生命周期 | AgentLifecycleManager | 8状态跟踪(未初始化→空闲→运行中→完成/失败) |
| 容错机制 | CircuitBreaker + RateLimiter + Heartbeat + ConcurrencyController | 熔断/限流/心跳/并发控制 |

### 记忆与存储

| 组件 | 技术 | 说明 |
|------|------|------|
| 短期记忆 | ShortTermBuffer | 滚动窗口(32条)，TTL过期(300s)，自动压缩 |
| 长期记忆 | LongTermTaskStore | 历史诊断任务持久化，按order_id索引，磁盘存储 |
| 经验沉淀 | ExperienceRepository | 自动学习 error_code→solution 映射 |
| 热存储 | 内存TTL | 结构化业务数据(订单/支付/风控) |
| 冷存储 | JSONL追加式 | 任务日志、审计追踪，按日分文件，自动归档 |
| 规则存储 | JSON配置 | 风控规则配置，支持热加载 |
| 向量存储 | FAISS | 磁盘持久化，重启不丢失不重建 |

### Python 依赖库

| 包名 | 版本 | 用途 |
|------|------|------|
| pydantic | >=2.0 | 数据模型/配置校验 |
| faiss-cpu | >=1.7.4 | 向量索引与L2检索 |
| numpy | >=1.24 | 向量运算 |
| openai | >=1.0.0 | DashScope API调用 |
| pyyaml | >=6.0 | 配置解析 |
| python-json-logger | >=2.0.7 | JSON结构化日志 |
| jieba | >=0.42 | 中文分词 |
| langchain-text-splitters | >=0.3.0 | 递归字符分割器 |
| redis | >=5.0.0 | 结构化缓存(可选) |
| mysql-connector-python | >=8.0.0 | 持久化存储(可选) |
| opentelemetry-* | >=1.20.0 | 可观测性追踪(可选) |

---

## 系统架构

```
main.py                       入口：加载.env → 校验数据 → 初始化 → 诊断场景
│
├── agents/                   专家Agent团队
│   ├── plan_agent.py         PlanAgent: 意图理解 + 步骤规划
│   ├── coordinator.py        Coordinator: 任务调度 + 决策汇总
│   ├── order_agent.py        OrderAgent: 交易查询
│   ├── payment_agent.py      PaymentAgent: 支付核验 + 错误码匹配
│   ├── risk_agent.py         RiskAgent: 风险评估 + 规则命中
│   ├── reconciliation_agent.py  ReconciliationAgent: 资金对账
│   ├── operation_agent.py    OperationAgent: 综合诊断 + 处置方案
│   └── rag_orchestrator.py   Agent+RAG编排器: 工具决策 + 记忆路由
│
├── memory/                   记忆体系
│   ├── embedding.py          EmbeddingProvider: DashScope/确定性哈希/本地模型
│   ├── chunking.py           DocumentChunker: LangChain递归字符分割器
│   ├── memory_tiers.py       ShortTermBuffer + LongTermTaskStore + ExperienceRepository
│   ├── memory_hub.py         MemoryHub: 统一记忆入口
│   ├── storage_router.py     HotStore + ColdStore + RuleStore + StorageRouter
│   ├── knowledge_catalog.py  层级领域目录 + KnowledgeRouter
│   ├── multimodal.py         MultimodalProcessor: 图片分析+OCR+多格式文档
│   └── storage/
│       ├── vector/vector_store.py    FAISS IndexFlatL2 + 磁盘持久化
│       ├── hybrid_search.py          BM25+Vector+Rule混合检索+RRF融合
│       ├── sync_manager.py           双库一致性管理器
│       └── structured/               Redis/MySQL结构化存储
│
├── tools/                    原子工具
│   ├── DeepSearch/
│   │   ├── vector_search.py     VectorSearchTool: Agent调用的向量检索工具
│   │   ├── deep_search.py       DeepSearchEngine: 多级深度检索
│   │   ├── rag_pipeline.py      RAGPipeline: 完整检索+LLM生成闭环
│   │   └── query_rewrite.py     QueryRewriteService: LLM查询改写+候选级联
│   ├── preprocessing.py     jieba分词 + 关键词提取 + 停用词过滤
│   ├── intent_recognizer.py 规则意图识别(领域分类)
│   ├── text_compressor.py   TF-IDF关键句提取 + 结构化字段保留
│   ├── interactive.py       交互式命令行模式(诊断/RAG问答/状态)
│   ├── DataCarry/           数据读写工具
│   ├── BaseTool/            工具基类
│   └── tool_registry.py     工具注册表
│
├── MCP/                     多智能体协作协议(控制平面)
│   ├── mcp_gateway.py       MCPGateway: Coordinator↔Worker唯一通道
│   ├── acl/                 权限矩阵
│   ├── context_manager/     上下文切片 + 会话管理
│   ├── memory_manager/      Memory访问ACL
│   ├── prompt_manager/      专家Prompt模板
│   ├── tool_guard/          工具白名单
│   └── validator/           出入参校验
│
├── prompts/                 Prompt管理
│   ├── system.st            系统角色 + 回答原则 + 格式规范 + 约束
│   ├── user.st              上下文注入 + 问题 + 回答要求
│   ├── rewrite.st           查询改写规则
│   ├── agent_prompts.py     每Agent专属Prompt(角色/约束/输出/行为/禁止)
│   ├── manager.py           PromptManager: 模板加载+缓存+热更新
│   └── security.py          PromptSanitizer: 注入检测+清洗
│
├── infrastructure/          基础设施
│   ├── harness.py           HarnessOrchestrator: 生命周期+优先级+资源+降级
│   ├── data_generator.py    批量测试数据生成器(1000条)
│   ├── kb_loader.py         知识库加载器(分块+Embedding+双写+去重+目录注册)
│   ├── async_pipeline.py    异步管道(Producer→Queue→Consumer模板方法)
│   ├── fake_data.py         内置测试数据
│   ├── mock_infra.py        Mock基础设施(DB/Redis/MQ/Metrics)
│   ├── resilience.py        韧性系统(熔断/限流/心跳/并发控制)
│   ├── decision_engine.py   决策引擎 + 规则引擎
│   ├── approval.py          审批工作流
│   ├── state_persistence.py 状态持久化 + 断点管理
│   └── agent_pool.py        Agent池
│
├── core/                    核心模块
│   ├── errors.py            错误码体系(E1xxx/E2xxx/E3xxx/SYS_xxx)
│   ├── logger.py            JSON结构化日志(控制台WARNING+/文件DEBUG+)
│   ├── tracing.py           OpenTelemetry追踪
│   └── order_state_machine.py 订单状态机
│
└── config.py                全部可调参数集中配置(无硬编码)
```

---

## 启动流程

`python main.py` 执行步骤：

1. 加载 `.env` — 读取 `DASHSCOPE_API_KEY`
2. 初始化追踪 — OpenTelemetry
3. 初始化 MemoryHub — FAISS向量库 + Redis/MySQL + 混合检索引擎
4. 初始化Mock基础设施 — 内存DB/Redis/MQ/Metrics
5. 初始化Embedding — 千问DashScope API / 确定性哈希回退
6. 加载业务数据 — 自动检测 `data/*.json`(1000条)，否则用小数据集
7. 加载知识库 — 200+文档 → 分块 → Embedding → FAISS索引(已持久化则跳过)
8. 初始化记忆体系 — 短期缓冲区 + 长期任务存储 + 经验沉淀库
9. 初始化存储路由 — 热/冷/规则/向量 四级存储
10. 初始化知识目录 — 层级领域目录 + 路由
11. 初始化韧性系统 — 熔断器/限流器/心跳/并发控制
12. 初始化决策引擎 — 规则引擎 + 审批流
13. 初始化状态持久化 — 断点管理器
14. 初始化Agent池 — 注册5个专家Agent + PlanAgent + Coordinator
15. 初始化Harness编排器 — 生命周期管理 + 优先级调度 + 降级策略
16. 初始化工具体系 + MCP网关
17. 启动心跳 — 全部组件健康监控
18. 运行诊断场景 — 3个预设支付异常场景
19. 输出状态报告 — 指标/熔断器/限流器/Agent池/心跳

---

## 运行命令

```bash
python main.py                                      # 全自动3个诊断场景 + 状态报告
python main.py --interactive                        # 交互式诊断 + RAG问答模式
python test_rag.py                                  # RAG 10步全链路验证
python infrastructure/data_generator.py              # 生成1000条测试数据
```

---

## 交互模式命令

```
ORD00001          对指定订单执行完整5-Agent诊断流程
run ORD00001      同上
status            显示系统状态: 任务计数、熔断器、健康检查
clear             清屏
<任意问题>         RAG知识库问答
exit              退出
```
