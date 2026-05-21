from __future__ import annotations

import base64
import html
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


SearchResult = dict[str, str]
NO_CONFIG_VALUE: str | None = None


class SearchRouter:
    def __init__(
        self,
        brave_key: str | None = None,
        serper_key: str | None = None,
        searxng_url: str | None = None,
        timeout: float = 10.0,
        allow_bing_fallback: bool = True,
    ):
        self.brave_key = _clean_optional(brave_key)
        self.serper_key = _clean_optional(serper_key)
        self.searxng_url = _clean_optional(searxng_url)
        self.timeout = timeout
        self.allow_bing_fallback = allow_bing_fallback

    def search(self, query: str, provider: str | None = None) -> list[SearchResult]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []

        for provider_name, handler in self._providers(provider):
            try:
                results = handler(normalized_query)
            except httpx.HTTPError:
                results = []
            except ValueError:
                results = []
            if results:
                return results
        return []

    def _providers(
        self,
        requested: str | None,
    ) -> list[tuple[str, Callable[[str], list[SearchResult]]]]:
        available: list[tuple[str, Callable[[str], list[SearchResult]]]] = []
        if self.searxng_url:
            available.append(("searxng", self._search_searxng))
        if self.brave_key:
            available.append(("brave", self._search_brave))
        if self.serper_key:
            available.append(("serper", self._search_serper))
        if self.allow_bing_fallback:
            available.append(("bing", self._search_bing))

        requested_name = (requested or "").strip().lower()
        if not requested_name:
            return available
        if requested_name == "searx":
            requested_name = "searxng"
        return [(name, handler) for name, handler in available if name == requested_name]

    def _search_searxng(self, query: str) -> list[SearchResult]:
        if not self.searxng_url:
            return []
        base_url = self.searxng_url.rstrip("/")
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json"},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        return _normalize_results(payload.get("results", []), "content", "url")

    def _search_brave(self, query: str) -> list[SearchResult]:
        if not self.brave_key:
            return []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.brave_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
        web_results = payload.get("web", {}).get("results", [])
        return _normalize_results(web_results, "description", "url")

    def _search_serper(self, query: str) -> list[SearchResult]:
        if not self.serper_key:
            return []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.post(
                "https://google.serper.dev/search",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-API-KEY": self.serper_key,
                },
                json={"q": query},
            )
            response.raise_for_status()
            payload = response.json()
        return _normalize_results(payload.get("organic", []), "snippet", "link")

    def _search_bing(self, query: str) -> list[SearchResult]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Mozilla/5.0 MAYDAY-WebSearch/1.0",
                },
            )
            response.raise_for_status()
        return _parse_bing_results(response.text)


def _clean_optional(value: str | None) -> str | None:
    if not isinstance(value, str):
        return NO_CONFIG_VALUE
    stripped = value.strip()
    return stripped or NO_CONFIG_VALUE


def _normalize_results(
    raw_results: Any,
    snippet_field: str,
    url_field: str,
) -> list[SearchResult]:
    if not isinstance(raw_results, list):
        return []

    normalized: list[SearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = _coerce_text(item.get("title"))
        url = _coerce_text(item.get(url_field) or item.get("url") or item.get("link"))
        snippet = _coerce_text(item.get(snippet_field) or item.get("snippet") or item.get("content"))
        if title and url:
            normalized.append({"title": title, "url": url, "snippet": snippet})
    return normalized


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_bing_results(text: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    pattern = re.compile(
        r"<h2[^>]*>\s*<a[^>]+href=\"(?P<url>[^\"]+)\"[^>]*>(?P<title>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        url = _decode_bing_url(html.unescape(match.group("url")))
        title = _strip_html(match.group("title"))
        if not title or not url or "bing.com/search" in url:
            continue
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= 10:
            break
    return results


def _decode_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/"):
        return url
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if not encoded.startswith("a1"):
        return url
    payload = encoded[2:]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(payload + padding).decode("utf-8")
    except Exception:
        return url


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return html.unescape(without_tags).strip()
