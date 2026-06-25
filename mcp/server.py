"""
MAYDAY MCP Server - exposes MAYDAY tools as HTTP endpoints.
Runs FastAPI in a daemon thread without external container services.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("mayday.mcp")

_server_thread: threading.Thread | None = None
_tools_registry: dict[str, Any] = {}


def register_tool(name: str, tool_instance: Any) -> None:
    """Register a MAYDAY BaseTool instance for MCP exposure."""
    _tools_registry[name] = tool_instance


def _run_server() -> None:
    try:
        from fastapi import FastAPI
        import uvicorn

        app = FastAPI(title="MAYDAY MCP Server", version="1.0")

        @app.get("/tools")
        def list_tools():
            return {
                "tools": [
                    {
                        "name": name,
                        "capabilities": getattr(tool, "get_capabilities", lambda: [])(),
                    }
                    for name, tool in _tools_registry.items()
                ]
            }

        @app.post("/execute")
        def execute_tool(payload: dict):
            tool_name = payload.get("tool")
            parameters = dict(payload.get("parameters", {}))
            if tool_name not in _tools_registry:
                return {"status": "error", "error": f"Unknown tool: {tool_name}"}
            try:
                parameters["_tool_name"] = payload.get("action", tool_name)
                result = _tools_registry[tool_name].execute(parameters)
                return {"status": "ok", "result": result}
            except Exception as exc:
                return {"status": "error", "error": str(exc)}

        @app.get("/health")
        def health():
            return {"status": "running", "tools": len(_tools_registry)}

        uvicorn.run(app, host="127.0.0.1", port=9998, log_level="warning")
    except ImportError:
        logger.warning("MCP server unavailable: fastapi/uvicorn not installed")
    except Exception as exc:
        logger.error("MCP server error: %s", exc)


def start_mcp_server(tools: dict[str, Any]) -> None:
    """Start MCP server in a daemon thread. Safe to call more than once."""
    global _server_thread
    for name, tool in tools.items():
        register_tool(name, tool)

    if _server_thread is not None and _server_thread.is_alive():
        logger.info("MCP server already running on http://127.0.0.1:9998")
        return

    _server_thread = threading.Thread(target=_run_server, daemon=True, name="mayday-mcp")
    _server_thread.start()
    logger.info("MCP server started on http://127.0.0.1:9998")
