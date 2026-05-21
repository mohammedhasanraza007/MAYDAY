from __future__ import annotations

from typing import Any

from core.exceptions import WebAccessDisabledError
from runtime.search_router import SearchRouter


_brave_key: str | None = None
_serper_key: str | None = None
_searxng_url: str | None = None
_web_enabled = False
NO_CONFIG_VALUE: str | None = None


def configure_search(
    brave_key: str | None = None,
    serper_key: str | None = None,
    searxng_url: str | None = None,
) -> dict[str, str | None]:
    global _brave_key, _serper_key, _searxng_url
    _brave_key = _clean_optional(brave_key)
    _serper_key = _clean_optional(serper_key)
    _searxng_url = _clean_optional(searxng_url)
    return get_search_config()


def set_web_enabled(enabled: bool) -> bool:
    global _web_enabled
    _web_enabled = bool(enabled)
    return _web_enabled


def is_web_enabled() -> bool:
    return _web_enabled


def ensure_web_enabled() -> None:
    if not _web_enabled:
        raise WebAccessDisabledError("Web access is disabled. Enable it before search or fetch.")


def get_search_config() -> dict[str, str | None]:
    return {
        "brave_key": _brave_key,
        "serper_key": _serper_key,
        "searxng_url": _searxng_url,
    }


def search(query: str, provider: str | None = None) -> list[dict[str, str]]:
    ensure_web_enabled()
    router = SearchRouter(
        brave_key=_brave_key,
        serper_key=_serper_key,
        searxng_url=_searxng_url,
    )
    return router.search(query, provider=provider)


class WebAccessTool:
    @property
    def name(self) -> str:
        return "web_access"

    @property
    def description(self) -> str:
        return "Web search using configured SearXNG, Brave, or Serper providers"

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        tool_name = parameters.get("_tool_name", "web_search")
        if tool_name != "web_search":
            return {"status": "error", "error": f"Unsupported web action: {tool_name}"}

        query = parameters.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return {"status": "error", "error": "web_search.query must be a non-empty string"}

        provider = parameters.get("provider")
        if provider is not None and not isinstance(provider, str):
            return {"status": "error", "error": "web_search.provider must be a string when provided"}

        results = search(query, provider=provider)
        return {"status": "success", "results": results, "count": len(results)}


def _clean_optional(value: str | None) -> str | None:
    if not isinstance(value, str):
        return NO_CONFIG_VALUE
    stripped = value.strip()
    return stripped or NO_CONFIG_VALUE
