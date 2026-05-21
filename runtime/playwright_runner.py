from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from runtime.provider_config import provider_config


_PLAYWRIGHTS: dict[int, Any] = {}


def launch_persistent(profile_dir: Path, headless: bool = False):
    from playwright.sync_api import sync_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    try:
        options: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
        }
        executable = _preferred_browser_executable()
        if executable is not None:
            options["executable_path"] = str(executable)
        context = playwright.chromium.launch_persistent_context(**options)
    except Exception:
        playwright.stop()
        raise
    _PLAYWRIGHTS[id(context)] = playwright
    return context


def close_context(context) -> None:
    playwright = _PLAYWRIGHTS.pop(id(context), None)
    try:
        context.close()
    finally:
        if playwright is not None:
            playwright.stop()


def headless_requested() -> bool:
    return provider_config.browser_headless()


def _preferred_browser_executable() -> Path | None:
    explicit = provider_config.browser_executable_path().strip()
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
    if platform.system().lower() != "windows":
        return None
    candidates = [
        os.environ.get("LOCALAPPDATA", "") + r"\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.environ.get("PROGRAMFILES", "") + r"\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate:
            path = Path(candidate)
            if path.exists():
                return path
    return None
