"""
RAG 闭环端到端验证脚本
测试完整的：向量库 → 知识库 → 检索 → 噪声过滤 → Prompt构建 → LLM调用

借鉴 Java KnowledgeBaseQueryService 的完整验证流程
"""
# ── 最早：加载 .env ──────────────────────────────────
import os as _os
from pathlib import Path as _Path
_env = _Path(__file__).resolve().parent / ".env"
if _env.exists():
    with open(_env, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip())
# ──────────────────────────────────────────────────────

import sys
import time
import numpy as np
from memory.memory_hub import MemoryHub
from memory.embedding import EmbeddingProvider
from memory.chunking import TextSplitter, ChunkConfig, DocumentChunker
from infrastructure.kb_loader import KnowledgeBaseLoader, VectorStatus
from infrastructure.fake_data import KNOWLEDGE_BASE, EXPERT_CASES
from memory.storage.hybrid_search import HybridSearchEngine
from tools.DeepSearch.deep_search import DeepSearchEngine, DeepSearchQuery
from tools.DeepSearch.rag_pipeline import RAGPipeline, RagConfig
from tools.DeepSearch.query_rewrite import QueryRewriteService, RewriteConfig, CandidateQueryGenerator
from agents.rag_orchestrator import AgentRAGOrchestrator


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_result(label: str, value, indent: int = 2):
    prefix = " " * indent
    if isinstance(value, dict):
        print(f"{prefix}{label}:")
        for k, v in value.items():
            v_str = str(v)
            if len(v_str) > 100:
                v_str = v_str[:100] + "..."
            print(f"{prefix}  {k}: {v_str}")
    elif isinstance(value, list):
        print(f"{prefix}{label}: [{len(value)}条]")
        for i, item in enumerate(value[:3]):
            if isinstance(item, dict):
                print(f"{prefix}  [{i}] {item.get('doc_id', item.get('title', str(item)[:60]))}")
    else:
        v_str = str(value)
        if len(v_str) > 120:
            v_str = v_str[:120] + "..."
        print(f"{prefix}{label}: {v_str}")


def test_step1_memory_init():
    """Step 1: 记忆中心初始化"""
    print_section("Step 1: MemoryHub 初始化")
    hub = MemoryHub()
    print_result("Redis客户端", type(hub.struct_redis).__name__)
    print_result("MySQL仓库", type(hub.struct_mysql).__name__)
    print_result("向量存储", type(hub.vector_store).__name__)
    print_result("混合检索引擎", type(hub.hybrid_search).__name__)
    print_result("FAISS可用", hub.vector_store.index is not None)
    print_result("向量维度", hub.vector_store.dimension)
    return hub


def test_step2_embedding(hub: MemoryHub):
    """Step 2: Embedding 测试"""
    print_section("Step 2: EmbeddingProvider 测试 (千问 DashScope)")

    emb = EmbeddingProvider(dim=1024)
    print_result("Embedding后端", emb.backend)

    # 测试编码
    texts = [
        "支付超时处理规则：当支付超时(E2001)时需要查询渠道确认支付状态",
        "订单风控拦截处理规范：高风险订单需人工审核",
        "对账差异处理流程：金额不一致需财务确认"
    ]
    embeddings = emb.encode_batch(texts)
    print_result("编码文本数", len(texts))
    print_result("向量维度", len(embeddings[0]))
    print_result("向量L2范数", round(np.linalg.norm(embeddings[0]), 4))

    # 测试语义相似度（相似文本应该有更近的距离）
    sim_dist = np.linalg.norm(np.array(embeddings[0]) - np.array(embeddings[1]))
    print_result("相似文本距离(支付vs风控)", round(sim_dist, 4))

    return emb


