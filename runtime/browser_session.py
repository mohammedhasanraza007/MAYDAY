from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from runtime.playwright_runner import close_context, headless_requested, launch_persistent


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = MAYDAY_ROOT / "runtime" / "browser_profile"


@dataclass
class BrowserSession:
    context: object
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pages: list = field(default_factory=list)
    alive: bool = True

    def touch(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)

    def is_alive(self) -> bool:
        return self.alive

    def close(self) -> None:
        if not self.alive:
            return
        close_context(self.context)
        self.alive = False


class SessionRegistry:
    _sessions: dict[str, BrowserSession] = {}
    _latest_session_id: str = ""
    _close_all_dispatcher: Callable[[], None] | None = None

    @classmethod
    def set_close_all_dispatcher(cls, dispatcher: Callable[[], None] | None) -> None:
        cls._close_all_dispatcher = dispatcher

    @classmethod
    def create(cls) -> BrowserSession:
        if cls._latest_session_id:
            session = cls._sessions.get(cls._latest_session_id)
            if session is not None and session.is_alive():
                session.touch()
                return session
        context = launch_persistent(PROFILE_DIR, headless=headless_requested())
        session = BrowserSession(context=context)
        cls._sessions[session.id] = session
        cls._latest_session_id = session.id
        return session

    @classmethod
    def get(cls, session_id: str) -> BrowserSession:
        session = cls._sessions.get(session_id)
        if session is None or not session.is_alive():
            raise RuntimeError(f"Browser session not found or closed: {session_id}")
        session.touch()
        cls._latest_session_id = session.id
        return session

    @classmethod
    def latest(cls) -> BrowserSession:
        if not cls._latest_session_id:
            raise RuntimeError("No active browser session")
        return cls.get(cls._latest_session_id)

    @classmethod
    def close(cls, session_id: str | None = None) -> BrowserSession:
        session = cls.get(session_id) if session_id else cls.latest()
        session.close()
        cls._sessions.pop(session.id, None)
        if cls._latest_session_id == session.id:
            cls._latest_session_id = ""
            for candidate_id, candidate in reversed(list(cls._sessions.items())):
                if candidate.is_alive():
                    cls._latest_session_id = candidate_id
                    break
        return session

    @classmethod
    def active_count(cls) -> int:
        return sum(1 for session in cls._sessions.values() if session.is_alive())

    @classmethod
    def close_all(cls) -> None:
        if cls._close_all_dispatcher is not None:
            cls._close_all_dispatcher()
            return
        cls._close_all_local()

    @classmethod
    def _close_all_local(cls) -> None:
        for session in list(cls._sessions.values()):
            session.close()
        cls._sessions.clear()
        cls._latest_session_id = ""

    @classmethod
    def cleanup_idle(cls, timeout_minutes: int = 30) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        for session_id, session in list(cls._sessions.items()):
            if session.last_used_at < cutoff:
                session.close()
                cls._sessions.pop(session_id, None)
                if cls._latest_session_id == session_id:
                    cls._latest_session_id = ""
