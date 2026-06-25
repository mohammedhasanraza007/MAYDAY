"""MAYDAY MCP router adapter derived from the OpenHands MCP surface."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from mcp.server import register_tool, start_mcp_server


router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "running"}


@router.get("/tools")
def tools() -> dict[str, list[dict[str, Any]]]:
    try:
        from mcp.server import _tools_registry

        return {
            "tools": [
                {
                    "name": name,
                    "capabilities": getattr(tool, "get_capabilities", lambda: [])(),
                }
                for name, tool in _tools_registry.items()
            ]
        }
    except Exception:
        return {"tools": []}


def register_mayday_tool(name: str, tool: Any) -> None:
    register_tool(name, tool)


def start_mayday_mcp(tools_by_name: dict[str, Any]) -> None:
    start_mcp_server(tools_by_name)

