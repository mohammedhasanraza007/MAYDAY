from __future__ import annotations

import time

import pytest

import core.model_router as router_module
from core.model_router import ModelRouter
from runtime.api_manager import APIApprovalRequired, ApiManager


def test_key_store_encrypts_round_trip(tmp_path):
    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")

    manager.save_key("openai", "test-secret-key")

    assert manager.has_active_provider() is True
    assert manager.active_provider_name() == "openai"
    assert manager.get_key("openai") == "test-secret-key"
    assert b"test-secret-key" not in (tmp_path / "keys.enc").read_bytes()


def test_no_call_without_approval(tmp_path):
    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")
    manager.save_key("openai", "test-key")

    with pytest.raises(APIApprovalRequired):
        manager.complete("hi", "")


def test_call_after_approval(tmp_path, monkeypatch):
    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")
    manager.save_key("openai", "test-key")
    manager.set_user_approved(True)

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return object()

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeHTTPXClient:
        def __init__(self, timeout):
            assert timeout == 120.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            assert url == "https://api.openai.com/v1/chat/completions"
            assert headers["Authorization"] == "Bearer test-key"
            assert json["messages"][-1]["content"] == "hi"
            assert json["max_tokens"] == 2000
            return FakeResponse()

    monkeypatch.setattr(
        "runtime.provider_clients.openai_compatible_client.httpx.Client",
        FakeHTTPXClient,
    )

    assert manager.complete("hi", "") == "ok"


def test_pbkdf2_no_hardcoded_fallback(tmp_path, monkeypatch):
    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")
    salt = manager._get_or_create_salt()
    monkeypatch.delenv("MAYDAY_KEYSTORE_SECRET", raising=False)

    key = manager._derive_key(salt)

    assert isinstance(key, bytes)
    assert key != b"mayday"


def test_missing_salt_path_raises_instead_of_fallback(tmp_path):
    manager = ApiManager(
        keys_path=tmp_path / "missing" / "keys.enc",
        salt_path=tmp_path / "missing" / ".salt",
    )

    with pytest.raises(FileNotFoundError):
        manager._get_or_create_salt()


def test_api_panel_saves_to_runtime_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from ui.panels import APIManagerPanel

    app = QApplication.instance() or QApplication([])
    assert app is not None

    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")
    panel = APIManagerPanel()
    panel.api_keys_saved.connect(lambda keys: [manager.save_key(k, v) for k, v in keys.items()])
    panel.api_approval_changed.connect(manager.set_user_approved)

    panel.provider_inputs["openai"].setText("ui-dummy-key")
    panel._save_keys()
    panel.approval_checkbox.setChecked(True)

    client = manager._client_for(manager.active_provider_name(), manager.get_key("openai"))
    assert client.api_key == "ui-dummy-key"
    assert manager.api_user_approved is True
    assert b"ui-dummy-key" not in (tmp_path / "keys.enc").read_bytes()


def test_router_surfaces_api_approval_requirement(tmp_path, monkeypatch):
    class SlowInference:
        loader = None

        def generate(self, prompt, context):
            time.sleep(0.05)
            return "late local response"

        def destroy_model(self):
            return object()

    monkeypatch.setattr(router_module, "LOCAL_TIMEOUT_WITH_API", 0.01)
    manager = ApiManager(keys_path=tmp_path / "keys.enc", salt_path=tmp_path / ".salt")
    manager.save_key("openai", "test-key")

    router = ModelRouter(SlowInference(), manager)

    with pytest.raises(APIApprovalRequired):
        router.route("build a multi file project with an api", "")
