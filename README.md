# Order Guardian Agents

基于多智能体协作（Multi-Agent）+ 深度检索（DeepSearch）的**双层订单异常治理系统**。

---

## 快速开始

```bash
# 1. 安装依赖（仅首次）
pip install -r requirements.txt

# 2. 配置 API Key（编辑 .env 文件，已有默认值）
#    DASHSCOPE_API_KEY=sk-your-key

# 3. 启动系统
python main.py

# 4. RAG 闭环验证
python test_rag.py
```

---

## 完整技术栈

### 向量生成方案

| 组件 | 技术 | 说明 |
|------|------|------|
| **主方案** | 千问 DashScope `text-embedding-v3` | 1024维，OpenAI兼容API，批量上限10条 |
| **回退方案** | 确定性哈希 Embedding | 零依赖，1024维，字符n-gram+MD5哈希+TF-IDF加权 |
| **多模态** | 千问 `qwen-vl-plus` 视觉理解 + `tongyi-embedding-vision-01` | 图片OCR+描述+向量化 |
| **SDK** | `openai>=1.0.0` | 通过 DashScope 兼容接口调用 |

### 检索引擎

| 组件 | 技术 | 说明 |
|------|------|------|
| **向量数据库** | FAISS (faiss-cpu 1.7.4+) | IndexFlatL2，内存索引，精确搜索 |
| **距离算法** | L2 欧氏距离 | FAISS IndexFlatL2 |
| **混合检索** | 三路召回 + RRF 融合 | Vector(语义) + BM25(关键词) + Rule(业务规则) |
| **深度检索** | DeepSearch 多级排序 | 查询理解→多路召回→RRF融合→粗排→精排→交叉验证 |
| **上下文管理** | 噪声过滤 + 上下文窗口压缩 | n-gram相关性校验 + Token预算动态截断 |

### 大模型

| 组件 | 技术 | 说明 |
|------|------|------|
| **Embedding** | DashScope text-embedding-v3 | 1024维向量 |
| **视觉理解** | DashScope qwen-vl-plus | 图片分析/OCR |
| **LLM调用** | 可插拔 LLMClient | 当前Mock模式，支持 qwen/gpt/llama |

### Python 依赖库

| 包名 | 版本 | 用途 |
|------|------|------|
| `pydantic` | >=2.0 | 数据模型/配置校验 |
| `faiss-cpu` | >=1.7.4 | 向量索引与L2检索 |
| `numpy` | >=1.24 | 向量运算 |
| `openai` | >=1.0.0 | DashScope API 调用 |
| `pyyaml` | >=6.0 | 配置解析 |
| `python-json-logger` | >=2.0.7 | JSON格式日志 |
| `redis` | >=5.0.0 | 结构化缓存（可选） |
| `mysql-connector-python` | >=8.0.0 | 持久化存储（可选） |
| `opentelemetry-*` | >=1.20.0 | 可观测性追踪（可选） |

---

## 项目定位

- 前置：订单脏单拦截、规则校验
- 后置：差错池智能诊断（掉单、状态不一致、金额不匹配）
- 全程只读、不执行资金操作、可审计、可解释

## 架构分层

