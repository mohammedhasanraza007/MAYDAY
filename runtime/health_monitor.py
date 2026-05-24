from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass(frozen=True)
class RuntimeHealth:
    safe_mode: bool
    retry_spikes: int
    failure_spikes: int
    max_context_chars: int
    cooldown_events: int
    inference_slowdowns: int


class RuntimeHealthMonitor:
    def __init__(self) -> None:
        self._events: Deque[tuple[float, str, float]] = deque(maxlen=200)
        self._safe_mode = False

    def record(self, event: str, value: float = 1.0) -> None:
        now = time.time()
        self._events.append((now, event, value))
        self._prune(now)
        if self._threshold_exceeded(now):
            self.enter_safe_mode()

    def enter_safe_mode(self) -> None:
        self._safe_mode = True

    def exit_safe_mode(self) -> None:
        self._safe_mode = False

    def is_safe_mode(self) -> bool:
        self._prune(time.time())
        if self._threshold_exceeded(time.time()):
            self._safe_mode = True
        return self._safe_mode

    def snapshot(self) -> RuntimeHealth:
        now = time.time()
        self._prune(now)
        return RuntimeHealth(
            safe_mode=self._safe_mode,
            retry_spikes=self._count("retry"),
            failure_spikes=self._count("failure"),
            max_context_chars=int(max((value for _, event, value in self._events if event == "context_chars"), default=0)),
            cooldown_events=self._count("cooldown"),
            inference_slowdowns=self._count("slow_inference"),
        )

    def _count(self, event_name: str) -> int:
        return sum(1 for _, event, _ in self._events if event == event_name)

    def _prune(self, now: float) -> None:
        cutoff = now - 120
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def _threshold_exceeded(self, now: float) -> bool:
        recent = [event for ts, event, _ in self._events if ts >= now - 60]
        return (
            recent.count("retry") >= 4
            or recent.count("failure") >= 5
            or recent.count("cooldown") >= 3
            or recent.count("slow_inference") >= 3
        )


runtime_health_monitor = RuntimeHealthMonitor()
