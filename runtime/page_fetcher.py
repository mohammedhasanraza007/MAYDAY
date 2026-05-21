from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from runtime import web_access


class PageFetcher:
    def fetch(self, url: str, timeout: float = 10) -> dict[str, Any]:
        web_access.ensure_web_enabled()
        normalized_url = (url or "").strip()
        if not _is_http_url(normalized_url):
            return {"status": "error", "error": "Only http and https URLs can be fetched"}

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(
                    normalized_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
                        "User-Agent": "MAYDAY-WebFetcher/1.0",
                    },
                )
        except httpx.HTTPError as exc:
            return {"status": "error", "error": str(exc), "url": normalized_url}

        text = response.text
        title = _extract_title(text)
        return {
            "status": "success",
            "url": str(response.url),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
            "title": title,
            "text": text,
        }


class PageFetchTool:
    @property
    def name(self) -> str:
        return "page_fetcher"

    @property
    def description(self) -> str:
        return "Fetch a web page with real HTTP and return response evidence"

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        tool_name = parameters.get("_tool_name", "web_fetch")
        if tool_name != "web_fetch":
            return {"status": "error", "error": f"Unsupported fetch action: {tool_name}"}

        url = parameters.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return {"status": "error", "error": "web_fetch.url must be a non-empty string"}

        timeout = parameters.get("timeout", 10)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            return {"status": "error", "error": "web_fetch.timeout must be a positive number"}

        return PageFetcher().fetch(url, timeout=float(timeout))


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.IGNORECASE | re.DOTALL)
    if match is None:
        return ""
    compact = re.sub(r"\s+", " ", match.group(1)).strip()
    return html.unescape(compact)
