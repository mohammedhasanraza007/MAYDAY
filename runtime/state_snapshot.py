from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StateSnapshot:
    session_history: list[dict[str, str]] = field(default_factory=list)
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    last_provider: str = "unknown"


class StateSnapshotManager:
    def capture(self, orchestrator: Any) -> StateSnapshot:
        session = getattr(orchestrator, "session", None)
        history = []
        if session is not None:
            raw_history = getattr(session, "history", getattr(session, "_history", []))
            history = [dict(item) for item in raw_history if isinstance(item, dict)]
        return StateSnapshot(
            session_history=history,
            tools_used=[dict(item) for item in getattr(orchestrator, "_tools_used", [])],
            last_provider=str(getattr(orchestrator, "_last_provider", "unknown")),
        )

    def rollback(self, orchestrator: Any, snapshot: StateSnapshot) -> None:
        session = getattr(orchestrator, "session", None)
        if session is not None:
            if hasattr(session, "history"):
                session.history = [dict(item) for item in snapshot.session_history]
            elif hasattr(session, "_history"):
                session._history = [dict(item) for item in snapshot.session_history]
        orchestrator._tools_used = [dict(item) for item in snapshot.tools_used]
        orchestrator._last_provider = snapshot.last_provider
