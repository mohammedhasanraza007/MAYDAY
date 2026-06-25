"""
MAYDAY Event Stream - action/observation typed bus.
Zero dependency on Qt; UI subscribes via callbacks.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class AgentAction:
    type: str
    tool: str | None
    parameters: dict
    timestamp: float = field(default_factory=time.time)
    action_id: str = ""


@dataclass
class AgentObservation:
    action_id: str
    status: str
    result: dict
    timestamp: float = field(default_factory=time.time)
    pinned: bool = False


class EventStream:
    """Thread-safe event bus. Orchestrator emits; UI and memory subscribe."""

    def __init__(self, maxlen: int = 500):
        self._events: deque = deque(maxlen=maxlen)
        self._subscribers: list[Callable] = []
        self._lock = threading.Lock()

    def emit(self, event: AgentAction | AgentObservation) -> None:
        with self._lock:
            self._events.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                pass

    def subscribe(self, callback: Callable) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        with self._lock:
            self._subscribers = [c for c in self._subscribers if c != callback]

    def get_history(self) -> list:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


agent_event_stream = EventStream()
