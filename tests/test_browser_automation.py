from __future__ import annotations

import os
import functools
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from runtime.browser_audit_log import read_recent
from runtime.browser_automation import BrowserAutomation
from runtime.browser_session import PROFILE_DIR, SessionRegistry
from runtime.permission_gate import permission_gate


def _chromium_available() -> bool:
    try:
        os.environ.setdefault("MAYDAY_BROWSER_HEADLESS", "1")
        os.environ["MAYDAY_AUTO_APPROVE_BROWSER"] = "1"
        result = BrowserAutomation().execute(
            {
                "_tool_name": "browser_open",
                "url": "data:text/html;charset=utf-8,<title>launch-check</title>",
            }
        )
        session_id = result.get("session_id", "")
        if session_id:
            BrowserAutomation().execute({"_tool_name": "browser_close", "session_id": session_id})
        return result.get("status") == "success"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_available(), reason="Playwright chromium is not installed or cannot launch")


@pytest.fixture(autouse=True)
def browser_env(monkeypatch):
    monkeypatch.setenv("MAYDAY_AUTO_APPROVE_BROWSER", "1")
    monkeypatch.setenv("MAYDAY_BROWSER_HEADLESS", "1")
    permission_gate.cancelled = False
    yield
    SessionRegistry.close_all()
    permission_gate.cancelled = False


@pytest.fixture
def local_site(tmp_path):
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>Example Domain</title><h1>Example Domain</h1>",
        encoding="utf-8",
    )
    (tmp_path / "form.html").write_text(
        "<!doctype html><title>Form</title><form><input name='custname'></form>",
        encoding="utf-8",
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_open_real_url(local_site):
    result = BrowserAutomation().execute({"_tool_name": "browser_open", "url": f"{local_site}/index.html"})

    assert result["status"] == "success"
    assert "Example" in result["title"]
    screenshot = Path(result["screenshot"])
    assert screenshot.exists()
    assert screenshot.stat().st_size > 1024


def test_atomic_form_fill_real(local_site):
    ba = BrowserAutomation()
    opened = ba.execute({"_tool_name": "browser_open", "url": f"{local_site}/form.html"})

    result = ba.execute(
        {
            "_tool_name": "browser_type",
            "session_id": opened["session_id"],
            "selector": "input[name=custname]",
            "text": "TEST",
        }
    )

    assert result["status"] == "success"
    assert result["value"] == "TEST"


def test_permission_denied_blocks(monkeypatch):
    monkeypatch.delenv("MAYDAY_AUTO_APPROVE_BROWSER", raising=False)
    permission_gate.cancelled = False

    result = BrowserAutomation().execute({"_tool_name": "browser_open", "url": "data:text/html,<title>Denied</title>"})

    assert result["status"] == "cancelled"
    assert result["reason"] == "user_denied"


def test_audit_log_written(local_site):
    result = BrowserAutomation().execute({"_tool_name": "browser_open", "url": f"{local_site}/index.html"})

    recent = read_recent(20)
    assert result["status"] == "success"
    assert any(entry.get("action") == "open" and entry.get("session_id") == result["session_id"] for entry in recent)


def test_session_persistence():
    ba = BrowserAutomation()
    first = ba.execute({"_tool_name": "browser_open", "url": "data:text/html,<title>Persist 1</title>"})
    ba.execute({"_tool_name": "browser_close", "session_id": first["session_id"]})
    second = ba.execute({"_tool_name": "browser_open", "url": "data:text/html,<title>Persist 2</title>"})

    cookie_files = list(PROFILE_DIR.rglob("Cookies"))
    assert second["status"] == "success"
    assert any(path.stat().st_size > 0 for path in cookie_files)
