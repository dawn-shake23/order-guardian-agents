from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from core.logger import get_logger


class ToolDecision(str, Enum):
    NEED_RAG = "need_rag"
    SKIP_RAG = "skip_rag"
    NEED_STRUCTURED_ONLY = "need_structured_only"
    NEED_DEEP_SEARCH = "need_deep_search"


class MemoryLevel(str, Enum):
    SHORT_TERM = "short_term"
    MID_TERM = "mid_term"
    LONG_TERM = "long_term"


class ToolUsePlanner:
    """
    工具调用决策器
    解决：Agent什么时候该调用RAG？
    判断依据：
    1. 是否涉及历史知识 → 需要RAG
    2. 是否涉及专业领域 → 需要RAG
    3. 是否需要外部资料 → 需要RAG
    4. 纯数据查询 → 只需结构化查询
    5. 简单状态确认 → 不需要检索
    """

    DOMAIN_KEYWORDS = {
        "payment": ["支付", "退款", "回调", "渠道", "掉单", "付款", "结算"],
        "order": ["订单", "下单", "取消", "创建", "状态"],
        "risk": ["风险", "风控", "评分", "黑名单", "异常"],
        "reconciliation": ["对账", "账实", "差异", "核销"],
        "operation": ["运营", "建议", "处理", "工单"],
    }

    HISTORY_KEYWORDS = ["历史", "之前", "上次", "过去", "曾经", "以往", "案例", "先例"]
    EXTERNAL_KEYWORDS = ["手册", "规范", "流程", "规则", "政策", "标准", "文档"]

    def decide(self, query: str, agent_type: str, context: Optional[Dict] = None) -> ToolDecision:
        """
        决策是否需要调用RAG
        """
        query_lower = query.lower()

        domain_keywords = self.DOMAIN_KEYWORDS.get(agent_type, [])
        is_domain_query = any(kw in query for kw in domain_keywords)

        is_history_query = any(kw in query for kw in self.HISTORY_KEYWORDS)
        is_external_query = any(kw in query for kw in self.EXTERNAL_KEYWORDS)

        if is_history_query or is_external_query:
            return ToolDecision.NEED_DEEP_SEARCH

        if is_domain_query:
            return ToolDecision.NEED_RAG

        simple_queries = ["查询状态", "获取信息", "读取数据", "确认"]
        if any(q in query for q in simple_queries):
            return ToolDecision.NEED_STRUCTURED_ONLY

        trivial_queries = ["是", "否", "确认", "继续"]
        if query.strip() in trivial_queries:
            return ToolDecision.SKIP_RAG

        return ToolDecision.NEED_RAG


class MemoryRouter:
    """
    多级记忆路由器
    解决：短期、中期、长期记忆怎么配合检索？
    策略：
    - 短期：当前对话上下文（直接使用）
    - 中期：用户历史偏好（session级缓存）
    - 长期：知识库（需要检索）
    """

    def __init__(self, memory_hub):
        self.memory_hub = memory_hub
        self.logger = get_logger("memory_router")

    def route(self, query: str, session_id: str, agent_type: str) -> Dict[MemoryLevel, Any]:
        """
        多级记忆路由
        """
        result = {}

        # 短期记忆：当前session上下文
        result[MemoryLevel.SHORT_TERM] = self._get_short_term(session_id)

        # 中期记忆：session级偏好/历史
        result[MemoryLevel.MID_TERM] = self._get_mid_term(session_id, agent_type)

        # 长期记忆：是否需要检索知识库
        planner = ToolUsePlanner()
        decision = planner.decide(query, agent_type)
        result[MemoryLevel.LONG_TERM] = {
            "need_retrieval": decision in (ToolDecision.NEED_RAG, ToolDecision.NEED_DEEP_SEARCH),
            "decision": decision.value,
        }

        self.logger.info("记忆路由完成", extra={
            "session_id": session_id,
            "agent_type": agent_type,
            "decision": decision.value
        })

        return result

    def _get_short_term(self, session_id: str) -> Dict[str, Any]:
        key = f"short_term:{session_id}"
        data = self.memory_hub.struct_redis.get(key)
        return data if data else {"context": [], "current_step": None}

    def _get_mid_term(self, session_id: str, agent_type: str) -> Dict[str, Any]:
        key = f"mid_term:{session_id}:{agent_type}"
        data = self.memory_hub.struct_redis.get(key)
        return data if data else {"preferences": [], "history": []}


class RetrievalResultProcessor:
    """
    检索结果处理器
    解决：Agent拿到资料后怎么决策？
    - 直接回答？
    - 继续调用其他工具？
    - 反问用户？
    """

    def __init__(self):
        self.logger = get_logger("retrieval_processor")

    def process(self, retrieval_results: List[Dict], agent_type: str, query: str) -> Dict[str, Any]:
        """
        处理检索结果，决定Agent下一步动作
        """
        if not retrieval_results:
            return {
                "action": "ask_user",
                "reason": "未检索到相关资料，需要用户提供更多信息",
                "data": None
            }

        high_relevance = [r for r in retrieval_results if r.get("score", 0) > 0.7 or r.get("validated", False)]
        medium_relevance = [r for r in retrieval_results if 0.3 < r.get("score", 0) <= 0.7]
        low_relevance = [r for r in retrieval_results if r.get("score", 0) <= 0.3]

        if high_relevance:
            return {
                "action": "direct_answer",
                "reason": "检索到高相关性资料，可以直接回答",
                "data": high_relevance,
                "confidence": "high"
            }

        if medium_relevance:
            return {
                "action": "continue_tools",
                "reason": "检索到中等相关性资料，建议继续调用其他工具补充信息",
                "data": medium_relevance,
                "confidence": "medium",
                "suggested_tools": self._suggest_next_tools(agent_type)
            }

        return {
            "action": "ask_user",
            "reason": "检索结果相关性较低，需要用户确认或补充信息",
            "data": low_relevance,
            "confidence": "low"
        }

    def _suggest_next_tools(self, agent_type: str) -> List[str]:
        tool_map = {
            "order": ["struct_search", "memory_read_write"],
            "payment": ["struct_search", "vector_search"],
            "risk": ["agent_acl_check", "vector_search"],
            "reconciliation": ["struct_search", "memory_read_write"],
            "operation": ["sandbox_read_write", "memory_read_write"],
        }
        return tool_map.get(agent_type, [])