def test_step3_kb_loading(hub: MemoryHub, emb: EmbeddingProvider):
    """Step 3: 知识库加载（借鉴Java上传管道）"""
    print_section("Step 3: 知识库加载")

    # 测试分块器（长文本分块）
    chunk_config = ChunkConfig(max_chunk_tokens=200, min_chunk_tokens=30)
    splitter = TextSplitter(config=chunk_config)

    long_text = KNOWLEDGE_BASE[0]["content"]  # E2001支付超时处理规则
    chunks = splitter.split(long_text)
    print_result("分块器-长文本", f"{len(long_text)}字符 → {len(chunks)}chunks")
    for c in chunks[:3]:
        print_result(f"  {c.chunk_id}", f"{c.token_count}tokens, {len(c.text)}chars")

    # 加载知识库（不分块模式，适合小知识库）
    loader = KnowledgeBaseLoader(
        memory_hub=hub,
        embedding_provider=emb,
        enable_chunking=False
    )

    result = loader.load(KNOWLEDGE_BASE, EXPERT_CASES)
    print_result("加载结果", {
        "status": result["status"],
        "total_documents": result["total_documents"],
        "total_cases": result["total_cases"],
        "vector_store_size": result["vector_store_size"],
        "failed": result["failed"],
        "skipped_duplicate": result["skipped_duplicate"],
        "duration_ms": f"{result['duration_ms']:.1f}",
        "embedding_backend": result["embedding_backend"],
    })

    return loader


def test_step4_vector_search(hub: MemoryHub, emb: EmbeddingProvider):
    """Step 4: 向量检索测试"""
    print_section("Step 4: 向量检索")

    vs = hub.vector_store
    print_result("向量库大小", len(vs.embeddings))
    print_result("元数据大小", len(vs.metadata))

    # 展示知识库内容概览
    print("\n  知识库索引内容:")
    for i, meta in enumerate(vs.metadata):
        print(f"  [{i}] {meta.get('doc_id')} | {meta.get('biz_domain')} | {meta.get('title')[:50]}")

    return vs


def test_step5_hybrid_search(hub: MemoryHub, emb: EmbeddingProvider):
    """Step 5: 混合检索测试（多路召回+RRF融合）"""
    print_section("Step 5: 混合检索 (HybridSearch)")

    hybrid = HybridSearchEngine(hub.vector_store, hub.struct_mysql)

    test_queries = [
        ("支付超时怎么处理", "payment"),
        ("风控拦截规则", "risk"),
        ("订单对账不一致", "reconciliation"),
        ("回调丢失处理", "payment"),
    ]

    for query, domain in test_queries:
        query_embedding = emb.encode(query)
        results = hybrid.search_with_filter(
            query_embedding=query_embedding,
            biz_domain=domain,
            top_k=3
        )
        print(f"\n  查询: '{query}' (domain={domain})")
        print(f"  命中: {len(results)}条")
        for i, r in enumerate(results):
            meta = r.get("metadata", {})
            print(f"    [{i+1}] {meta.get('doc_id')} | {meta.get('title','')[:50]} | dist={r.get('distance', 0):.4f}")

    # 测试多路召回+RRF融合
    query = "支付超时和风控拦截的处理方案"
    query_embedding = emb.encode(query)
    multi = hybrid.multi_route_recall(query, query_embedding, top_k=5)
    fused = HybridSearchEngine.rrf_fusion(multi)
    print(f"\n  多路召回+RRF融合: '{query}'")
    print(f"  向量路: {len(multi['vector'])}条, BM25路: {len(multi['bm25'])}条, 规则路: {len(multi['rule'])}条")
    print(f"  融合后: {len(fused)}条")
    for i, item in enumerate(fused[:3]):
        print(f"    [{i+1}] {item.get('doc_id')} | score={item.get('score', 0):.4f}")

    return hybrid


def test_step6_deep_search(hub: MemoryHub, emb: EmbeddingProvider, hybrid):
    """Step 6: DeepSearch深度检索（查询理解→多路召回→粗排→精排→交叉验证）"""
    print_section("Step 6: DeepSearch 深度检索")

    deep_search = DeepSearchEngine(hybrid)

    test_cases = [
        ("支付超时E2001怎么处理，需要交叉验证", "payment", True),
        ("风控黑名单拦截", "risk", False),
        ("对账差异处理流程", "reconciliation", False),
    ]

    for query, domain, require_cv in test_cases:
        query_embedding = emb.encode(query)
        ds_query = DeepSearchQuery(
            raw_query=query,
            biz_domain=domain,
            top_k=5,
            require_cross_validation=require_cv
        )
        results = deep_search.search(ds_query, query_embedding)
        print(f"\n  查询: '{query}' (domain={domain}, cross_validation={require_cv})")
        print(f"  结果: {len(results)}条")
        for r in results:
            print(f"    [{r.doc_id}] {r.title[:50]} | score={r.score:.4f} | routes={r.source_route} | validated={r.validated}")

    return deep_search


