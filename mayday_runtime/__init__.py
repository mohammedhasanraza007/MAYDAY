"""Application execution layer (renamed from `runtime` to avoid collision with embedded `runtime/python/`)."""

__all__ = ["ExecutionEngine", "ApiManager"]


def __getattr__(name: str):
    if name == "ExecutionEngine":
        from mayday_runtime.engine import ExecutionEngine

        return ExecutionEngine
    if name == "ApiManager":
        from mayday_runtime.api_manager import ApiManager

        return ApiManager
    raise AttributeError(name)