class AgentRAGOrchestrator:
    """
    Agent + RAG 编排器
    整合：工具调用决策 + 多级记忆路由 + 检索结果驱动决策
    这是Agent和RAG深度融合的核心
    """

    def __init__(self, memory_hub, deep_search_engine=None, rag_pipeline=None):
        self.memory_hub = memory_hub
        self.tool_planner = ToolUsePlanner()
        self.memory_router = MemoryRouter(memory_hub)
        self.result_processor = RetrievalResultProcessor()
        self.deep_search = deep_search_engine
        self.rag_pipeline = rag_pipeline
        self.logger = get_logger("agent_rag_orchestrator")

    def orchestrate(self, agent_type: str, query: str, session_id: str,
                    order_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        完整的Agent+RAG编排流程
        """
        self.logger.info("Agent+RAG编排开始", extra={
            "agent_type": agent_type,
            "query": query,
            "session_id": session_id
        })

        # Step 1: 工具调用决策
        decision = self.tool_planner.decide(query, agent_type)

        # Step 2: 多级记忆路由
        memory_routes = self.memory_router.route(query, session_id, agent_type)

        # Step 3: 根据决策执行不同路径
        if decision == ToolDecision.SKIP_RAG:
            return self._skip_rag_path(memory_routes, query)

        elif decision == ToolDecision.NEED_STRUCTURED_ONLY:
            return self._structured_only_path(memory_routes, query, agent_type)

        elif decision == ToolDecision.NEED_RAG:
            return self._rag_path(memory_routes, query, agent_type, session_id, order_id, context)

        elif decision == ToolDecision.NEED_DEEP_SEARCH:
            return self._deep_search_path(memory_routes, query, agent_type, session_id, order_id, context)

        return {"action": "unknown", "decision": decision.value}

    def _skip_rag_path(self, memory_routes: Dict, query: str) -> Dict[str, Any]:
        short_term = memory_routes.get(MemoryLevel.SHORT_TERM, {})
        return {
            "action": "direct_answer",
            "reason": "简单查询，无需检索",
            "context": short_term,
            "rag_prompt": None
        }

    def _structured_only_path(self, memory_routes: Dict, query: str, agent_type: str) -> Dict[str, Any]:
        return {
            "action": "structured_query",
            "reason": "纯数据查询，只需结构化库",
            "context": memory_routes.get(MemoryLevel.SHORT_TERM, {}),
            "rag_prompt": None
        }

    def _rag_path(self, memory_routes: Dict, query: str, agent_type: str,
                  session_id: str, order_id: str, context: Optional[Dict]) -> Dict[str, Any]:
        from tools.DeepSearch.vector_search import VectorSearchTool
        tool = VectorSearchTool(self.memory_hub)
        result = tool.execute(
            agent_type=agent_type,
            params={"query": query, "biz_domain": agent_type, "top_k": 5},
            sandbox=None
        )

        search_data = result.data if result.success else {}
        results = search_data.get("search_result", []) if search_data else []

        processed = self.result_processor.process(results, agent_type, query)

        rag_prompt = None
        if self.rag_pipeline and results:
            rag_prompt = self.rag_pipeline.process(results, query, agent_type,
                                                    extra_context={"session_id": session_id, "order_id": order_id})

        return {
            "action": processed["action"],
            "reason": processed["reason"],
            "confidence": processed.get("confidence", "unknown"),
            "data": processed.get("data"),
            "suggested_tools": processed.get("suggested_tools", []),
            "rag_prompt": rag_prompt
        }

    def _deep_search_path(self, memory_routes: Dict, query: str, agent_type: str,
                          session_id: str, order_id: str, context: Optional[Dict]) -> Dict[str, Any]:
        if self.deep_search is None:
            return self._rag_path(memory_routes, query, agent_type, session_id, order_id, context)

        from tools.DeepSearch.deep_search import DeepSearchQuery
        ds_query = DeepSearchQuery(
            raw_query=query,
            biz_domain=agent_type,
            require_cross_validation=True,
            top_k=5
        )

        ds_results = self.deep_search.search(ds_query)
        results = [r.model_dump() for r in ds_results]

        processed = self.result_processor.process(results, agent_type, query)

        rag_prompt = None
        if self.rag_pipeline and results:
            rag_prompt = self.rag_pipeline.process(results, query, agent_type,
                                                    extra_context={"session_id": session_id, "order_id": order_id})

        return {
            "action": processed["action"],
            "reason": processed["reason"],
            "confidence": processed.get("confidence", "unknown"),
            "data": processed.get("data"),
            "suggested_tools": processed.get("suggested_tools", []),
            "rag_prompt": rag_prompt,
            "deep_search": True
        }
