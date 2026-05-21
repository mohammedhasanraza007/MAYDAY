from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


MAX_BROWSER_ATTEMPTS = 2
TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "target page",
    "context or browser has been closed",
    "browser has been closed",
    "page closed",
    "crash",
    "net::err",
    "navigation",
    "profile",
    "connection reset",
)
TERMINAL_MARKERS = (
    "user_denied",
    "denied",
    "cancelled",
    "permission",
    "safety",
    "could not resolve browser target",
    "strict mode violation",
    "unknown tool",
    "schema",
    "outside allowed root",
)


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    reason: str
    delay_seconds: float = 0.0


class RetryPolicy:
    def __init__(self, max_browser_attempts: int = MAX_BROWSER_ATTEMPTS) -> None:
        self.max_browser_attempts = max(1, int(max_browser_attempts))

    def decide(self, tool_name: str, attempt_index: int, result: dict[str, Any] | None = None, exc: Exception | None = None) -> RetryDecision:
        if not tool_name.startswith("browser_"):
            return RetryDecision(False, "non_browser_tool")
        if attempt_index + 1 >= self.max_browser_attempts:
            return RetryDecision(False, "retry_ceiling_reached")

        message = self._message(result, exc)
        lowered = message.lower()
        if any(marker in lowered for marker in TERMINAL_MARKERS):
            return RetryDecision(False, "terminal_failure")
        if any(marker in lowered for marker in TRANSIENT_MARKERS):
            return RetryDecision(True, "transient_browser_failure", self.backoff(attempt_index))
        return RetryDecision(False, "not_classified_recoverable")

    def backoff(self, attempt_index: int) -> float:
        return min(2.0, 0.35 * (2 ** max(0, attempt_index)))

    def sleep(self, decision: RetryDecision) -> None:
        if decision.delay_seconds > 0:
            time.sleep(decision.delay_seconds)

    def _message(self, result: dict[str, Any] | None, exc: Exception | None) -> str:
        parts: list[str] = []
        if exc is not None:
            parts.append(str(exc))
        if isinstance(result, dict):
            for key in ("error", "reason", "classification"):
                value = result.get(key)
                if isinstance(value, str):
                    parts.append(value)
        return " | ".join(parts)


retry_policy = RetryPolicy()
