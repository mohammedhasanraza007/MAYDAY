"""
M.A.Y.D.A.Y Provider Cooldown Manager
======================================
Tracks per-provider rate-limit cooldown windows from 429 Retry-After headers.
Prevents retry storms that waste cycles and degrade UX.

Addresses E104 (rate limit collision failure).
"""
from __future__ import annotations

import logging
import time
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

    def record_rate_limit(self, provider: str, retry_after_seconds: float) -> None:
        """Record that a provider returned 429 with a Retry-After value."""
        retry_at = time.time() + max(retry_after_seconds, 1.0)
        self._cooldowns[provider] = retry_at
        logger.info(
            "Rate limit recorded for %s — retry after %.1f seconds (at %.0f)",
            provider, retry_after_seconds, retry_at,
        )

    def is_cooled_down(self, provider: str) -> bool:
        """Return True if the provider's cooldown has expired."""
        retry_at = self._cooldowns.get(provider, 0.0)
        return time.time() >= retry_at

    def seconds_remaining(self, provider: str) -> float:
        """Return seconds until the provider is available again. 0 if ready."""
        retry_at = self._cooldowns.get(provider, 0.0)
        remaining = retry_at - time.time()
        return max(remaining, 0.0)

    def clear(self, provider: str | None = None) -> None:
        """Clear cooldown for a specific provider or all providers."""
        if provider is None:
            self._cooldowns.clear()
        else:
            self._cooldowns.pop(provider, None)


# Module-level singleton
provider_cooldown = ProviderCooldownManager()
