"""
M.A.Y.D.A.Y Provider Cooldown Manager
======================================
Tracks per-provider rate-limit cooldown windows from 429 Retry-After headers.
Prevents retry storms that waste cycles and degrade UX.

Addresses E104 (rate limit collision failure).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Dict

logger = logging.getLogger("mayday.cooldown")


class ProviderCooldownManager:
    """Singleton-style cooldown tracker for API providers.

    Usage:
        cooldown.record_rate_limit("openai_compatible", 29)
        if cooldown.is_cooled_down("openai_compatible"):
            # safe to call
        else:
            wait = cooldown.seconds_remaining("openai_compatible")
            # skip or queue
    """

    def __init__(self) -> None:
        self._cooldowns: Dict[str, float] = {}  # provider -> earliest_retry_time
        self._epochs: Dict[str, int] = {}
        self._failures: Dict[str, deque[float]] = {}
        self._last_byok_notice: Dict[str, float] = {}
        self._lock = threading.RLock()

    def record_rate_limit(self, provider: str, retry_after_seconds: float) -> None:
        """Record that a provider returned 429 with a Retry-After value."""
        now = time.time()
        with self._lock:
            history = self._failures.setdefault(provider, deque(maxlen=20))
            history.append(now)
            cutoff = now - 300
            while history and history[0] < cutoff:
                history.popleft()
            recent_count = len(history)
            exponential_floor = min(600.0, 60.0 * (2 ** max(recent_count - 1, 0)))
            effective_retry_after = max(float(retry_after_seconds), exponential_floor, 1.0)
            retry_at = now + effective_retry_after
            self._cooldowns[provider] = retry_at
            self._epochs[provider] = self._epochs.get(provider, 0) + 1
        logger.info(
            "Rate limit recorded for %s - retry after %.1f seconds (at %.0f, recent_429s=%d)",
            provider, effective_retry_after, retry_at, recent_count,
        )
        if recent_count >= 3:
            self._maybe_log_byok_notice(provider, recent_count)

    def is_cooled_down(self, provider: str) -> bool:
        """Return True if the provider's cooldown has expired."""
        with self._lock:
            retry_at = self._cooldowns.get(provider, 0.0)
        return time.time() >= retry_at

    def seconds_remaining(self, provider: str) -> float:
        """Return seconds until the provider is available again. 0 if ready."""
        with self._lock:
            retry_at = self._cooldowns.get(provider, 0.0)
        remaining = retry_at - time.time()
        return max(remaining, 0.0)

    def failures_in_last(self, provider: str, minutes: float = 5.0) -> int:
        """Return recent 429 failures for a provider."""
        now = time.time()
        cutoff = now - (minutes * 60.0)
        with self._lock:
            history = self._failures.setdefault(provider, deque(maxlen=20))
            while history and history[0] < cutoff:
                history.popleft()
            return len(history)

    def epoch(self, provider: str) -> int:
        with self._lock:
            return self._epochs.get(provider, 0)

    def snapshot(self, provider: str) -> dict[str, float | int | str | bool]:
        with self._lock:
            retry_at = self._cooldowns.get(provider, 0.0)
            epoch = self._epochs.get(provider, 0)
            recent_429s = len(self._failures.get(provider, ()))
        return {
            "provider": provider,
            "cooldown_epoch": epoch,
            "retry_at": retry_at,
            "cooled_down": time.time() >= retry_at,
            "seconds_remaining": max(retry_at - time.time(), 0.0),
            "recent_429s": recent_429s,
        }

    def clear(self, provider: str | None = None) -> None:
        """Clear cooldown for a specific provider or all providers."""
        if provider is None:
            with self._lock:
                self._cooldowns.clear()
                self._epochs.clear()
                self._failures.clear()
                self._last_byok_notice.clear()
        else:
            with self._lock:
                self._cooldowns.pop(provider, None)
                self._epochs[provider] = self._epochs.get(provider, 0) + 1
                self._failures.pop(provider, None)
                self._last_byok_notice.pop(provider, None)

    def _maybe_log_byok_notice(self, provider: str, recent_count: int) -> None:
        now = time.time()
        with self._lock:
            last = self._last_byok_notice.get(provider, 0.0)
            if now - last < 120:
                return
            self._last_byok_notice[provider] = now
        logger.warning(
            "Provider %s has %d recent 429s. Free upstream quota is saturated; add a BYOK key or wait for cooldown.",
            provider, recent_count,
        )


# Module-level singleton
provider_cooldown = ProviderCooldownManager()
