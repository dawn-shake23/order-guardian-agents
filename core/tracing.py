"""
LangSmith 可观测性模块 — 全链路追踪

初始化 → init_tracing()
装饰器 → @traceable
LLM 调用 → trace_llm_call() 上下文管理器
Agent 运行 → trace_agent_run() 上下文管理器

所有 Span 自动上报到 LangSmith，附带 metadata / tags / input / output。
"""

import os
import functools
from typing import Any, Callable, Dict, Optional
from contextlib import contextmanager

from dotenv import load_dotenv

# 加载 .env，已有环境变量不覆盖
load_dotenv(override=False)

from langsmith import traceable as _langsmith_traceable
from langsmith.run_helpers import trace as _langsmith_trace
from langsmith import Client as LangSmithClient

from core.logger import get_logger

logger = get_logger("tracing")

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

_tracing_initialized: bool = False
_langsmith_client: Optional[LangSmithClient] = None


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("true", "1", "yes", "on")


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def init_tracing() -> None:
    """初始化 LangSmith 追踪系统，同时保留 OpenTelemetry 作为补充导出器。"""
    global _tracing_initialized, _langsmith_client

    if _tracing_initialized:
        return

    tracing_enabled = _env_bool("LANGSMITH_TRACING", True)
    api_key = _env_str("LANGSMITH_API_KEY")
    project = _env_str("LANGSMITH_PROJECT", "order-guardian")
    endpoint = _env_str("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    # 写入环境变量让 langsmith SDK 自动读取
    os.environ.setdefault("LANGSMITH_TRACING", str(tracing_enabled).lower())
    os.environ.setdefault("LANGSMITH_PROJECT", project)
    os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)
    if api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)

    if not tracing_enabled:
        logger.info("LangSmith 追踪已关闭（LANGSMITH_TRACING=false）")
        _tracing_initialized = True
        return

    if not api_key or api_key == "your-langsmith-api-key-here":
        logger.warning(
            "LANGSMITH_API_KEY 未配置，追踪数据不会上报到 LangSmith。"
            "请在 .env 中填入真实 API Key。"
        )
        _tracing_initialized = True
        return

    try:
        _langsmith_client = LangSmithClient(
            api_key=api_key,
            api_url=endpoint,
        )
        logger.info(
            "LangSmith 追踪已初始化",
            extra={"project": project, "endpoint": endpoint},
        )
    except Exception as e:
        logger.error("LangSmith 客户端初始化失败", extra={"error": str(e)})

    # 初始化 OpenTelemetry 作为补充导出器
    _init_otel()

    _tracing_initialized = True


def _init_otel() -> None:
    """初始化 OpenTelemetry（保留作为补充导出器）。"""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        service_name = _env_str("SERVICE_NAME", "order-guardian")
        otlp_endpoint = _env_str("OTLP_ENDPOINT", "http://localhost:4318/v1/traces")

        resource = Resource.create({"service.name": service_name})
        tracer_provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(tracer_provider)

        logger.info("OpenTelemetry 补充导出器已初始化", extra={"endpoint": otlp_endpoint})
    except Exception as e:
        logger.warning("OpenTelemetry 初始化失败（不影响 LangSmith）", extra={"error": str(e)})


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def get_client() -> Optional[LangSmithClient]:
    """获取 LangSmith 客户端实例。"""
    return _langsmith_client


def get_tracer(name: str = "order-guardian"):
    """获取 OpenTelemetry tracer（兼容旧接口）。"""
    from opentelemetry import trace
    return trace.get_tracer(name)


# ---------------------------------------------------------------------------
# @traceable 装饰器 — 自动为函数创建 LangSmith Span
# ---------------------------------------------------------------------------

def traceable(
    name: Optional[str] = None,
    run_type: str = "chain",
    tags: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
    project_name: Optional[str] = None,
):
    """
    LangSmith 追踪装饰器。

    使用方式：
        @traceable(name="order_query", run_type="chain", tags=["order", "query"])
        def my_func(...): ...

    参数：
        name: Span 名称，默认为函数名
        run_type: 运行类型 — "llm" | "chain" | "tool" | "retriever" | "agent"
        tags: 标签列表，方便在 LangSmith 中过滤
        metadata: 自定义元数据
        project_name: 覆盖项目名
    """
    kwargs: Dict[str, Any] = {"run_type": run_type}
    if name is not None:
        kwargs["name"] = name
    if tags is not None:
        kwargs["tags"] = tags
    if metadata is not None:
        kwargs["metadata"] = metadata
    if project_name is not None:
        kwargs["project_name"] = project_name

    return _langsmith_traceable(**kwargs)


# ---------------------------------------------------------------------------
# trace_llm_call — LLM 调用专用上下文管理器
# ---------------------------------------------------------------------------

@contextmanager
def trace_llm_call(
    model_name: str,
    prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
):
    """
    为 LLM 调用创建 LangSmith Span（自动嵌套于当前 trace context）。

    使用方式：
        with trace_llm_call("qwen14b", prompt) as span:
            result = llm.generate(prompt)
            span.end(outputs={"result": result})
    """
    with _langsmith_trace(
        name=f"llm:{model_name}",
        run_type="llm",
        inputs={"prompt": prompt},
        metadata={
            "model": model_name,
            **(metadata or {}),
        },
        tags=tags or [],
    ) as run:
        yield run


# ---------------------------------------------------------------------------
# trace_agent_run — Agent 运行专用上下文管理器
# ---------------------------------------------------------------------------

@contextmanager
def trace_agent_run(
    agent_type: str,
    session_id: str,
    step_id: Optional[int] = None,
    inputs: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
):
    """
    为 Agent 运行创建 LangSmith Span。

    使用方式：
        with trace_agent_run("order", session_id, step_id=1, inputs=ctx) as span:
            result = agent.run(ctx)
            span.end(outputs=result)
    """
    span_name = f"agent:{agent_type}"
    if step_id is not None:
        span_name += f":step_{step_id}"

    with _langsmith_trace(
        name=span_name,
        run_type="chain",
        inputs=inputs or {},
        metadata={
            "agent_type": agent_type,
            "session_id": session_id,
            "step_id": step_id,
        },
        tags=tags or [agent_type, "agent"],
    ) as run:
        yield run


# ---------------------------------------------------------------------------
# trace_coordinator — Coordinator 调度专用 Span
# ---------------------------------------------------------------------------

@contextmanager
def trace_coordinator(
    session_id: str,
    order_id: str,
    plan_steps: int = 0,
    tags: Optional[list] = None,
):
    """
    为 Coordinator 整体调度创建 LangSmith Span（作为 trace root）。

    使用方式：
        with trace_coordinator(session_id, order_id, plan_steps=5) as span:
            final_report = coordinator.execute(plan, agent_map)
            span.end(outputs=final_report)
    """
    with _langsmith_trace(
        name="coordinator:execute",
        run_type="chain",
        inputs={
            "session_id": session_id,
            "order_id": order_id,
            "plan_steps": plan_steps,
        },
        metadata={
            "session_id": session_id,
            "order_id": order_id,
        },
        tags=tags or ["coordinator", "orchestration"],
    ) as run:
        yield run


# ---------------------------------------------------------------------------
# trace_function — 兼容旧 OpenTelemetry 装饰器接口
# ---------------------------------------------------------------------------

def trace_function(func: Callable) -> Callable:
    """
    兼容旧 tracing 装饰器。

    优先使用 @traceable，此装饰器仅用于向后兼容。
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tracer = get_tracer(func.__module__)
        with tracer.start_as_current_span(func.__name__):
            return func(*args, **kwargs)

    return wrapper