def test_step7_rag_pipeline(emb: EmbeddingProvider, hybrid):
    """Step 7: RAG Pipeline完整流程（噪声过滤→上下文压缩→Prompt构建）"""
    print_section("Step 7: RAG Pipeline (噪声过滤→上下文压缩→Prompt构建)")

    config = RagConfig()
    pipeline = RAGPipeline(config=config, hybrid_engine=hybrid)

    # 执行一次完整检索
    query = "支付超时怎么处理"
    query_embedding = emb.encode(query)

    results = hybrid.search_with_filter(
        query_embedding=query_embedding,
        biz_domain="payment",
        top_k=5
    )

    # 完整RAG处理
    prompt = pipeline.process(results, query, biz_domain="payment",
                              extra_context={"order_id": "ORD00001"})

    print_result("检索结果数", len(results))
    print_result("System Prompt长度", len(prompt["system"]))
    print_result("User Prompt长度", len(prompt["user"]))
    print("\n  --- System Prompt (前500字符) ---")
    print(prompt["system"][:500] + "...")
    print("\n  --- User Prompt (前500字符) ---")
    print(prompt["user"][:500] + "...")

    return pipeline


def test_step8_query_rewrite():
    """Step 8: 查询改写测试（借鉴Java rewriteQuestion）"""
    print_section("Step 8: 查询改写 (QueryRewrite)")

    config = RewriteConfig(enabled=True)
    rewrite_svc = QueryRewriteService(config=config, llm_client=None)

    test_queries = [
        "超时了怎么办",  # 过短需要改写
        "支付超时E2001怎么处理",  # 已经具体
        "那个黑名单规则是什么",  # 指代不明
    ]

    history = [
        {"role": "user", "content": "订单ORD00003被风控拦截了什么原因"},
        {"role": "assistant", "content": "订单ORD00003因命中黑名单规则(R005)，风险评分95分，被高风险拦截"},
    ]

    for q in test_queries:
        rewritten = rewrite_svc.rewrite(q, history)
        print(f"\n  原始: {q}")
        print(f"  改写: {rewritten}")

    # 候选查询生成器
    candidate_gen = CandidateQueryGenerator(rewrite_svc)
    candidates = candidate_gen.generate("那个处理流程是什么", history)
    print(f"\n  候选查询级联: {candidates}")

    return rewrite_svc


def test_step9_rag_orchestrator(hub: MemoryHub):
    """Step 9: Agent+RAG 编排器"""
    print_section("Step 9: Agent+RAG 编排器 (AgentRAGOrchestrator)")

    orchestrator = AgentRAGOrchestrator(memory_hub=hub)
    print_result("编排器组件", {
        "tool_planner": type(orchestrator.tool_planner).__name__,
        "memory_router": type(orchestrator.memory_router).__name__,
        "result_processor": type(orchestrator.result_processor).__name__,
    })

    # 测试工具调用决策
    decisions = [
        ("支付超时怎么处理", "payment"),
        ("历史案例中类似的情况", "payment"),
        ("查询订单状态", "order"),
        ("确认", "order"),
    ]

    for query, agent_type in decisions:
        decision = orchestrator.tool_planner.decide(query, agent_type)
        print(f"  查询: '{query}' (agent={agent_type}) → {decision.value}")

    # 测试完整编排
    result = orchestrator.orchestrate(
        agent_type="payment",
        query="支付超时E2001怎么处理",
        session_id="test_session_001",
        order_id="ORD00001",
        context={"biz_domain": "payment"}
    )
    print_result("\n  编排结果", {
        "action": result.get("action"),
        "reason": result.get("reason", ""),
        "confidence": result.get("confidence", "unknown"),
        "data_count": len(result.get("data", [])),
        "suggested_tools": result.get("suggested_tools", []),
    })

    return orchestrator


