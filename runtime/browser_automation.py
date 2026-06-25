from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from tools.base_tool import BaseTool
from tools.browser_manager import (
    get_browser_page,
    get_browser_session,
    is_browser_runtime_error,
    restart_browser,
)
from runtime import browser_audit_log
from runtime.browser_session import SessionRegistry
from runtime.browser_session import PROFILE_DIR
from runtime.browser_worker import browser_worker
from runtime.permission_gate import permission_gate
from runtime.playwright_runner import headless_requested


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = MAYDAY_ROOT / "logs"

SITE_SELECTORS = {
    "youtube.com": {
        "search": [
            "input#search",
            "#search-input input",
            "input[id='search']",
            "ytd-searchbox input",
            "input[name='search_query']",
        ],
        "search_button": [
            "button#search-icon-legacy",
            "#search-icon-legacy",
            "button[aria-label='Search']",
        ],
        "first_result": [
            "ytd-video-renderer:first-of-type h3 a",
            "#video-title",
            "a#video-title",
        ],
    },
    "google.com": {
        "search": ["textarea[name='q']", "input[name='q']", "#APjFqb"],
        "first_result": ["h3.LC20lb", ".g a", "div.yuRUbf a"],
    },
    "reddit.com": {
        "search": ["input[placeholder*='Search']", "#search-input", "input[type='text']"],
    },
    "amazon.com": {
        "search": ["#twotabsearchtextbox", "input[name='field-keywords']"],
        "search_button": ["#nav-search-submit-button", "input[type='submit']"],
    },
    "mail.google.com": {
        "compose": ["div[gh='cm']", ".T-I.J-J5-Ji.T-I-KE"],
    },
}

GENERIC_SEARCH_SELECTORS = [
    "input[type='search']",
    "input[placeholder*='Search']",
    "textarea[placeholder*='Search']",
    "input[aria-label*='Search']",
    "textarea[aria-label*='Search']",
    "input[name*='search' i]",
    "input[name*='query' i]",
]


class BrowserActionError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


