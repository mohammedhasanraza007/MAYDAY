from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskNode:
    id: str
    tool_name: str
    parameters: dict[str, Any]
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""


class TaskGraphExecutor:
    """Sequential task graph executor with per-node result capture.

    MAYDAY's model interface already emits ordered tool calls. This class makes
    that order explicit and exposes node validation/failure state to the caller.
    """

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.nodes = [
            TaskNode(
                id=f"node_{index + 1}",
                tool_name=str(entry.get("tool_name", "")),
                parameters=dict(entry.get("parameters", {}) or {}),
            )
            for index, entry in enumerate(entries)
            if isinstance(entry, dict)
        ]

    def run(self, execute: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        overall_status = "success"
        output: list[dict[str, Any]] = []
        for node in self.nodes:
            node.status = "running"
            node.started_at = _now()
            result = execute(node.tool_name, node.parameters)
            node.result = result
            node.finished_at = _now()
            node.status = str(result.get("status", "unknown")) if isinstance(result, dict) else "error"
            output.append({"tool": node.tool_name, "result": result, "node_id": node.id})
            if not isinstance(result, dict) or result.get("status") != "success":
                overall_status = "cancelled" if isinstance(result, dict) and result.get("status") == "cancelled" else "error"
                break
        return {
            "status": overall_status,
            "results": output,
            "task_graph": [
                {
                    "id": node.id,
                    "tool_name": node.tool_name,
                    "status": node.status,
                    "started_at": node.started_at,
                    "finished_at": node.finished_at,
                }
                for node in self.nodes
            ],
        }
