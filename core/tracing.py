from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
import os

# 初始化追踪系统
def init_tracing():
    # 设置服务名称
    service_name = os.environ.get("SERVICE_NAME", "order-guardian")
    
    # 创建资源
    resource = Resource.create({
        "service.name": service_name
    })
    
    # 创建追踪提供者
    tracer_provider = TracerProvider(resource=resource)
    
    # 创建OTLP导出器
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.environ.get("OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
    )
    
    # 添加批处理器
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    # 设置全局追踪提供者
    trace.set_tracer_provider(tracer_provider)

# 获取追踪器
def get_tracer(name: str):
    return trace.get_tracer(name)

# 追踪装饰器
def trace_function(func):
    def wrapper(*args, **kwargs):
        tracer = get_tracer(func.__module__)
        with tracer.start_as_current_span(func.__name__):
            return func(*args, **kwargs)
    return wrapper