```
main.py                    入口：加载.env → 校验数据 → 初始化 → 诊断场景
│
├── agents/                专家Agent团队
│   ├── plan_agent.py      PlanAgent: 意图理解 + 步骤规划
│   ├── coordinator.py      Coordinator: 任务调度 + 决策汇总
│   ├── order_agent.py      OrderAgent: 订单查询
│   ├── payment_agent.py    PaymentAgent: 支付状态 + 错误码匹配
│   ├── risk_agent.py       RiskAgent: 风控评估 + 规则命中
│   ├── reconciliation_agent.py  ReconciliationAgent: 对账核查
│   ├── operation_agent.py  OperationAgent: 综合诊断 + 运营建议
│   └── rag_orchestrator.py Agent+RAG编排器: 工具决策 + 记忆路由
│
├── memory/                记忆体系（三级）
│   ├── embedding.py        EmbeddingProvider: DashScope/确定性哈希/SentenceTransformer
│   ├── chunking.py         TextSplitter: 段落→句子→Token限制→重叠窗口
│   ├── multimodal.py       MultimodalProcessor: 图片理解+OCR+多格式文档
│   ├── memory_hub.py       MemoryHub: 统一入口
│   └── storage/
│       ├── vector/vector_store.py    FAISS IndexFlatL2 向量存储
│       ├── hybrid_search.py          BM25+Vector+Rule混合检索+RRF融合
│       ├── sync_manager.py           双库一致性管理器
│       └── structured/               Redis/MySQL 结构化存储
│
├── tools/                 原子工具
│   ├── DeepSearch/
│   │   ├── vector_search.py    VectorSearchTool: Agent调用的向量检索工具
│   │   ├── deep_search.py      DeepSearchEngine: 多路召回+粗精排+交叉验证
│   │   ├── rag_pipeline.py     RAGPipeline: 噪声过滤+上下文压缩+Prompt构建
│   │   └── query_rewrite.py    QueryRewriteService: LLM查询改写+候选级联
│   ├── DataCarry/          数据读写工具
│   ├── BaseTool/           工具基类
│   └── tool_registry.py    工具注册表
│
├── MCP/                   多智能体协作协议（控制平面）
│   ├── mcp_gateway.py      MCPGateway: Coordinator↔Worker唯一通道
│   ├── acl/                权限矩阵
│   ├── context_manager/    上下文切片 + 会话管理
│   ├── memory_manager/     Memory访问ACL
│   ├── prompt_manager/     专家Prompt模板
│   ├── tool_guard/         工具白名单
│   └── validator/          出入参校验
│
├── prompts/               Prompt模板（独立文件管理）
│   ├── system.st           系统角色+回答原则+领域知识+格式规范+约束
│   ├── user.st             上下文注入+问题+回答要求
│   ├── rewrite.st          查询改写规则
│   ├── manager.py          PromptManager: 模板加载+缓存+热更新
│   └── security.py         PromptSanitizer: 注入检测+清洗
│
├── infrastructure/        基础设施
│   ├── data_generator.py   批量数据生成器（1000条）
│   ├── kb_loader.py        知识库加载器（分块+Embedding+双写+去重）
│   ├── async_pipeline.py   异步管道（Producer→Queue→Consumer模板方法）
│   ├── fake_data.py        内置测试数据
│   ├── mock_infra.py       Mock基础设施（DB/Redis/MQ）
│   ├── resilience.py       韧性系统（熔断/限流/心跳/并发控制）
│   ├── decision_engine.py  决策引擎+规则引擎
│   ├── approval.py         审批流
│   ├── state_persistence.py 状态持久化+断点管理
│   └── agent_pool.py       Agent池
│
└── core/                  核心模块
    ├── errors.py           错误码体系（E1xxx/E2xxx/E3xxx/SYS_xxx）
    ├── logger.py            JSON格式日志
    ├── tracing.py           OpenTelemetry追踪
    └── order_state_machine.py 订单状态机
```

---

## 启动流程

`python main.py` 执行步骤：

1. **加载 .env** — 读取项目根目录 `.env` 中的 `DASHSCOPE_API_KEY`
2. **初始化追踪** — OpenTelemetry
3. **初始化 MemoryHub** — FAISS向量库 + Redis/MySQL存储 + 混合检索引擎
4. **初始化Mock基础设施** — 内存DB/Redis/MQ/Metrics
5. **加载业务数据** — 自动检测 `data/*.json`，有则批量加载(1000条)，否则用小数据集
6. **初始化Embedding** — 千问DashScope API（有Key）/ 确定性哈希（无Key）
7. **加载向量知识库** — 200条知识文档 → Embedding → FAISS索引
8. **初始化韧性系统** — 熔断器/限流器/心跳/并发控制
9. **初始化决策引擎** — 规则引擎+审批流
10. **初始化Agent池** — 注册5个专家Agent + PlanAgent + Coordinator
11. **启动心跳** — 所有组件健康监控
12. **运行诊断场景** — 3个订单异常场景 + 1个缓存测试
13. **输出状态报告** — 指标/熔断器/限流器/Agent池/心跳/持久化

---

## 运行命令

```bash
python main.py          # 完整系统：3个诊断场景 + 状态报告
python test_rag.py      # RAG闭环：10步全链路验证
python infrastructure/data_generator.py  # 生成1000条测试数据
```