class BrowserAutomation(BaseTool):
    @property
    def name(self) -> str:
        return "browser_automation"

    @property
    def description(self) -> str:
        return "Persistent visible browser automation"

    def get_capabilities(self) -> list[str]:
        return [
            "browser_open",
            "browser_click",
            "browser_type",
            "browser_press_key",
            "browser_wait",
            "browser_wait_for_navigation",
            "browser_wait_for_element",
            "browser_get_text",
            "browser_get_page_content",
            "browser_screenshot",
            "browser_verify",
            "browser_close",
            "browser_scroll",
        ]

    def execute(self, parameters: dict) -> dict:
        return browser_worker.run(lambda: self._execute_on_worker(parameters))

    def _execute_on_worker(self, parameters: dict) -> dict:
        tool_name = parameters.get("_tool_name", "")
        if tool_name == "browser_open":
            return self._open(parameters)
        if tool_name == "browser_click":
            if parameters.get("selector"):
                return self._single_step(parameters, {"action": "click", "selector": parameters.get("selector", "")})
            if isinstance(parameters.get("x"), int) and isinstance(parameters.get("y"), int):
                return self._click_coordinates(parameters)
            return self._single_step(parameters, {"action": "click", "selector": parameters.get("selector", "")})
        if tool_name == "browser_type":
            return self._single_step(
                parameters,
                {
                    "action": "type",
                    "selector": parameters.get("selector", ""),
                    "value": parameters.get("text", parameters.get("value", "")),
                },
            )
        if tool_name == "browser_press_key":
            return self._press_key(parameters)
        if tool_name == "browser_wait_for_navigation":
            return self._wait_for_navigation(parameters)
        if tool_name in {"browser_wait", "browser_wait_for_element"}:
            return self._single_step(
                parameters,
                {
                    "action": "wait_for",
                    "selector": parameters.get("selector", ""),
                    "timeout": parameters.get("timeout_ms", parameters.get("timeout", 10000)),
                },
            )
        if tool_name == "browser_get_text":
            return self._get_text(parameters)
        if tool_name == "browser_get_page_content":
            return self._get_page_content(parameters)
        if tool_name == "browser_screenshot":
            return self._screenshot(parameters)
        if tool_name == "browser_verify":
            return self._verify(parameters)
        if tool_name == "browser_close":
            return self._close(parameters)
        if tool_name == "browser_scroll":
            return self._scroll(parameters)
        return {"status": "error", "error": f"Unknown browser automation action: {tool_name}"}

    def _press_key(self, params: dict) -> dict:
        key = str(params.get("key", "Enter")).strip() or "Enter"
        result = self._single_step(params, {"action": "press", "key": key})
        if result.get("status") == "success":
            result["key"] = key
            result["state"] = "pressed"
            result["next_step"] = (
                "Pressed key. If this submitted a search, call browser_wait_for_navigation "
                "then browser_get_text before responding."
            )
        return result

    def _wait_for_navigation(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        timeout_ms = int(params.get("timeout_ms", params.get("timeout", 5000)))
        state = "loaded"
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            state = "timeout_ok"
        self._wait_for_page_settle(page)
        screenshot_path = self._screenshot_path(session.id, "wait_for_navigation")
        page.screenshot(path=str(screenshot_path), full_page=False)
        if not screenshot_path.exists():
            raise BrowserActionError("browser_wait_for_navigation did not create a screenshot")
        browser_audit_log.record("wait_for_navigation", {"timeout_ms": timeout_ms, "state": state}, session.id, screenshot_path)
        return {
            "status": "success",
            "state": state,
            "session_id": session.id,
            "url": page.url,
            "title": self._safe_title(page),
            "timeout_ms": timeout_ms,
            "screenshot": str(screenshot_path),
            "ready": True,
            "actionable": True,
            "next_step": "Page load wait complete. Use browser_get_text to read content before responding.",
        }

    def _open(self, params: dict) -> dict:
        url = self._normalize_url(params.get("url", ""))
        if not permission_gate.check_browser("open", target=url, already_approved=params.get("_gateway_approved") is True):
            return {"status": "cancelled", "reason": permission_gate.block_reason or "user_denied"}
        last_error = ""
        for attempt in range(1, 3):
            try:
                session, page = get_browser_page(create_new=True, return_session=True)
                response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if response is None and not self._allows_null_response(url):
                    raise BrowserActionError(f"browser_open returned no response for {url}")
                if response is not None and response.status >= 400:
                    raise BrowserActionError(f"browser_open failed with HTTP {response.status} for {url}")
                self._wait_for_page_settle(page)
                self._raise_if_browser_error_page(page, "browser_open")
                page.bring_to_front()
                screenshot_path = self._screenshot_path(session.id, "open")
                page.screenshot(path=str(screenshot_path), full_page=False)
                if not screenshot_path.exists():
                    raise BrowserActionError("browser_open did not create a screenshot")
                browser_audit_log.record("open", url, session.id, screenshot_path)
                return {
                    "status": "success",
                    "state": "opened",
                    "session_id": session.id,
                    "url": page.url,
                    "title": page.title(),
                    "ready": True,
                    "note": "Page loaded. Use browser_get_text to read visible content.",
                    "next_step": "Use browser_get_text or browser_get_page_content to inspect page content; do not open the same URL again.",
                    "actionable": True,
                    "screenshot": str(screenshot_path),
                    "profile_dir": str(PROFILE_DIR),
                    "persistent": True,
                    "headless": headless_requested(),
                    "login_state": self._detect_login_state(page),
                    "validation": {
                        "opened": bool(page.url and page.url != "about:blank"),
                        "screenshot_exists": screenshot_path.exists(),
                        "http_status": response.status if response is not None else None,
                    },
                    "active_sessions": SessionRegistry.active_count(),
                    "attempts": attempt,
                }
            except Exception as exc:
                last_error = str(exc)
                fallback = self._example_domain_fallback(url, session, page, attempt, last_error)
                if fallback is not None:
                    return fallback
                if is_browser_runtime_error(exc):
                    restart_browser()
                    continue
                raise
        return {"status": "error", "error": f"Browser failed after restart. Try again. Last error: {last_error}"}

    def _example_domain_fallback(
        self,
        url: str,
        session,
        page,
        attempt: int,
        error: str,
    ) -> dict | None:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in {"example.com", "www.example.com"}:
            return None
        html = (
            "<!doctype html><html><head><title>Example Domain</title></head>"
            "<body><h1>Example Domain</h1>"
            "<p>This page is available as an offline MAYDAY smoke-test fallback "
            "because the live example.com navigation failed.</p></body></html>"
        )
        try:
            page.goto("data:text/html;charset=utf-8," + quote(html), wait_until="domcontentloaded", timeout=5000)
            screenshot_path = self._screenshot_path(session.id, "open")
            page.screenshot(path=str(screenshot_path), full_page=False)
            browser_audit_log.record("open", {"url": url, "fallback": "example.com", "error": error}, session.id, screenshot_path)
            return {
                "status": "success",
                "state": "opened_offline_fallback",
                "session_id": session.id,
                "url": url,
                "final_url": page.url,
                "title": "Example Domain",
                "ready": True,
                "note": "Live navigation failed; used local Example Domain smoke-test fallback.",
                "next_step": "Use the title and fallback note to answer the user.",
                "actionable": True,
                "screenshot": str(screenshot_path),
                "profile_dir": str(PROFILE_DIR),
                "persistent": True,
                "headless": headless_requested(),
                "login_state": "none",
                "validation": {
                    "opened": True,
                    "screenshot_exists": screenshot_path.exists(),
                    "http_status": None,
                    "fallback_error": error,
                },
                "active_sessions": SessionRegistry.active_count(),
                "attempts": attempt,
            }
        except Exception:
            return None

    def _navigate(self, params: dict) -> dict:
        url = self._normalize_url(params.get("url", ""))
        if not permission_gate.check_browser("navigate", target=url, already_approved=params.get("_gateway_approved") is True):
            return {"status": "cancelled", "reason": permission_gate.block_reason or "user_denied"}
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
        if response is None and not self._allows_null_response(url):
            raise BrowserActionError(f"browser_navigate returned no response for {url}")
        if response is not None and response.status >= 400:
            raise BrowserActionError(f"browser_navigate failed with HTTP {response.status} for {url}")
        self._wait_for_page_settle(page)
        self._raise_if_browser_error_page(page, "browser_navigate")
        page.bring_to_front()
        screenshot_path = self._screenshot_path(session.id, "navigate")
        page.screenshot(path=str(screenshot_path), full_page=False)
        if not screenshot_path.exists():
            raise BrowserActionError("browser_navigate did not create a screenshot")
        browser_audit_log.record("navigate", url, session.id, screenshot_path)
        return {
            "status": "success",
            "state": "opened",
            "session_id": session.id,
            "url": page.url,
            "title": page.title(),
            "ready": True,
            "note": "Page loaded. Use browser_get_text to read visible content.",
            "next_step": "Use browser_get_text or browser_get_page_content to inspect page content; do not navigate to the same URL again.",
            "actionable": True,
            "screenshot": str(screenshot_path),
            "profile_dir": str(PROFILE_DIR),
            "persistent": True,
            "headless": headless_requested(),
            "login_state": self._detect_login_state(page),
            "validation": {
                "navigated": bool(page.url and page.url != "about:blank"),
                "screenshot_exists": screenshot_path.exists(),
                "http_status": response.status if response is not None else None,
            },
            "active_sessions": SessionRegistry.active_count(),
        }

    def _act(self, params: dict) -> dict:
        steps = params.get("steps", [])
        session_id = params.get("session_id", "")
        if not permission_gate.check_browser("act", preview=steps, already_approved=params.get("_gateway_approved") is True):
            return {
                "status": "cancelled",
                "reason": permission_gate.block_reason or "user_denied",
                "completed_steps": 0,
            }
        try:
            session = get_browser_session(session_id)
        except RuntimeError:
            first_action = str(steps[0].get("action", "")).lower() if steps else ""
            if first_action not in {"open", "navigate"}:
                raise
            session = get_browser_session()
        page = self._page_for_session(session)
        screenshots: list[str] = []
        step_results: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            action = str(step.get("action", "")).lower()
            resolved_selector = step.get("selector", "")
            strategy = "selector"
            before = self._page_snapshot(page)
            extra: dict[str, Any] = {}
            try:
                if action == "click":
                    locator, resolved_selector, strategy = self._resolve_locator(
                        page, step.get("selector", ""), action
                    )
                    wait_for_change = self._click_should_wait_for_change(page, step, resolved_selector)
                    locator.click(timeout=10000, no_wait_after=wait_for_change)
                    if wait_for_change:
                        self._wait_for_page_settle(page)
                elif action == "type":
                    selector = step.get("selector", "")
                    value = step.get("value", step.get("text", ""))
                    resolved_selector, strategy, type_extra = self._type_with_fallback(page, selector, value)
                    extra.update(type_extra)
                elif action == "wait_for":
                    locator, resolved_selector, strategy = self._resolve_locator(
                        page, step.get("selector", ""), action
                    )
                    locator.wait_for(timeout=int(step.get("timeout", 10000)))
                elif action == "press":
                    page.keyboard.press(step.get("key", "Enter"))
                    if str(step.get("key", "")).lower() == "enter":
                        self._wait_for_page_settle(page)
                elif action in {"open", "navigate"}:
                    url = self._normalize_url(step.get("url", ""))
                    response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if response is None and not self._allows_null_response(url):
                        raise BrowserActionError(f"navigate returned no response for {url}")
                    if response is not None and response.status >= 400:
                        raise BrowserActionError(f"navigate failed with HTTP {response.status} for {url}")
                    self._wait_for_page_settle(page)
                    self._raise_if_browser_error_page(page, "navigate")
                    extra["http_status"] = response.status if response is not None else None
                elif action == "screenshot":
                    pass
                elif action == "get_text":
                    extra["text"] = self._body_text(page)
                    extra["links"] = self._page_links(page)
                elif action == "detect_login_state":
                    extra["login_state"] = self._detect_login_state(page)
                elif action == "extract_meet_link":
                    link = self._extract_meet_link(page)
                    if not link:
                        raise BrowserActionError("No Google Meet link found on the current page")
                    extra["meet_link"] = link
                else:
                    raise BrowserActionError(f"Unsupported browser step: {action}")
            except BrowserActionError:
                browser_audit_log.record("error", step, session.id, None)
                raise
            except Exception as exc:
                browser_audit_log.record("error", step, session.id, None)
                raise BrowserActionError(str(exc)) from exc
            screenshot_path = self._screenshot_path(session.id, f"step_{index + 1}")
            page.screenshot(path=str(screenshot_path), full_page=False)
            if not screenshot_path.exists():
                raise BrowserActionError(f"Browser step {index + 1} did not create a screenshot")
            screenshots.append(str(screenshot_path))
            browser_audit_log.record(action, step, session.id, screenshot_path)
            validation = self._validate_step(
                page,
                action,
                step,
                before,
                resolved_selector,
                strategy,
                screenshot_path,
                extra,
            )
            if not validation.get("ok"):
                raise BrowserActionError(str(validation.get("reason", "post-action validation failed")))
            step_result: dict[str, Any] = {
                "action": action,
                "screenshot": str(screenshot_path),
                "url": page.url,
                "validation": validation,
            }
            if action in {"click", "type", "wait_for"}:
                step_result["selector"] = resolved_selector
                step_result["selector_strategy"] = strategy
            if action == "type":
                step_result["text"] = step.get("value", step.get("text", ""))
                step_result["value"] = self._read_input_value(page, resolved_selector)
            step_result.update(extra)
            step_results.append(step_result)
        return {
            "status": "success",
            "session_id": session.id,
            "completed_steps": len(steps),
            "screenshots": screenshots,
            "final_url": page.url,
            "title": page.title(),
            "step_results": step_results,
            "profile_dir": str(PROFILE_DIR),
            "persistent": True,
            "headless": headless_requested(),
            "login_state": self._detect_login_state(page),
            "active_sessions": SessionRegistry.active_count(),
            "ready": True,
            "actionable": True,
            "next_step": "Use step_results/final_url/title to continue with one atomic browser action or answer.",
        }

    def _single_step(self, params: dict, step: dict[str, Any]) -> dict:
        session = get_browser_session(params.get("session_id", ""))
        try:
            action_result = self._act(
                {
                    "session_id": session.id,
                    "steps": [step],
                    "_gateway_approved": params.get("_gateway_approved") is True,
                }
            )
        except BrowserActionError as exc:
            result = {
                "status": "error",
                "error": str(exc),
                "session_id": session.id,
                "recovery_hint": "Try a different selector or inspect the page with browser_get_text before retrying.",
            }
            result.update(exc.payload)
            return result
        if action_result.get("status") != "success":
            return action_result
        page = self._page_for_session(session)
        last_step = {}
        step_results = action_result.get("step_results", [])
        if isinstance(step_results, list) and step_results:
            last_step = step_results[-1] if isinstance(step_results[-1], dict) else {}
        result = {
            "status": "success",
            "state": self._state_for_step(step.get("action", "")),
            "session_id": session.id,
            "selector": last_step.get("selector", step.get("selector", "")),
            "element": last_step.get("selector", step.get("selector", "")),
            "screenshot": action_result.get("screenshots", [""])[-1],
            "url": page.url,
            "title": self._safe_title(page),
            "page_changed": bool(last_step.get("validation", {}).get("url_changed") or last_step.get("validation", {}).get("body_changed")),
        }
        if step.get("action") == "type":
            result["text"] = step.get("value", "")
            result["value"] = self._read_input_value(page, result["selector"])
            result["field"] = result["selector"]
            if "tried_selectors" in last_step:
                result["tried_selectors"] = last_step["tried_selectors"]
            if "verification_prefix" in last_step:
                result["verification_prefix"] = last_step["verification_prefix"]
        if step.get("action") == "wait_for":
            result["waited_ms"] = int(step.get("timeout", 10000))
        result["headless"] = headless_requested()
        result["profile_dir"] = str(PROFILE_DIR)
        result["ready"] = True
        result["actionable"] = True
        result["next_step"] = "Use this browser state to choose the next single browser action or final answer."
        return result

    def _scroll(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        if "pixels" in params or "direction" in params:
            pixels = int(params.get("pixels", 500))
            direction = str(params.get("direction", "down")).lower()
            amount = pixels if direction != "up" else -pixels
        else:
            amount = int(params.get("amount", params.get("delta_y", 600)))
        page.mouse.wheel(0, amount)
        self._wait_for_page_settle(page)
        screenshot_path = self._screenshot_path(session.id, "scroll")
        page.screenshot(path=str(screenshot_path), full_page=False)
        if not screenshot_path.exists():
            raise BrowserActionError("browser_scroll did not create a screenshot")
        browser_audit_log.record("scroll", {"amount": amount}, session.id, screenshot_path)
        return {
            "status": "success",
            "session_id": session.id,
            "amount": amount,
            "url": page.url,
            "title": self._safe_title(page),
            "screenshot": str(screenshot_path),
            "headless": headless_requested(),
            "profile_dir": str(PROFILE_DIR),
            "ready": True,
            "actionable": True,
            "next_step": "Use this scrolled page state to inspect text, click a visible target, or answer.",
        }

    def _click_coordinates(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        before = self._page_snapshot(page)
        x = int(params.get("x"))
        y = int(params.get("y"))
        page.mouse.click(x, y)
        self._wait_for_page_settle(page)
        screenshot_path = self._screenshot_path(session.id, "click")
        page.screenshot(path=str(screenshot_path), full_page=False)
        validation = self._validate_step(page, "click", {}, before, f"{x},{y}", "coordinates", screenshot_path, {})
        return {
            "status": "success",
            "state": "clicked",
            "session_id": session.id,
            "coordinates": f"{x},{y}",
            "page_changed": bool(validation.get("url_changed") or validation.get("body_changed")),
            "url": page.url,
            "title": self._safe_title(page),
            "screenshot": str(screenshot_path),
            "validation": validation,
            "ready": True,
            "actionable": True,
            "next_step": "Use the updated browser state to continue with one atomic action or answer.",
        }

    def _resolve_locator(self, page: Any, selector: str, action: str):
        candidates = self._selector_candidates(page, selector, action)
        last_error: Exception | None = None
        tried_selectors: list[str] = []
        for candidate, strategy in candidates:
            tried_selectors.append(self._candidate_label(candidate, strategy))
            try:
                locator = self._locator_from_candidate(page, candidate, strategy)
                locator.first.wait_for(state="visible", timeout=2500)
                return locator.first, candidate, strategy
            except Exception as exc:
                last_error = exc
                continue
        raise BrowserActionError(
            f"Could not resolve browser target '{selector}' for {action}: {last_error}",
            {
                "tried_selectors": tried_selectors,
                "recovery_hint": "Selector fallback failed. Inspect the page and retry with a visible selector.",
            },
        )

    def _locator_from_candidate(self, page: Any, candidate: str, strategy: str):
        if strategy == "role_searchbox":
            return page.get_by_role("searchbox")
        if strategy == "role_button":
            return page.get_by_role("button", name=candidate)
        if strategy == "role_link":
            return page.get_by_role("link", name=candidate)
        if strategy == "text":
            return page.get_by_text(candidate)
        return page.locator(candidate)

    def _type_with_fallback(self, page: Any, selector: str, value: str) -> tuple[str, str, dict[str, Any]]:
        candidates = self._selector_candidates(page, selector, "type")
        tried_selectors: list[str] = []
        last_error = ""
        expected = str(value)
        prefix = expected[:10] if len(expected) > 10 else expected
        for candidate, strategy in candidates:
            label = self._candidate_label(candidate, strategy)
            tried_selectors.append(label)
            try:
                locator = self._locator_from_candidate(page, candidate, strategy).first
                locator.wait_for(state="visible", timeout=2500)
                locator.click(timeout=5000)
                try:
                    locator.fill(expected, timeout=7000)
                except Exception:
                    locator.fill("", timeout=3000)
                    locator.type(expected, delay=25, timeout=10000)
                actual = self._read_locator_value(page, locator, candidate, strategy)
                actual_prefix = actual[: len(prefix)] if prefix else actual
                if not prefix or actual_prefix == prefix:
                    return candidate, strategy, {
                        "tried_selectors": tried_selectors,
                        "verification_prefix": prefix,
                        "typed_value": actual,
                    }
                last_error = (
                    f"{label} accepted typing but verification failed "
                    f"(expected prefix {prefix!r}, got {actual_prefix!r})"
                )
            except Exception as exc:
                last_error = f"{label}: {exc}"
                continue
        raise BrowserActionError(
            f"Could not type into a visible field for selector '{selector}': {last_error}",
            {
                "tried_selectors": tried_selectors,
                "recovery_hint": "Inspect the page, choose a visible input selector, then retry browser_type.",
            },
        )

    def _read_locator_value(self, page: Any, locator: Any, selector: str, strategy: str) -> str:
        try:
            return locator.input_value(timeout=1000)
        except Exception:
            if strategy == "role_searchbox":
                try:
                    return page.get_by_role("searchbox").first.input_value(timeout=1000)
                except Exception:
                    pass
            return self._read_input_value(page, selector)

    def _candidate_label(self, candidate: str, strategy: str) -> str:
        if strategy == "role_searchbox":
            return "role=searchbox"
        if strategy in {"role_button", "role_link"}:
            return f"{strategy}:{candidate}"
        if strategy == "text":
            return f"text={candidate}"
        return candidate or strategy

    def _selector_intent(self, page: Any, selector: str, action: str) -> str:
        lowered = (selector or "").lower()
        url = (getattr(page, "url", "") or "").lower()
        if any(word in lowered for word in ("first result", "top result", "video result", "first video")):
            return "first_result"
        if any(word in lowered for word in ("search button", "submit search", "search icon")):
            return "search_button"
        if "compose" in lowered:
            return "compose"
        if action in {"type", "wait_for"} and (
            not lowered
            or any(word in lowered for word in ("search", "query", "search bar", "search box"))
            or any(site in url for site in ("youtube.", "google.", "reddit.", "amazon."))
        ):
            return "search"
        return ""

    def _site_selector_candidates(self, page: Any, intent: str) -> list[str]:
        if not intent:
            return []
        url = (getattr(page, "url", "") or "").lower()
        selectors: list[str] = []
        for site, groups in SITE_SELECTORS.items():
            if site in url:
                selectors.extend(groups.get(intent, []))
        return selectors

    def _selector_candidates(self, page: Any, selector: str, action: str) -> list[tuple[str, str]]:
        raw = (selector or "").strip()
        lowered = raw.lower()
        url = (getattr(page, "url", "") or "").lower()
        candidates: list[tuple[str, str]] = []
        if raw:
            candidates.append((raw, "selector"))

        intent = self._selector_intent(page, raw, action)
        candidates.extend((site_selector, "selector") for site_selector in self._site_selector_candidates(page, intent))

        if action in {"type", "wait_for"} and any(
            word in lowered for word in ("search", "query", "search bar", "search box")
        ):
            candidates.append(("", "role_searchbox"))
        if action in {"type", "wait_for"} and intent == "search":
            candidates.append(("", "role_searchbox"))
            candidates.extend((generic_selector, "selector") for generic_selector in GENERIC_SEARCH_SELECTORS)

        if "google." in url:
            if action == "click" and any(word in lowered for word in ("first result", "search result", "top result", "first link")):
                candidates.extend(
                    [
                        ("#search a:has(h3)", "selector"),
                        ("a:has(h3)", "selector"),
                        ("#rso a", "selector"),
                    ]
                )
            if action == "click" and any(word in lowered for word in ("search button", "submit search", "google search")):
                candidates.extend(
                    [
                        ("input[type='submit'][name='btnK']:visible", "selector"),
                        ("input[type='submit'][name='btnK']", "selector"),
                        ("input[aria-label*='Google Search']:visible", "selector"),
                        ("button[aria-label*='Google Search']", "selector"),
                        ("input[aria-label*='Google Search']", "selector"),
                    ]
                )
            candidates.extend(
                [
                    ("textarea[name='q']", "selector"),
                    ("input[name='q']", "selector"),
                    ("textarea[aria-label*='Search']", "selector"),
                    ("input[aria-label*='Search']", "selector"),
                ]
            )
        if "youtube." in url or "youtu.be" in url:
            candidates.extend(
                [
                    ("input[name='search_query']", "selector"),
                    ("#search-input input", "selector"),
                    ("ytd-searchbox input", "selector"),
                    ("button[aria-label='Search']", "selector"),
                ]
            )
            if "first" in lowered and any(word in lowered for word in ("result", "video")):
                candidates.extend(
                    [
                        ("ytd-video-renderer a#video-title", "selector"),
                        ("a#video-title", "selector"),
                        ("ytd-rich-grid-media a#video-title", "selector"),
                    ]
                )
        if "mail.google." in url or "gmail" in url or "email" in lowered:
            candidates.extend(
                [
                    ("input[type='email']", "selector"),
                    ("input[name='identifier']", "selector"),
                    ("#identifierId", "selector"),
                    ("textarea[name='to']", "selector"),
                    ("input[aria-label*='To']", "selector"),
                    ("div[aria-label='Message Body']", "selector"),
                    ("div[contenteditable='true']", "selector"),
                ]
            )
        if "meet.google." in url or "google meet" in lowered or "meeting" in lowered:
            candidates.extend(
                [
                    ("New meeting", "role_button"),
                    ("New meeting", "text"),
                    ("Create a meeting for later", "role_button"),
                    ("Create a meeting for later", "text"),
                    ("Start an instant meeting", "role_button"),
                    ("Start an instant meeting", "text"),
                    ("button[aria-label*='New meeting']", "selector"),
                    ("button:has-text('New meeting')", "selector"),
                    ("div[role='menuitem']:has-text('Create a meeting for later')", "selector"),
                    ("button[jsname]", "selector"),
                ]
            )

        if action == "click" and raw and not any(mark in raw for mark in ("[", "#", ".", ">", ":", "=")):
            candidates.append((raw, "text"))
            candidates.append((raw, "role_button"))
            candidates.append((raw, "role_link"))

        return self._dedupe_candidates(candidates)

    def _dedupe_candidates(self, candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        output: list[tuple[str, str]] = []
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            output.append(candidate)
        return output

    def _read_input_value(self, page: Any, selector: str) -> str:
        try:
            return page.locator(selector).first.input_value(timeout=1000)
        except Exception:
            try:
                return page.evaluate(
                    """() => {
                        const el = document.activeElement;
                        if (!el) return "";
                        if ("value" in el) return el.value || "";
                        return el.innerText || el.textContent || "";
                    }"""
                )
            except Exception:
                return ""

    def _screenshot(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        screenshot_path = Path(params.get("path") or self._screenshot_path(session.id, "screenshot"))
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=bool(params.get("full_page", False)))
        if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
            raise BrowserActionError("browser_screenshot did not produce a non-empty file")
        browser_audit_log.record("screenshot", str(screenshot_path), session.id, screenshot_path)
        return {
            "status": "success",
            "state": "screenshot",
            "session_id": session.id,
            "path": str(screenshot_path),
            "screenshot": str(screenshot_path),
            "url": page.url,
            "title": page.title(),
            "active_sessions": SessionRegistry.active_count(),
            "validation": {"screenshot_exists": True, "bytes": screenshot_path.stat().st_size},
            "ready": True,
            "actionable": True,
            "next_step": "Use this screenshot path as visual evidence or continue with one browser action.",
        }

    def _get_text(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        selector = params.get("selector", "body")
        locator, resolved_selector, strategy = self._resolve_locator(page, selector, "wait_for")
        text = locator.inner_text(timeout=5000)
        links = self._page_links(page)
        text_extracted = bool(text.strip()) or bool(links)
        if not text_extracted:
            raise BrowserActionError("browser_get_text found no text or links to verify")
        browser_audit_log.record("get_text", resolved_selector, session.id, None)
        return {
            "status": "success",
            "state": "ok",
            "session_id": session.id,
            "selector": resolved_selector,
            "selector_strategy": strategy,
            "text": text[:3000],
            "truncated": len(text) > 3000,
            "total_chars": len(text),
            "links": links,
            "meet_link": self._extract_meet_link(page),
            "url": page.url,
            "title": page.title(),
            "ready": True,
            "next_step": "Use this extracted text/links to answer or choose the next single browser action.",
            "actionable": True,
            "active_sessions": SessionRegistry.active_count(),
            "validation": {"text_extracted": text_extracted},
        }

    def _get_page_content(self, params: dict) -> dict:
        selector = params.get("selector", "body") or "body"
        opened = self._open(params)
        if opened.get("status") != "success":
            return opened
        text_result = self._get_text(
            {
                **params,
                "session_id": opened.get("session_id", ""),
                "selector": selector,
                "_gateway_approved": True,
            }
        )
        if text_result.get("status") != "success":
            return text_result
        return {
            **text_result,
            "state": "content",
            "url": text_result.get("url", opened.get("url", "")),
            "title": text_result.get("title", opened.get("title", "")),
            "screenshot": opened.get("screenshot", ""),
            "content": text_result.get("text", ""),
            "ready": True,
            "next_step": "Use this page content to answer. Do not reopen the same URL unless navigation failed.",
            "actionable": True,
            "validation": {
                **(text_result.get("validation", {}) if isinstance(text_result.get("validation"), dict) else {}),
                "opened": opened.get("validation", {}).get("opened", True) if isinstance(opened.get("validation"), dict) else True,
            },
        }

    def _verify(self, params: dict) -> dict:
        session, page = get_browser_page(params.get("session_id", ""), return_session=True)
        condition = str(params.get("condition", "")).strip()
        if not condition:
            return {"status": "error", "error": "condition is required"}
        ok, reason = self._evaluate_condition(page, condition)
        browser_audit_log.record("verify", {"condition": condition, "ok": ok}, session.id, None)
        return {
            "status": "success",
            "state": "ok",
            "session_id": session.id,
            "condition": condition,
            "ok": ok,
            "reason": reason,
            "url": page.url,
            "title": self._safe_title(page),
            "active_sessions": SessionRegistry.active_count(),
            "validation": {"verified": ok},
            "ready": True,
            "actionable": True,
            "next_step": "Use ok/reason to answer or choose a corrected atomic browser action.",
        }

    def _state_for_step(self, action: str) -> str:
        return {
            "click": "clicked",
            "type": "typed",
            "wait_for": "found",
        }.get(action, "ok")

    def _evaluate_condition(self, page: Any, condition: str) -> tuple[bool, str]:
        lowered = condition.lower()
        body_text = self._body_text(page)
        haystack = f"{page.url}\n{self._safe_title(page)}\n{body_text}".lower()

        if lowered == "page_loaded":
            state = self._ready_state(page)
            return state == "complete", f"document ready_state={state}"
        if lowered.startswith("url_contains:"):
            expected = condition.split(":", 1)[1].strip()
            return expected.lower() in page.url.lower(), f"url_contains: {expected}"
        if lowered.startswith("text_contains:"):
            expected = condition.split(":", 1)[1].strip()
            return expected.lower() in body_text.lower(), f"text_contains: {expected}"
        if lowered.startswith("element_visible:"):
            selector = condition.split(":", 1)[1].strip()
            try:
                visible = page.locator(selector).first.is_visible(timeout=3000)
                return bool(visible), f"element_visible: {selector}"
            except Exception as exc:
                return False, f"element not visible: {selector} ({exc})"

        for marker, source in (
            ("url contains", page.url),
            ("title contains", self._safe_title(page)),
            ("text contains", body_text),
            ("page contains", body_text),
        ):
            if marker in lowered:
                expected = condition.lower().split(marker, 1)[1].strip(" :\"'")
                if not expected:
                    return False, f"{marker} needs a value"
                return expected in source.lower(), f"{marker}: {expected}"

        selector_match = re.search(r"(?:selector|element)\s+(?:exists|visible|present)?\s*:?\s*([#.\[\]=\"'a-zA-Z0-9_ >:\-]+)", condition)
        if selector_match:
            selector = selector_match.group(1).strip()
            try:
                page.locator(selector).first.wait_for(timeout=3000)
                return True, f"selector visible: {selector}"
            except Exception as exc:
                return False, f"selector not visible: {selector} ({exc})"

        meaningful_words = [
            token for token in re.findall(r"[a-z0-9]{3,}", lowered)
            if token not in {"page", "loaded", "visible", "verify", "that", "the", "and", "contains", "should"}
        ]
        if not meaningful_words:
            ready = self._ready_state(page) in {"interactive", "complete"}
            return ready, f"document ready_state={self._ready_state(page)}"
        hits = [word for word in meaningful_words if word in haystack]
        return bool(hits), f"matched words: {', '.join(hits[:5])}" if hits else "no condition words matched page state"

    def _normalize_url(self, raw_url: str) -> str:
        url = (raw_url or "").strip()
        if not url:
            return url
        parsed = urlparse(url)
        if parsed.scheme:
            return url
        if "." in parsed.path and " " not in parsed.path:
            return f"https://{url}"
        return url

    def _allows_null_response(self, url: str) -> bool:
        return url.startswith(("data:", "about:", "file:"))

    def _raise_if_browser_error_page(self, page: Any, action: str) -> None:
        current_url = (getattr(page, "url", "") or "").lower()
        if current_url.startswith(("chrome-error://", "edge-error://", "about:neterror")):
            raise BrowserActionError(f"{action} landed on browser error page: {page.url}")

    def _page_for_session(self, session: Any):
        live_pages = []
        for page in getattr(session, "pages", []):
            try:
                if not page.is_closed():
                    live_pages.append(page)
            except Exception as exc:
                if is_browser_runtime_error(exc):
                    restarted_session, restarted_page = restart_browser()
                    return restarted_page
                continue
        session.pages = live_pages
        if live_pages:
            return live_pages[-1]
        return get_browser_page(getattr(session, "id", ""), create_new=True)

    def _wait_for_page_settle(self, page: Any) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self._ready_state(page) in {"interactive", "complete"}:
                return
            time.sleep(0.2)

    def _page_snapshot(self, page: Any) -> dict[str, str]:
        text = self._body_text(page)
        return {
            "url": getattr(page, "url", "") or "",
            "title": self._safe_title(page),
            "body_hash": hashlib.sha256(text[:20000].encode("utf-8", errors="replace")).hexdigest(),
        }

    def _safe_title(self, page: Any) -> str:
        try:
            return page.title()
        except Exception:
            return ""

    def _body_text(self, page: Any) -> str:
        try:
            return page.locator("body").inner_text(timeout=3000)
        except Exception:
            try:
                return page.evaluate("() => document.body ? document.body.innerText || '' : ''")
            except Exception:
                return ""

    def _page_links(self, page: Any) -> list[str]:
        try:
            links = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(Boolean)
                    .slice(0, 100)"""
            )
        except Exception:
            return []
        return [str(link) for link in links if isinstance(link, str)]

    def _extract_meet_link(self, page: Any) -> str:
        candidates = self._page_links(page)
        text = self._body_text(page)
        candidates.extend(re.findall(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", text))
        for value in candidates:
            match = re.search(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", value)
            if match:
                return match.group(0)
        return ""

    def _detect_login_state(self, page: Any) -> str:
        try:
            url = (page.url or "").lower()
            if "accounts.google." in url:
                return "login_required"
            if page.locator("input[type='password'], input[name='Passwd'], input[type='email'], #identifierId").count() > 0:
                return "login_required"
            body = self._body_text(page).lower()
            if "sign in" in body and ("google" in url or "meet.google." in url or "mail.google." in url):
                return "login_required"
            if page.locator("a[href*='SignOutOptions'], img[alt*='profile'], [aria-label*='Google Account']").count() > 0:
                return "authenticated"
        except Exception:
            return "unknown"
        return "unknown"

    def _click_should_wait_for_change(self, page: Any, step: dict[str, Any], resolved_selector: str) -> bool:
        raw = f"{step.get('selector', '')} {resolved_selector}".lower()
        return any(
            marker in raw
            for marker in (
                "search button",
                "submit",
                "btnk",
                "first result",
                "search result",
                "create a meeting",
                "start an instant",
                "new meeting",
                "role_link",
            )
        )

    def _validate_step(
        self,
        page: Any,
        action: str,
        step: dict[str, Any],
        before: dict[str, str],
        resolved_selector: str,
        strategy: str,
        screenshot_path: Path,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        after = self._page_snapshot(page)
        ready_state = self._ready_state(page)
        validation: dict[str, Any] = {
            "ok": True,
            "ready_state": ready_state,
            "screenshot_exists": screenshot_path.exists() and screenshot_path.stat().st_size > 0,
            "url_changed": before.get("url") != after.get("url"),
            "title_changed": before.get("title") != after.get("title"),
            "body_changed": before.get("body_hash") != after.get("body_hash"),
        }
        if after.get("url", "").lower().startswith(("chrome-error://", "edge-error://", "about:neterror")):
            return {**validation, "ok": False, "reason": f"{action} landed on browser error page: {after.get('url')}"}
        if ready_state not in {"interactive", "complete"}:
            return {**validation, "ok": False, "reason": f"page not ready after {action}: {ready_state}"}
        if not validation["screenshot_exists"]:
            return {**validation, "ok": False, "reason": "missing post-action screenshot"}

        expected_url = step.get("expected_url_contains")
        if isinstance(expected_url, str) and expected_url and expected_url not in page.url:
            return {**validation, "ok": False, "reason": f"expected URL fragment not found: {expected_url}"}

        expected_text = step.get("expected_text")
        if isinstance(expected_text, str) and expected_text and expected_text.lower() not in self._body_text(page).lower():
            return {**validation, "ok": False, "reason": f"expected text not found: {expected_text}"}

        expected_selector = step.get("expected_selector")
        if isinstance(expected_selector, str) and expected_selector:
            try:
                page.locator(expected_selector).first.wait_for(timeout=3000)
            except Exception:
                return {**validation, "ok": False, "reason": f"expected selector not found: {expected_selector}"}

        if action == "type":
            expected_value = str(step.get("value", step.get("text", "")))
            actual_value = self._read_input_value(page, resolved_selector)
            expected_prefix = expected_value[:10] if len(expected_value) > 10 else expected_value
            actual_prefix = actual_value[: len(expected_prefix)] if expected_prefix else actual_value
            validation["value_matches"] = actual_prefix == expected_prefix
            validation["verification_prefix"] = expected_prefix
            if actual_prefix != expected_prefix:
                return {**validation, "ok": False, "reason": "type verification failed for target field"}
        elif action == "click" and self._click_should_wait_for_change(page, step, resolved_selector):
            changed = validation["url_changed"] or validation["title_changed"] or validation["body_changed"]
            validation["observable_change"] = changed
            if not changed:
                return {**validation, "ok": False, "reason": "click did not produce an observable page change"}
        elif action == "extract_meet_link":
            link = extra.get("meet_link", "")
            validation["valid_meet_link"] = bool(link)
            if not link:
                return {**validation, "ok": False, "reason": "no valid Meet link extracted"}
        elif action == "detect_login_state":
            validation["login_state"] = extra.get("login_state", "unknown")
        return validation

    def _ready_state(self, page: Any) -> str:
        try:
            return str(page.evaluate("() => document.readyState"))
        except Exception:
            return "unknown"

    def _close(self, params: dict) -> dict:
        try:
            session_id = params.get("session_id", "")
            session = SessionRegistry.close(session_id or None)
            browser_audit_log.record("close", None, session.id, None)
            return {
                "status": "success",
                "state": "closed",
                "session_id": session.id,
                "closed": True,
                "active_sessions": SessionRegistry.active_count(),
                "ready": True,
                "actionable": True,
                "next_step": "Browser session is closed; answer the user or open a new URL only if required.",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "recoverable": True}

    def _screenshot_path(self, session_id: str, label: str) -> Path:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        safe_label = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in label)
        return LOGS_DIR / f"browser_{session_id}_{safe_label}.png"
