from __future__ import annotations

from runtime.engine import ExecutionEngine


def test_gateway_denial_is_terminal_until_reset(monkeypatch):
    monkeypatch.delenv("MAYDAY_AUTO_APPROVE_BROWSER", raising=False)
    engine = ExecutionEngine()
    calls = {"count": 0}

    def deny_once(_action_type: str, _details: str) -> str:
        calls["count"] += 1
        return "DENY"

    engine.set_gateway_callback(deny_once)

    first = engine.execute("browser_open", {"url": "data:text/html,<title>Denied</title>"})
    second = engine.execute("browser_open", {"url": "data:text/html,<title>Denied</title>"})

    assert first["status"] == "cancelled"
    assert second["status"] == "cancelled"
    assert calls["count"] == 1
    assert "previously denied" in second["error"]

    engine.gateway.reset_denials()
    third = engine.execute("browser_open", {"url": "data:text/html,<title>Denied</title>"})

    assert third["status"] == "cancelled"
    assert calls["count"] == 2
