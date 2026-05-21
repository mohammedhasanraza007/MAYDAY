from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from core.exceptions import WebAccessDisabledError
from runtime import web_access
from runtime.page_fetcher import PageFetcher, PageFetchTool
from runtime.web_access import WebAccessTool


@pytest.fixture(autouse=True)
def reset_web_access():
    web_access.configure_search()
    web_access.set_web_enabled(False)
    yield
    web_access.configure_search()
    web_access.set_web_enabled(False)


def test_disabled_raises():
    with pytest.raises(WebAccessDisabledError):
        web_access.search("mayday")

    with pytest.raises(WebAccessDisabledError):
        PageFetcher().fetch("https://example.com")


def test_keys_persist_across_calls():
    server, base_url, requests = _start_search_server()
    try:
        web_access.configure_search(
            brave_key="brave-test-key",
            serper_key="serper-test-key",
            searxng_url=base_url,
        )
        web_access.set_web_enabled(True)

        first = web_access.search("alpha")
        second = web_access.search("beta")

        assert web_access.get_search_config() == {
            "brave_key": "brave-test-key",
            "serper_key": "serper-test-key",
            "searxng_url": base_url,
        }
        assert first[0]["title"] == "Result for alpha"
        assert second[0]["title"] == "Result for beta"
        assert requests == ["alpha", "beta"]
    finally:
        server.shutdown()
        server.server_close()


def test_searxng_pytest_importorskip():
    pytest.importorskip("httpx")
    server, base_url, requests = _start_search_server()
    try:
        web_access.configure_search(searxng_url=base_url)
        web_access.set_web_enabled(True)

        results = web_access.search("portable runtime", provider="searxng")

        assert requests == ["portable runtime"]
        assert results == [
            {
                "title": "Result for portable runtime",
                "url": "https://example.test/portable-runtime",
                "snippet": "Snippet for portable runtime",
            }
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_page_fetcher_fetches_real_http_response():
    server, base_url = _start_page_server()
    try:
        web_access.set_web_enabled(True)

        result = PageFetcher().fetch(f"{base_url}/hello")

        assert result["status"] == "success"
        assert result["status_code"] == 200
        assert result["bytes"] > 0
        assert result["title"] == ""
        assert "hello from mayday" in result["text"]
    finally:
        server.shutdown()
        server.server_close()


def test_tool_wrappers_execute_real_search_and_fetch():
    search_server, search_url, requests = _start_search_server()
    page_server, page_url = _start_page_server()
    try:
        web_access.configure_search(searxng_url=search_url)
        web_access.set_web_enabled(True)

        search_result = WebAccessTool().execute(
            {"_tool_name": "web_search", "query": "wrapper test"}
        )
        fetch_result = PageFetchTool().execute(
            {"_tool_name": "web_fetch", "url": f"{page_url}/hello"}
        )

        assert search_result["status"] == "success"
        assert search_result["count"] == 1
        assert search_result["results"][0]["title"] == "Result for wrapper test"
        assert fetch_result["status"] == "success"
        assert fetch_result["status_code"] == 200
        assert requests == ["wrapper test"]
    finally:
        search_server.shutdown()
        search_server.server_close()
        page_server.shutdown()
        page_server.server_close()


def _start_search_server():
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/search":
                self.send_error(404)
                return
            query = parse_qs(parsed.query).get("q", [""])[0]
            requests.append(query)
            payload = {
                "results": [
                    {
                        "title": f"Result for {query}",
                        "url": "https://example.test/" + query.replace(" ", "-"),
                        "content": f"Snippet for {query}",
                    }
                ]
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}", requests


def _start_page_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/hello":
                self.send_error(404)
                return
            body = b"<html><body>hello from mayday</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"