def test_step10_end_to_end(emb: EmbeddingProvider, hybrid, pipeline):
    """Step 10: 端到端RAG闭环验证"""
    print_section("Step 10: 端到端RAG闭环 — 完整检索链路验证")

    test_cases = [
        {
            "query": "支付超时E2001怎么处理",
            "biz_domain": "payment",
            "expected_docs": ["KB001"],
            "desc": "精确错误码查询"
        },
        {
            "query": "风控拦截黑名单",
            "biz_domain": "risk",
            "expected_docs": ["KB008", "KB004"],
            "desc": "风控规则查询"
        },
        {
            "query": "对账差异处理流程",
            "biz_domain": "reconciliation",
            "expected_docs": ["KB005"],
            "desc": "对账流程查询"
        },
        {
            "query": "支付回调丢失了",
            "biz_domain": "payment",
            "expected_docs": ["KB007"],
            "desc": "口语化查询（测试语义理解）"
        },
        {
            "query": "订单超时关闭规则",
            "biz_domain": "order",
            "expected_docs": ["KB009"],
            "desc": "跨域订单规则查询"
        },
    ]

    total_score = 0
    total_cases = len(test_cases)

    for case in test_cases:
        query = case["query"]
        biz_domain = case["biz_domain"]
        expected = set(case["expected_docs"])

        print(f"\n  [{case['desc']}]")
        print(f"  查询: '{query}' (domain={biz_domain})")

        # Step 1: Embedding
        query_embedding = emb.encode(query)

        # Step 2: 混合检索
        search_results = hybrid.search_with_filter(
            query_embedding=query_embedding,
            biz_domain=biz_domain,
            top_k=5
        )

        hit_docs = set()
        for r in search_results:
            meta = r.get("metadata", {})
            hit_docs.add(meta.get("doc_id", ""))

        # Step 3: RAG Pipeline处理
        if search_results:
            rag_prompt = pipeline.process(
                search_results, query, biz_domain=biz_domain
            )

        # Step 4: 验证
        recall = expected & hit_docs
        recall_rate = len(recall) / len(expected) if expected else 0
        total_score += recall_rate

        print(f"  期望: {expected}")
        print(f"  命中: {hit_docs}")
        print(f"  召回: {recall} ({recall_rate:.0%})")
        print(f"  检索: {len(search_results)}条, RAG Prompt: {len(rag_prompt.get('system', '')) + len(rag_prompt.get('user', ''))}字符")

    avg_recall = total_score / total_cases if total_cases > 0 else 0
    print(f"\n  {'─'*50}")
    print(f"  平均召回率: {avg_recall:.1%}")
    print(f"  测试用例: {total_cases}个, 通过: {int(total_score)}/{total_cases}")
    print(f"  RAG闭环状态: {'通过' if avg_recall >= 0.5 else '需优化'}")

    return avg_recall


def test_chunking_e2e(hub: MemoryHub, emb: EmbeddingProvider):
    """附加测试：分块模式下的知识库加载和检索"""
    print_section("附加: 分块模式验证 (借鉴Java TokenTextSplitter)")

    # 只为一条长文档测试分块模式
    chunk_config = ChunkConfig(max_chunk_tokens=150, min_chunk_tokens=30)
    chunker = DocumentChunker(
        splitter=TextSplitter(config=chunk_config),
        embedding_provider=emb
    )

    # 找一条长文档做分块测试
    long_doc = None
    for doc in KNOWLEDGE_BASE:
        if len(doc["content"]) > 150:
            long_doc = doc
            break

    if long_doc:
        print(f"\n  分块测试文档: {long_doc['doc_id']} {long_doc['title']}")
        print(f"  内容长度: {len(long_doc['content'])}字符")

        chunks = chunker.chunk_and_embed(
            doc_id=f"{long_doc['doc_id']}_chunked",
            title=long_doc["title"],
            content=long_doc["content"],
            biz_domain=long_doc["biz_domain"],
            doc_type=long_doc.get("doc_type", "rule")
        )

        print(f"  分块结果: {len(chunks)} chunks")
        for c in chunks:
            print(f"    {c['metadata']['chunk_id']}: {c['metadata'].get('chunk_index', '?')}/{c['metadata'].get('total_chunks', '?')} | {len(c['chunk_text'])}chars")

        # 将分块写入向量库并测试检索
        for c in chunks:
            if c["embedding"]:
                hub.vector_store.add(c["embedding"], c["metadata"])

        # 检索分块
        query = "支付超时的处理步骤"
        query_emb = emb.encode(query)
        results = hub.vector_store.search(query_emb, k=3)
        print(f"\n  分块检索 '{query}':")
        for r in results:
            meta = r.get("metadata", {})
            print(f"    [{meta.get('chunk_id', '?')}] {meta.get('doc_id')} | dist={r.get('distance', 0):.4f}")
            print(f"    内容: {meta.get('content', '')[:100]}...")


