from __future__ import annotations

import json as _json
import logging

import httpx

from core.exceptions import ProviderFailureError

_logger = logging.getLogger("mayday.api")


class RateLimitError(ProviderFailureError):
    """Raised when a provider returns HTTP 429 with a Retry-After value."""

    def __init__(self, message: str, retry_after: float = 30.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, messages: list[dict], system: str, max_tokens: int = 2000) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                _logger.info("OpenAI-compatible success response: %s", data)
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text if exc.response is not None else ""

            # Parse 429 rate-limit responses and extract Retry-After
            if exc.response is not None and exc.response.status_code == 429:
                retry_after = self._extract_retry_after(exc.response, response_text)
                _logger.warning(
                    "Rate limited (429) — retry after %.1fs. Response: %s",
                    retry_after, response_text[:300],
                )
                raise RateLimitError(
                    f"Rate limited: {response_text[:300]}",
                    retry_after=retry_after,
                ) from exc

            _logger.error(
                "HTTP Error during OpenAI-compatible completion: %s. Response content: %s",
                exc, response_text,
            )
            raise ProviderFailureError(f"HTTP Error: {exc}. Response: {response_text}") from exc
        except httpx.HTTPError as exc:
            response_text = ""
            if hasattr(exc, "response") and exc.response is not None:
                response_text = exc.response.text
            _logger.error(
                "HTTP Error during OpenAI-compatible completion: %s. Response content: %s",
                exc, response_text,
            )
            raise ProviderFailureError(f"HTTP Error: {exc}. Response: {response_text}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderFailureError(f"Bad OpenAI-compatible response: {exc}") from exc

    @staticmethod
    def _extract_retry_after(response: httpx.Response, body_text: str) -> float:
        """Extract Retry-After seconds from response headers or JSON body."""
        # Try JSON body first (OpenRouter includes metadata.retry_after_seconds)
        try:
            data = _json.loads(body_text)
            metadata = data.get("error", {}).get("metadata", {})
            raw_seconds = metadata.get("retry_after_seconds_raw") or metadata.get("retry_after_seconds")
            if raw_seconds is not None:
                return float(raw_seconds)
        except (ValueError, TypeError, _json.JSONDecodeError, AttributeError):
            pass

        # Fall back to Retry-After header
        header = response.headers.get("Retry-After", "")
        if header:
            try:
                return float(header)
            except ValueError:
                pass

        return 30.0  # safe default
