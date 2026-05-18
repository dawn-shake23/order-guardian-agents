import os

_tracing_initialized = False


def init_tracing():
    global _tracing_initialized
    if _tracing_initialized:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        service_name = os.environ.get("SERVICE_NAME", "order-guardian")
        resource = Resource.create({"service.name": service_name})
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        _tracing_initialized = True
    except ImportError:
        pass


def get_tracer(name: str):
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None


def trace_function(func):
    return func
