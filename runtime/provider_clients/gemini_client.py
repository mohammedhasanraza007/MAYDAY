from __future__ import annotations

import httpx

from core.exceptions import ProviderFailureError


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro") -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, messages: list[dict], system: str, max_tokens: int = 2000) -> str:
        text = "\n\n".join(m.get("content", "") for m in messages)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ProviderFailureError(str(exc)) from exc

        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderFailureError(f"Bad Gemini response: {exc}") from exc
