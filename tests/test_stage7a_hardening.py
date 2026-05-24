from __future__ import annotations

import json

import pytest

from core.composite_translator import CompositeActionTranslator
from core.model_router import ModelRouter
from runtime.action_schema import validate, validate_action
from runtime.execution_registry import BROWSER_ATOMIC_TOOLS, structural_validate
from runtime.provider_clients.openai_compatible_client import RateLimitError
from runtime.provider_cooldown import provider_cooldown
from runtime.engine import ExecutionEngine


def test_browser_act_decomposes_to_registered_atomic_tools_only():
    action = {
        "action": "browser_act",
        "steps": [
            {"action": "open", "url": "https://example.com"},
            {"action": "wait_for", "selector": "main"},
            {"action": "click", "selector": "a"},
        ],
    }

    valid, reason = structural_validate(action)
    assert valid, reason

    translated = CompositeActionTranslator.translate(action)
    assert translated["action"] == "multi_tool_call"
    tool_names = [entry["tool_name"] for entry in translated["tools"]]
    assert tool_names == ["browser_open", "browser_wait", "browser_click"]
    assert all(name in BROWSER_ATOMIC_TOOLS for name in tool_names)
    assert "browser_act" not in tool_names
    assert validate(translated) == (True, "")


def test_hallucinated_browser_tool_is_rejected_not_wrapped():
    action = {"action": "tool_call", "tool_name": "browser_multi", "parameters": {"steps": []}}
    assert CompositeActionTranslator.translate(action) is None

    valid, reason = validate_action("browser_act", {"steps": [{"action": "open", "url": "https://example.com"}]})
    assert not valid
    assert "Unknown or uncontracted tool" in reason


def test_malformed_structure_does_not_reach_translation_contract():
    action = {"action": "multi_tool_call", "tools": [{"tool_name": "browser_open", "parameters": "bad"}]}
    valid, reason = structural_validate(action)
    assert not valid
    assert "parameters must be an object" in reason


def test_engine_rejects_composite_pseudo_tool_at_schema_layer():
    result = ExecutionEngine().execute("browser_act", {"steps": [{"action": "open", "url": "https://example.com"}], "_sandbox_mode": True})
    assert result["status"] == "error"
    assert "Unknown or uncontracted tool" in result["error"]


class _ApiAlways429:
    def __init__(self) -> None:
        self.calls = 0

    def has_active_provider(self) -> bool:
        return True

    def active_provider_name(self) -> str:
        return "openai_compatible"

    def complete(self, prompt, context=""):
        self.calls += 1
        raise RateLimitError("rate limited", retry_after=30)

    def complete_messages(self, messages):
        self.calls += 1
        raise RateLimitError("rate limited", retry_after=30)


class _InvalidLocal:
    loader = None

    def generate(self, prompt, context=""):
        return json.dumps({"action": "respond", "text": "not allowed for executable intent"})

    def destroy_model(self):
        return None


def test_route_epoch_blocks_same_route_double_api_hammering():
    provider_cooldown.clear("openai_compatible")
    api = _ApiAlways429()
    router = ModelRouter(_InvalidLocal(), api)

    raw, provider = router.route("build a complex full stack app with backend database", "")

    payload = json.loads(raw)
    assert provider == "exhausted"
    assert payload["action"] == "respond"
    assert "cooldown" in payload["text"].lower()
    assert api.calls == 1
    assert provider_cooldown.seconds_remaining("openai_compatible") > 0
