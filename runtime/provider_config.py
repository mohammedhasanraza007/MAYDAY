from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = MAYDAY_ROOT / "runtime" / "provider_config.json"


DEFAULT_PROVIDER_CONFIG: dict[str, Any] = {
    "model_api": {
        "active_provider": "openai_compatible",
        "openai_compatible_base_url": "https://openrouter.ai/api/v1",
        "openai_compatible_model": "qwen/qwen3-coder:free",
    },
    "browser": {
        "automation_provider": "playwright",
        "executable_path": "",
        "headless": False,
        "profile_dir": "runtime/browser_profile",
    },
    "desktop": {
        "automation_provider": "pywinauto",
        "ocr_provider": "none",
        "vision_fallback_enabled": True,
    },
    "future_backends": {},
}


class ProviderConfigManager:
    """Non-secret provider/runtime configuration.

    API keys remain in the encrypted key store. This file only stores provider
    choices, endpoints, model names, and executor backend preferences.
    """

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        config = json.loads(json.dumps(DEFAULT_PROVIDER_CONFIG))
        if self.path.exists():
            try:
                disk = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                disk = {}
            if isinstance(disk, dict):
                self._merge(config, disk)
        return config

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        config = self.load()
        self._merge(config, updates)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
        return config

    def get(self, section: str, key: str, default: Any = None) -> Any:
        value = self.load().get(section, {})
        if not isinstance(value, dict):
            return default
        return value.get(key, default)

    def openai_compatible_base_url(self) -> str:
        return (
            os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
            or str(self.get("model_api", "openai_compatible_base_url", "https://api.openai.com/v1"))
        )

    def openai_compatible_model(self) -> str:
        return (
            os.environ.get("OPENAI_COMPATIBLE_MODEL")
            or str(self.get("model_api", "openai_compatible_model", "gpt-4o-mini"))
        )

    def browser_executable_path(self) -> str:
        return os.environ.get("MAYDAY_BROWSER_EXECUTABLE", "") or str(self.get("browser", "executable_path", ""))

    def browser_headless(self) -> bool:
        env = os.environ.get("MAYDAY_BROWSER_HEADLESS", "").strip().lower()
        if env:
            return env in {"1", "true", "yes", "on"}
        return bool(self.get("browser", "headless", False))

    def _merge(self, base: dict[str, Any], updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._merge(base[key], value)
            else:
                base[key] = value


provider_config = ProviderConfigManager()
