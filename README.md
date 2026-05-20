# Order Guardian Agents

Multi-Agent + RAG payment risk intelligent diagnostic analysis system.

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py                  # auto-run 3 diagnostic scenarios
python main.py --interactive    # interactive diagnostic + RAG QA mode
python test_rag.py              # RAG 10-step pipeline verification
```

---

## Tech Stack

### Embedding & Vector Search

| Component | Technology | Details |
|-----------|-----------|---------|
| Primary | DashScope `text-embedding-v3` | 1024-dim, OpenAI-compatible API, batch limit 10 |
| Fallback | Deterministic Hash | Zero-dependency, n-gram + MD5 hash + TF-IDF weighting |
| Vector DB | FAISS (faiss-cpu 1.7.4+) | IndexFlatL2, exact L2 distance search, disk persistence |
| Hybrid Search | 3-route + RRF Fusion | Vector (semantic) + BM25 (keyword) + Rule (business filter) |
| Deep Search | Multi-stage ranking | Query decomposition -> multi-recall -> RRF fusion -> coarse rank -> fine rank -> cross-validation |

### LLM & Language Processing

| Component | Technology | Details |
|-----------|-----------|---------|
| Chat LLM | DashScope `qwen-plus` | Natural language answer generation |
| Embedding | DashScope `text-embedding-v3` | 1024-dim vectors |
| Vision | DashScope `qwen-vl-plus` | Image analysis / OCR |
| Chinese NLP | jieba | Word segmentation + keyword extraction + stopword filtering |
| Intent Recognition | Rule-based keyword matching | ERNIE/BERT upgrade interface reserved |
| Text Chunking | LangChain RecursiveCharacterTextSplitter | chunk_size=300, chunk_overlap=50 |

### Agent Architecture

| Component | Technology | Details |
|-----------|-----------|---------|
| Agent Protocol | Custom MCP (Multi-Agent Cooperation Protocol) | ACL matrix, context slicing, memory access control |
| Task Scheduling | Harness Orchestrator | DAG dependency execution, parallel/serial, priority scheduling |
| Lifecycle | AgentLifecycleManager | 8-state tracking (uninitialized -> idle -> running -> completed/failed) |
| Resilience | CircuitBreaker + RateLimiter + Heartbeat + ConcurrencyController | Failure threshold, sliding window, health checks |

### Memory & Storage

| Component | Technology | Details |
|-----------|-----------|---------|
| Short-term | ShortTermBuffer | Rolling window (32 entries), TTL expiration (300s), auto-compression |
| Long-term | LongTermTaskStore | Persistent task history, indexed by order_id, disk-backed |
| Experience | ExperienceRepository | Auto-learning error_code->solution mappings |
| Hot Store | In-memory with TTL | Structured business data (orders, payments, risks) |
| Cold Store | JSONL append-only | Task logs, audit trails, daily files, auto-archive |
| Rule Store | JSON config | Risk rule configurations, hot-reload support |
| Vector Store | FAISS | Disk persistence, restart without rebuild |

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pydantic | >=2.0 | Data models / validation |
| faiss-cpu | >=1.7.4 | Vector index + L2 search |
| numpy | >=1.24 | Vector operations |
| openai | >=1.0.0 | DashScope API client |
| pyyaml | >=6.0 | Config parsing |
| python-json-logger | >=2.0.7 | JSON structured logging |
| jieba | >=0.42 | Chinese word segmentation |
| langchain-text-splitters | >=0.3.0 | RecursiveCharacterTextSplitter |
| redis | >=5.0.0 | Structured cache (optional) |
| mysql-connector-python | >=8.0.0 | Persistent storage (optional) |
| opentelemetry-* | >=1.20.0 | Observability tracing (optional) |

---

## Architecture

```
main.py                       Entry: load .env -> check data -> init -> diagnostic scenarios
│
├── agents/                   Expert agent team
│   ├── plan_agent.py         PlanAgent: intent understanding + step planning
│   ├── coordinator.py        Coordinator: task scheduling + decision aggregation
│   ├── order_agent.py        OrderAgent: transaction query
│   ├── payment_agent.py      PaymentAgent: payment verification + error code matching
│   ├── risk_agent.py         RiskAgent: risk assessment + rule matching
│   ├── reconciliation_agent.py  ReconciliationAgent: financial reconciliation
│   ├── operation_agent.py    OperationAgent: comprehensive diagnosis + action plan
│   └── rag_orchestrator.py   Agent+RAG orchestrator: tool decision + memory routing
│
├── memory/                   Memory system
│   ├── embedding.py          EmbeddingProvider: DashScope / deterministic hash / sentence-transformers
│   ├── chunking.py           DocumentChunker: LangChain RecursiveCharacterTextSplitter
│   ├── memory_tiers.py       ShortTermBuffer + LongTermTaskStore + ExperienceRepository
│   ├── memory_hub.py         MemoryHub: unified memory entry point
│   ├── storage_router.py     HotStore + ColdStore + RuleStore + StorageRouter
│   ├── knowledge_catalog.py  Hierarchical domain catalog + KnowledgeRouter
│   ├── multimodal.py         MultimodalProcessor: image analysis + OCR + multi-format docs
│   └── storage/
│       ├── vector/vector_store.py    FAISS IndexFlatL2 with disk persistence
│       ├── hybrid_search.py          BM25 + Vector + Rule hybrid search + RRF fusion
│       ├── sync_manager.py           Dual-store consistency manager
│       └── structured/               Redis/MySQL structured storage
│
├── tools/                    Atomic tools
│   ├── DeepSearch/
│   │   ├── vector_search.py     VectorSearchTool: agent-callable vector search
│   │   ├── deep_search.py       DeepSearchEngine: multi-stage deep search
│   │   ├── rag_pipeline.py      RAGPipeline: full retrieval + LLM generation loop
│   │   └── query_rewrite.py     QueryRewriteService: LLM query rewrite + candidate cascade
│   ├── preprocessing.py     jieba tokenization + keyword extraction + stopword filtering
│   ├── intent_recognizer.py Rule-based intent recognition (domain classification)
│   ├── text_compressor.py   TF-IDF key sentence extraction + structured field preservation
│   ├── interactive.py       Interactive command-line mode (diagnosis / RAG QA / status)
│   ├── DataCarry/           Data read/write tools
│   ├── BaseTool/            Tool base class
│   └── tool_registry.py     Tool registry
│
├── MCP/                     Multi-Agent Cooperation Protocol (control plane)
│   ├── mcp_gateway.py       MCPGateway: Coordinator-Worker communication channel
│   ├── acl/                 Permission matrix
│   ├── context_manager/     Context slicing + session management
│   ├── memory_manager/      Memory access ACL
│   ├── prompt_manager/      Expert prompt templates
│   ├── tool_guard/          Tool whitelist
│   └── validator/           Input/output validation
│
├── prompts/                 Prompt management
│   ├── system.st            System role + answer principles + format spec + constraints
│   ├── user.st              Context injection + question + requirements
│   ├── rewrite.st           Query rewrite rules
│   ├── agent_prompts.py     Per-agent specialized prompts (role/constraints/output/behavior)
│   ├── manager.py           PromptManager: template loading + caching + hot-reload
│   └── security.py          PromptSanitizer: injection detection + sanitization
│
├── infrastructure/          Infrastructure
│   ├── harness.py           HarnessOrchestrator: lifecycle + priority + resources + fallback
│   ├── data_generator.py    Bulk test data generator (1000 records)
│   ├── kb_loader.py         Knowledge base loader (chunk + embed + dual-write + dedup)
│   ├── async_pipeline.py    Async pipeline (Producer->Queue->Consumer template method)
│   ├── fake_data.py         Built-in test data
│   ├── mock_infra.py        Mock infrastructure (DB/Redis/MQ/Metrics)
│   ├── resilience.py        Resilience (circuit breaker / rate limiter / heartbeat / concurrency)
│   ├── decision_engine.py   Decision engine + rule engine
│   ├── approval.py          Approval workflow
│   ├── state_persistence.py State persistence + checkpoint management
│   └── agent_pool.py        Agent pool
│
├── core/                    Core modules
│   ├── errors.py            Error code system (E1xxx/E2xxx/E3xxx/SYS_xxx)
│   ├── logger.py            JSON structured logging (console WARNING+ / file DEBUG+)
│   ├── tracing.py           OpenTelemetry tracing
│   └── order_state_machine.py Order state machine
│
└── config.py                All tunable parameters centralized (no magic numbers)
```

---

## Startup Flow

`python main.py` executes:

1. Load `.env` - read `DASHSCOPE_API_KEY` from project root
2. Init tracing - OpenTelemetry
3. Init MemoryHub - FAISS vector store + Redis/MySQL + hybrid search engine
4. Init mock infrastructure - in-memory DB/Redis/MQ/Metrics
5. Init embedding - DashScope API (with key) / deterministic hash (without)
6. Load business data - auto-detect `data/*.json` (1000 records) or fallback to built-in
7. Load knowledge base - 200+ docs -> chunk -> embed -> FAISS index (skip if persisted)
8. Init memory facade - short-term buffer + long-term task store + experience repository
9. Init storage router - hot/cold/rule/vector storage tiers
10. Init knowledge catalog - hierarchical domain catalog + router
11. Init resilience - circuit breakers / rate limiters / heartbeat / concurrency control
12. Init decision engine - rule engine + approval workflow
13. Init state persistence - checkpoint manager
14. Init agent pool - register 5 expert agents + PlanAgent + Coordinator
15. Init harness orchestrator - lifecycle management + priority scheduling + fallback strategies
16. Init tools + MCP gateway
17. Start heartbeat - all component health monitoring
18. Run diagnostic scenarios - 3 preset scenarios
19. Output status report - metrics / breakers / limiters / agent pool / heartbeat

---

## Run Commands

```bash
python main.py                                      # auto-run 3 diagnostic scenarios
python main.py --interactive                        # interactive diagnostic + RAG QA mode
python test_rag.py                                  # RAG 10-step pipeline verification
python infrastructure/data_generator.py              # generate 1000 test data records
```

---

## Interactive Mode Commands

```
ORD00001          run full 5-agent diagnostic pipeline for an order
run ORD00001      same as above
status            display system status: task counts, breakers, health
clear             clear screen
<any question>    RAG knowledge base query
exit              quit
```
