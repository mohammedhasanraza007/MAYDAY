"""
M.A.Y.D.A.Y Browser Tools - Playwright-based with depth limit.
"""
from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Any

from core.exceptions import BrowserDepthError
from tools.base_tool import BaseTool

logger = logging.getLogger("mayday.tools.browser")
MAX_DEPTH = 5


class BrowserTools(BaseTool):
    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Visible browser navigation and interaction"

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._depth = 0
        self._browser_label = ""

    def get_capabilities(self) -> list[str]:
        return [
            "browser_open",
            "browser_navigate",
            "browser_act",
            "browser_click",
            "browser_type",
            "browser_wait",
            "browser_wait_for_element",
            "browser_screenshot",
            "browser_get_text",
            "browser_verify",
            "browser_close",
        ]

    def execute(self, parameters: dict) -> dict:
        name = parameters.get("_tool_name", "")
        if "navigate" in name or "open" in name:
            return self._navigate(parameters)
        if "act" in name:
            return self._act(parameters)
        if "click" in name:
            return self._click(parameters)
        if "type" in name:
            return self._type(parameters)
        if "wait_for_element" in name or name.endswith("browser_wait"):
            return self._wait(parameters)
        if "screenshot" in name:
            return self._screenshot(parameters)
        if "get_text" in name:
            return self._get_text(parameters)
        if "verify" in name:
            return self._verify(parameters)
        if "close" in name:
            return self._close(parameters)
        return {"status": "error", "error": f"Unknown browser action: {name}"}

    def _ensure_browser(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright

                self._playwright = sync_playwright().start()
                self._browser = self._launch_visible_browser()
                self._page = self._browser.new_page()
                self._depth = 0
            except Exception as exc:
                self._cleanup_playwright()
                return {"status": "error", "error": f"Browser launch failed: {exc}"}
        return None

    def _launch_visible_browser(self):
        launch_options = self._launch_options()
        self._browser_label = launch_options.pop("_browser_label")
        try:
            return self._playwright.chromium.launch(**launch_options)
        except Exception as primary_error:
            if "executable_path" not in launch_options:
                raise
            logger.warning(
                "Host browser launch failed for %s; falling back to Playwright Chromium: %s",
                self._browser_label,
                primary_error,
            )
            self._browser_label = "playwright-chromium"
            return self._playwright.chromium.launch(
                headless=self._headless_requested(),
                args=self._launch_args(),
            )

    def _launch_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headless": self._headless_requested(),
            "args": self._launch_args(),
            "_browser_label": "playwright-chromium",
        }
        executable = self._preferred_browser_executable()
        if executable:
            options["executable_path"] = str(executable)
            options["_browser_label"] = executable.name
        return options

    def _headless_requested(self) -> bool:
        value = os.environ.get("MAYDAY_BROWSER_HEADLESS", "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _launch_args(self) -> list[str]:
        return [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]

    def _preferred_browser_executable(self) -> Path | None:
        explicit = os.environ.get("MAYDAY_BROWSER_EXECUTABLE", "").strip()
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

    def _navigate(self, params: dict) -> dict:
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise BrowserDepthError(f"Navigation depth exceeded {MAX_DEPTH}")
        err = self._ensure_browser()
        if err:
            return err
        url = params.get("url", "")
        try:
            self._page.goto(url, timeout=15000)
            self._page.bring_to_front()
            return {
                "status": "success",
                "url": self._page.url,
                "title": self._page.title(),
                "depth": self._depth,
                "browser": self._browser_label,
                "headless": self._headless_requested(),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _click(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        selector = params.get("selector", "")
        try:
            self._page.click(selector, timeout=5000)
            return {"status": "success", "selector": selector}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _type(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        selector = params.get("selector", "")
        text = params.get("text", "")
        try:
            self._page.fill(selector, text)
            value = self._page.input_value(selector)
            return {"status": "success", "selector": selector, "text": text, "value": value}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _wait(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        selector = params.get("selector", "")
        timeout_ms = int(params.get("timeout_ms", params.get("timeout", 10000)))
        try:
            self._page.locator(selector).first.wait_for(timeout=timeout_ms)
            return {"status": "success", "selector": selector}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _act(self, params: dict) -> dict:
        steps = params.get("steps", [])
        results: list[dict[str, Any]] = []
        for step in steps:
            action = str(step.get("action", "")).lower()
            if action in {"open", "navigate"}:
                result = self._navigate({"url": step.get("url", "")})
            elif action == "click":
                result = self._click({"selector": step.get("selector", "")})
            elif action == "type":
                result = self._type(
                    {
                        "selector": step.get("selector", ""),
                        "text": step.get("text", step.get("value", "")),
                    }
                )
            else:
                result = {"status": "error", "error": f"Unsupported browser_act step: {action}"}
            results.append({"action": action, "result": result})
            if result.get("status") != "success":
                return {"status": "error", "results": results, "error": result.get("error", "step failed")}
        return {"status": "success", "results": results}

    def _screenshot(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        path = params.get("path", "screenshot.png")
        try:
            self._page.screenshot(path=path)
            return {"status": "success", "path": path}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _get_text(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        selector = params.get("selector", "body")
        try:
            text = self._page.inner_text(selector)
            return {"status": "success", "text": text[:5000]}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _verify(self, params: dict) -> dict:
        err = self._ensure_browser()
        if err:
            return err
        condition = str(params.get("condition", "")).strip()
        try:
            haystack = f"{self._page.url}\n{self._page.title()}\n{self._page.inner_text('body')}".lower()
            words = [word for word in condition.lower().split() if len(word) > 2]
            ok = any(word in haystack for word in words) if words else bool(self._page.url)
            return {"status": "success", "condition": condition, "ok": ok, "url": self._page.url, "title": self._page.title()}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _close(self, params: dict) -> dict:
        self._cleanup_playwright()
        return {"status": "success"}

    def _cleanup_playwright(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception as exc:
                logger.warning("Browser close failed: %s", exc)
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as exc:
                logger.warning("Playwright stop failed: %s", exc)
        self._playwright = None
        self._browser = None
        self._page = None
        self._depth = 0
        self._browser_label = ""
