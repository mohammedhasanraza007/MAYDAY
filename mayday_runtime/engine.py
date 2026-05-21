"""
M.A.Y.D.A.Y execution engine — tool dispatch only (no direct tool imports from orchestrator).
"""
from __future__ import annotations

import logging
from typing import Any
from core.gateway import ToolGatewayCore

logger = logging.getLogger("mayday.execution")


class ExecutionEngine:
    """Registers tools by short name (e.g. file, browser) and dispatches execute()."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}
        self.gateway = ToolGatewayCore()

    def set_gateway_callback(self, callback):
        self.gateway.set_permission_callback(callback)

    def register_tool(self, name: str, tool: Any) -> None:
        self._registry[name] = tool

    def register_tools(self, mapping: dict[str, Any]) -> None:
        for name, tool in mapping.items():
            self.register_tool(name, tool)

    def get_registered_tools(self) -> list[str]:
        return sorted(self._registry.keys())

    def execute_tool(self, tool_name: str, parameters: dict) -> Any:
        if not tool_name:
            raise ValueError("tool_name is required")

        params = dict(parameters or {})
        base = tool_name
        if "." in tool_name:
            base, sub = tool_name.split(".", 1)
            params.setdefault("_tool_name", sub)

        tool = self._registry.get(base)
        if tool is None:
            raise KeyError(f"No tool registered for {tool_name!r} (base={base!r})")

        if not hasattr(tool, "execute"):
            raise TypeError(f"Registered object for {base!r} has no execute()")

        # Gatekeeper validation
        self.gateway.validate_and_request_permission(base, params)

        logger.debug("execute_tool base=%s keys=%s", base, list(params.keys()))
        return tool.execute(params)
