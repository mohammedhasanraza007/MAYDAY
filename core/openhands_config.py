"""MAYDAY-local OpenHands configuration adapter."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _mayday_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_default_persistence_dir() -> Path:
    configured = os.getenv("OH_PERSISTENCE_DIR") or os.getenv("FILE_STORE_PATH")
    path = Path(configured) if configured else _mayday_root() / ".openhands"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_web_url() -> str | None:
    return os.getenv("MAYDAY_WEB_URL") or os.getenv("WEB_HOST")


def get_default_permitted_cors_origins() -> list[str]:
    raw = os.getenv("OH_PERMITTED_CORS_ORIGINS") or os.getenv("PERMITTED_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass
class AppServerConfig:
    persistence_dir: Path = field(default_factory=get_default_persistence_dir)
    web_url: str | None = field(default_factory=get_default_web_url)
    permitted_cors_origins: list[str] = field(default_factory=get_default_permitted_cors_origins)
    runtime: str = "process"
    tavily_api_key: str | None = field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY") or os.getenv("SEARCH_API_KEY")
    )


def config_from_env() -> AppServerConfig:
    runtime = os.getenv("MAYDAY_RUNTIME", "process").strip().lower() or "process"
    if runtime not in {"process", "local"}:
        runtime = "process"
    config = AppServerConfig(runtime=runtime)
    return config


_global_config: AppServerConfig | None = None


def get_global_config() -> AppServerConfig:
    global _global_config
    if _global_config is None:
        _global_config = config_from_env()
    return _global_config


def reset_global_config() -> None:
    global _global_config
    _global_config = None