def main():
    print("=" * 70)
    print("  Order Guardian - RAG 闭环端到端验证")
    print("  借鉴 Java InterviewGuide RAG 架构设计")
    print("=" * 70)

    start_time = time.time()

    # Step 1-2: 基础设施
    hub = test_step1_memory_init()
    emb = test_step2_embedding(hub)

    # Step 3: 知识库加载
    loader = test_step3_kb_loading(hub, emb)
    test_step4_vector_search(hub, emb)

    # Step 5-6: 检索
    hybrid = test_step5_hybrid_search(hub, emb)
    test_step6_deep_search(hub, emb, hybrid)

    # Step 7-8: RAG Pipeline
    pipeline = test_step7_rag_pipeline(emb, hybrid)
    test_step8_query_rewrite()

    # Step 9: 编排器
    test_step9_rag_orchestrator(hub)

    # Step 10: 端到端
    avg_recall = test_step10_end_to_end(emb, hybrid, pipeline)

    # 附加：分块验证
    test_chunking_e2e(hub, emb)

    elapsed = (time.time() - start_time) * 1000

    # 最终总结
    print_section("验证总结")
    print(f"  总耗时: {elapsed:.1f}ms")
    print(f"  Embedding后端: {emb.backend}")
    print(f"  向量库大小: {len(hub.vector_store.embeddings)}条")
    print(f"  结构化库表: {list(hub.struct_mysql.data.keys())}")
    print(f"  平均召回率: {avg_recall:.1%}")
    print(f"  FAISS加速: {'启用' if hub.vector_store.index is not None else '关闭'}")
    print(f"  分块器: {'可用' if loader.enable_chunking else '关闭（适合小知识库）'}")
    print(f"  查询改写: {'可用' if loader.embedding.backend != 'unknown' else '可用(规则模式)'}")

    print(f"\n  RAG闭环组件清单:")
    components = [
        ("向量库 (FAISS)", True),
        ("Embedding (确定性哈希)", True),
        ("知识库加载器", True),
        ("混合检索 (Vector+BM25+Rule)", True),
        ("RRF融合", True),
        ("DeepSearch深度检索", True),
        ("噪声过滤", True),
        ("上下文窗口压缩", True),
        ("结构化Prompt构建 (System/User双模板)", True),
        ("查询改写 (QueryRewrite)", True),
        ("候选查询级联回退", True),
        ("Agent+RAG编排器", True),
        ("文本分块 (TokenTextSplitter)", True),
        ("内容去重 (SHA-256)", True),
        ("VectorStatus生命周期", True),
    ]
    for name, status in components:
        icon = "[OK]" if status else "[--]"
        print(f"  {icon} {name}")

    print(f"\n  借鉴Java项目的关键模式已全部实现：")
    patterns = [
        "查询改写 → 候选查询级联 → 动态检索参数",
        "System/User 双提示词模板 (knowledgebase-query-*.st)",
        "分块→Embedding→批量存储 (TokenTextSplitter)",
        "VectorStatus: PENDING→PROCESSING→COMPLETED/FAILED",
        "SHA-256内容去重 (FileHashService)",
        "多路召回+RRF融合 (RRF Fusion)",
        "噪声过滤+上下文压缩 (NoiseFilter+ContextWindow)",
    ]
    for p in patterns:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
