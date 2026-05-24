from __future__ import annotations

import httpx

from core.exceptions import ProviderFailureError


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, messages: list[dict], system: str, max_tokens: int = 2000) -> str:
        user_messages = [m for m in messages if m.get("role") != "system"]
        payload = {
            "model": self.model,
            "system": system,
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "top_p": 0.2,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ProviderFailureError(str(exc)) from exc

        try:
            chunks = data["content"]
            return "".join(part.get("text", "") for part in chunks).strip()
        except (KeyError, TypeError) as exc:
            raise ProviderFailureError(f"Bad Claude response: {exc}") from exc
