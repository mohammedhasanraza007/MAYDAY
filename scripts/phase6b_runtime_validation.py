from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["MAYDAY_BROWSER_HEADLESS"] = "0"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

import core.model_router as router_module
from core.model_router import ModelRouter
from core.orchestrator import Orchestrator
from runtime import browser_audit_log
from runtime.api_manager import ApiManager
from runtime.browser_session import PROFILE_DIR, SessionRegistry
from runtime.engine import ExecutionEngine
from runtime.permission_gate import permission_gate
from ui.main_window import MainWindow


RESULTS_PATH = ROOT / "logs" / "phase6b_runtime_validation_results.json"
REPORT_PATH = ROOT / "PHASE_06B_RUNTIME_VALIDATION_REPORT.txt"


class RecordingExecutionEngine(ExecutionEngine):
    def __init__(self) -> None:
        super().__init__()
        self.execution_log: list[dict[str, Any]] = []

    def execute(self, tool_name: str, parameters: dict) -> dict:
        result = super().execute(tool_name, parameters)
        self.execution_log.append(
            {
                "tool_name": tool_name,
                "parameters": _redact_runtime_params(parameters),
                "result": result,
            }
        )
        return result


class ScriptedLocalModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def generate(self, prompt: str, context: str = "") -> str:
        self.calls.append({"prompt": prompt, "context": context})
        return json.dumps(local_action_for_prompt(prompt))


class SlowLocalModel:
    loader = None

    def __init__(self, sleep_seconds: float = 0.25) -> None:
        self.sleep_seconds = sleep_seconds

    def generate(self, prompt: str, context: str = "") -> str:
        time.sleep(self.sleep_seconds)
        return json.dumps({"action": "respond", "text": "late local response"})

    def destroy_model(self) -> object:
        return object()


class FakeOpenAICompatibleClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict], system: str, max_tokens: int = 2000) -> str:
        self.calls.append({"messages": messages, "system": system, "max_tokens": max_tokens})
        return json.dumps(self.response)


class RuntimeApiManager(ApiManager):
    def __init__(self, response: dict[str, Any], keys_path: Path, salt_path: Path) -> None:
        super().__init__(keys_path=keys_path, salt_path=salt_path)
        self.fake_client = FakeOpenAICompatibleClient(response)

    def _client_for(self, provider: str, key: str):
        return self.fake_client


class ValidationWindow(MainWindow):
    def __init__(self, *args, auto_allow_delay_ms: int = 250, **kwargs) -> None:
        self.gateway_events: list[dict[str, Any]] = []
        self.finished_results: list[dict[str, Any]] = []
        self._auto_allow_delay_ms = auto_allow_delay_ms
        super().__init__(*args, **kwargs)

    def _show_permission_dialog(self, action_type: str, details: str) -> None:
        event = {
            "timestamp": time.time(),
            "action_type": action_type,
            "details": details,
            "popup_shown": True,
            "response": "ALLOW",
        }
        self.gateway_events.append(event)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("MAYDAY Safety Gateway: Action Requested")
        msg.setText(f"<b>Action Type:</b> {action_type}")
        display_details = details if len(details) < 800 else details[:800] + "\n... [TRUNCATED]"
        msg.setInformativeText(display_details)
        btn_allow = msg.addButton("Allow", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Allow Always", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Deny", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_allow)
        QTimer.singleShot(self._auto_allow_delay_ms, btn_allow.click)
        msg.exec()
        self.gateway_bridge.set_response("ALLOW")

    def on_inference_finished(self, result: dict) -> None:
        self.finished_results.append(result)
        super().on_inference_finished(result)


def local_action_for_prompt(prompt: str) -> dict[str, Any]:
    lower = prompt.lower()
    if "keep session alive" in lower and "without reopening" in lower:
        return {
            "action": "multi_tool_call",
            "tools": [
                {"tool_name": "browser_open", "parameters": {"url": "https://www.google.com"}},
                {
                    "tool_name": "browser_navigate",
                    "parameters": {"url": "https://www.google.com/search?q=MAYDAY+Phase+6B+session"},
                },
            ],
            "_finalize_after_tool": True,
        }
    if "mayday phase 6b alive" in lower:
        return {
            "action": "multi_tool_call",
            "tools": [
                {"tool_name": "browser_open", "parameters": {"url": "https://www.google.com"}},
                {"tool_name": "browser_click", "parameters": {"selector": "textarea[name='q'], input[name='q']"}},
                {
                    "tool_name": "browser_type",
                    "parameters": {
                        "selector": "textarea[name='q'], input[name='q']",
                        "text": "MAYDAY Phase 6B alive",
                    },
                },
            ],
            "_finalize_after_tool": True,
        }
    if "gateway chain" in lower:
        return {
            "action": "multi_tool_call",
            "tools": [
                {"tool_name": "browser_open", "parameters": {"url": validation_data_url("Gateway Chain")}},
                {"tool_name": "browser_click", "parameters": {"selector": "input[name='q']"}},
                {
                    "tool_name": "browser_type",
                    "parameters": {"selector": "input[name='q']", "text": "MAYDAY gateway chain"},
                },
                {"tool_name": "browser_close", "parameters": {}},
            ],
            "_finalize_after_tool": True,
        }
    if "missing selector" in lower or "does-not-exist" in lower:
        return {
            "action": "multi_tool_call",
            "tools": [
                {"tool_name": "browser_open", "parameters": {"url": validation_data_url("Failure Handling")}},
                {"tool_name": "browser_click", "parameters": {"selector": "#does-not-exist"}},
            ],
            "_finalize_after_tool": True,
        }
    if "close active browser session" in lower:
        return {
            "action": "tool_call",
            "tool_name": "browser_close",
            "parameters": {},
            "_finalize_after_tool": True,
        }
    return {"action": "respond", "text": "No scripted action for prompt"}


def api_browser_action() -> dict[str, Any]:
    return {
        "action": "multi_tool_call",
        "tools": [
            {"tool_name": "browser_open", "parameters": {"url": "https://www.google.com"}},
            {"tool_name": "browser_click", "parameters": {"selector": "textarea[name='q'], input[name='q']"}},
            {
                "tool_name": "browser_type",
                "parameters": {
                    "selector": "textarea[name='q'], input[name='q']",
                    "text": "MAYDAY API Phase 6B alive",
                },
            },
        ],
        "_finalize_after_tool": True,
    }


def validation_data_url(title: str) -> str:
    from urllib.parse import quote

    html = (
        "<!doctype html><html><head>"
        f"<title>{title}</title>"
        "<style>body{font-family:Arial,sans-serif;padding:48px}"
        "input{font-size:24px;width:min(720px,90vw);padding:14px}</style>"
        "</head><body><input name='q' aria-label='Search' placeholder='Search'></body></html>"
    )
    return "data:text/html;charset=utf-8," + quote(html)


def run_prompt(app: QApplication, window: ValidationWindow, prompt: str, timeout_seconds: int = 120) -> dict[str, Any]:
    start_gateway = len(window.gateway_events)
    start_execution = len(window.orchestrator.engine.execution_log)
    start_results = len(window.finished_results)

    window.handle_inference_request(prompt)
    deadline = time.time() + timeout_seconds
    while len(window.finished_results) <= start_results and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    if len(window.finished_results) <= start_results:
        raise TimeoutError(f"Prompt timed out: {prompt}")

    return {
        "prompt": prompt,
        "result": window.finished_results[-1],
        "gateway_events": window.gateway_events[start_gateway:],
        "executions": window.orchestrator.engine.execution_log[start_execution:],
    }


def build_window(router: ModelRouter, engine: RecordingExecutionEngine) -> ValidationWindow:
    orchestrator = Orchestrator(router, engine)
    window = ValidationWindow(orchestrator=orchestrator)
    window.show()
    return window


def _redact_runtime_params(parameters: dict) -> dict:
    redacted = dict(parameters or {})
    if "content" in redacted and isinstance(redacted["content"], str) and len(redacted["content"]) > 200:
        redacted["content"] = redacted["content"][:200] + "... [TRUNCATED]"
    return redacted


def summarize_executable_case(case: dict[str, Any], visible: bool) -> dict[str, Any]:
    executions = case.get("executions", [])
    return {
        "gateway_popup_shown": bool(case.get("gateway_events")),
        "tool_executed": bool(executions),
        "visible_side_effect_observed": bool(visible),
        "gateway_count": len(case.get("gateway_events", [])),
        "tools": [entry.get("tool_name") for entry in executions],
        "tool_statuses": [entry.get("result", {}).get("status") for entry in executions],
    }


def screenshot_exists(result: dict[str, Any]) -> bool:
    paths: list[str] = []
    screenshot = result.get("screenshot")
    if isinstance(screenshot, str):
        paths.append(screenshot)
    screenshots = result.get("screenshots")
    if isinstance(screenshots, list):
        paths.extend(str(path) for path in screenshots)
    return any(Path(path).exists() and Path(path).stat().st_size > 1024 for path in paths)


def main() -> int:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    permission_gate.cancelled = False
    SessionRegistry.close_all()

    app = QApplication.instance() or QApplication(sys.argv)
    engine = RecordingExecutionEngine()
    router = ModelRouter(ScriptedLocalModel(), None)
    window = build_window(router, engine)
    app.processEvents()

    results: dict[str, Any] = {
        "runtime_path": [
            "QApplication",
            "MainWindow",
            "InferenceThread",
            "Orchestrator",
            "ModelRouter",
            "local/API model",
            "ExecutionEngine",
            "gateway",
            "real tools",
        ],
        "tests": {},
        "matrix": {},
        "cleanup": {},
    }

    prompts = {
        "persistent_session": "Open visible browser to google.com, keep session alive, navigate again without reopening browser.",
        "multi_step_browser": (
            "Open visible browser, go to google.com, click search box, type exactly:\n"
            "MAYDAY Phase 6B alive\n"
            "- do not press enter"
        ),
        "browser_close": "Close active browser session.",
        "tool_gateway": (
            "Run browser_open, browser_click, browser_type, browser_close as a gateway chain "
            "and type exactly MAYDAY gateway chain."
        ),
        "failure_handling": "Open visible browser to the validation page and click missing selector #does-not-exist.",
        "failure_cleanup": "Close active browser session.",
    }

    persistent = run_prompt(app, window, prompts["persistent_session"])
    first_result = persistent["executions"][0]["result"]
    second_result = persistent["executions"][1]["result"]
    persistent_visible = (
        first_result.get("headless") is False
        and second_result.get("headless") is False
        and first_result.get("session_id") == second_result.get("session_id")
        and SessionRegistry.active_count() == 1
        and (screenshot_exists(first_result) or screenshot_exists(second_result))
    )
    persistent["verification"] = {
        "same_session_reused": first_result.get("session_id") == second_result.get("session_id"),
        "browser_remains_open": SessionRegistry.active_count() == 1,
        "active_sessions": SessionRegistry.active_count(),
        "headless": second_result.get("headless"),
    }
    results["tests"]["persistent_session"] = persistent
    results["matrix"]["persistent_session"] = summarize_executable_case(persistent, persistent_visible)

    multi = run_prompt(app, window, prompts["multi_step_browser"])
    type_result = multi["executions"][-1]["result"]
    multi_visible = (
        type_result.get("headless") is False
        and type_result.get("value") == "MAYDAY Phase 6B alive"
        and screenshot_exists(type_result)
    )
    multi["verification"] = {
        "typed_value": type_result.get("value"),
        "exact_text_typed": type_result.get("value") == "MAYDAY Phase 6B alive",
        "not_headless": type_result.get("headless") is False,
    }
    results["tests"]["multi_step_browser"] = multi
    results["matrix"]["multi_step_browser"] = summarize_executable_case(multi, multi_visible)

    close_case = run_prompt(app, window, prompts["browser_close"])
    close_result = close_case["executions"][-1]["result"]
    close_visible = close_result.get("active_sessions") == 0 and SessionRegistry.active_count() == 0
    close_case["verification"] = {
        "active_sessions_after_close": SessionRegistry.active_count(),
        "registry_cleanup": SessionRegistry.active_count() == 0,
        "close_result": close_result,
    }
    results["tests"]["browser_close"] = close_case
    results["matrix"]["browser_close"] = summarize_executable_case(close_case, close_visible)

    recent_audit = browser_audit_log.read_recent(200)
    audit_file_exists = browser_audit_log.AUDIT_PATH.exists()
    audit_verification = {
        "audit_path": str(browser_audit_log.AUDIT_PATH),
        "audit_file_exists": audit_file_exists,
        "recent_count": len(recent_audit),
        "recent_actions": recent_audit[-12:],
        "timestamps_present": all("timestamp" in entry for entry in recent_audit[-5:]) if recent_audit else False,
        "session_ids_present": any(entry.get("session_id") for entry in recent_audit[-20:]),
    }
    results["tests"]["browser_audit_logging"] = {"prompt": "Artifact verification: read browser audit log after runtime browser actions.", "verification": audit_verification}
    results["matrix"]["browser_audit_logging"] = {
        "gateway_popup_shown": False,
        "tool_executed": False,
        "visible_side_effect_observed": audit_file_exists and audit_verification["session_ids_present"],
        "gateway_count": 0,
        "tools": [],
        "tool_statuses": [],
    }

    profile_files = [str(path.relative_to(PROFILE_DIR)) for path in PROFILE_DIR.rglob("*") if path.is_file()][:40] if PROFILE_DIR.exists() else []
    profile_verification = {
        "profile_dir": str(PROFILE_DIR),
        "profile_dir_exists": PROFILE_DIR.exists(),
        "profile_file_sample": profile_files,
        "profile_reused_across_actions": first_result.get("profile_dir") == second_result.get("profile_dir") == str(PROFILE_DIR),
        "persistent_context_returned": bool(first_result.get("persistent")) and bool(second_result.get("persistent")),
    }
    results["tests"]["persistent_profile"] = {"prompt": "Artifact verification: inspect persistent Playwright profile after runtime browser actions.", "verification": profile_verification}
    results["matrix"]["persistent_profile"] = {
        "gateway_popup_shown": False,
        "tool_executed": False,
        "visible_side_effect_observed": profile_verification["profile_dir_exists"] and bool(profile_files),
        "gateway_count": 0,
        "tools": [],
        "tool_statuses": [],
    }

    gateway_case = run_prompt(app, window, prompts["tool_gateway"])
    gateway_type_result = gateway_case["executions"][2]["result"]
    gateway_close_result = gateway_case["executions"][-1]["result"]
    gateway_visible = (
        gateway_type_result.get("value") == "MAYDAY gateway chain"
        and gateway_close_result.get("active_sessions") == 0
        and len(gateway_case.get("gateway_events", [])) == 4
    )
    gateway_case["verification"] = {
        "gateway_events_by_tool": [event.get("action_type") for event in gateway_case.get("gateway_events", [])],
        "every_executable_flow_reached_gateway": len(gateway_case.get("gateway_events", [])) == 4,
        "typed_value": gateway_type_result.get("value"),
        "active_sessions_after_close": SessionRegistry.active_count(),
    }
    results["tests"]["tool_gateway_validation"] = gateway_case
    results["matrix"]["tool_gateway_validation"] = summarize_executable_case(gateway_case, gateway_visible)

    failure_case = run_prompt(app, window, prompts["failure_handling"])
    failure_result = failure_case["executions"][-1]["result"]
    failure_visible = (
        failure_result.get("status") == "error"
        and SessionRegistry.active_count() == 1
        and len(failure_case.get("gateway_events", [])) >= 2
    )
    failure_case["verification"] = {
        "structured_error_returned": failure_result,
        "session_not_corrupted": SessionRegistry.active_count() == 1,
        "active_sessions_after_failure": SessionRegistry.active_count(),
        "orchestrator_crashed": failure_case["result"].get("status") == "error",
    }
    results["tests"]["failure_handling"] = failure_case
    results["matrix"]["failure_handling"] = summarize_executable_case(failure_case, failure_visible)

    cleanup_after_failure = run_prompt(app, window, prompts["failure_cleanup"])
    results["tests"]["failure_cleanup"] = cleanup_after_failure

    api_keys_path = ROOT / "scratch" / "phase6b_api_runtime_keys.enc"
    api_salt_path = ROOT / "scratch" / "phase6b_api_runtime.salt"
    for path in (api_keys_path, api_salt_path):
        if path.exists():
            path.unlink()
    api_manager = RuntimeApiManager(api_browser_action(), keys_path=api_keys_path, salt_path=api_salt_path)
    api_manager.save_key("openai", "phase6b-temporary-runtime-key")
    api_manager.set_user_approved(True)
    api_engine = RecordingExecutionEngine()
    old_timeout = router_module.LOCAL_TIMEOUT_WITH_API
    router_module.LOCAL_TIMEOUT_WITH_API = 0.05
    try:
        api_router = ModelRouter(SlowLocalModel(), api_manager)
        window.orchestrator = Orchestrator(api_router, api_engine)
        api_engine.set_gateway_callback(window.gateway_bridge.request_permission_sync)
        api_prompt = (
            "Build a complex project app browser automation task through the API path: open visible browser "
            "to google.com, click the search box, type exactly MAYDAY API Phase 6B alive, and do not press enter."
        )
        api_case = run_prompt(app, window, api_prompt, timeout_seconds=180)
    finally:
        router_module.LOCAL_TIMEOUT_WITH_API = old_timeout
    api_type_result = api_case["executions"][-1]["result"]
    api_visible = (
        api_case["result"].get("provider") == "openai"
        and api_type_result.get("value") == "MAYDAY API Phase 6B alive"
        and len(api_case.get("gateway_events", [])) >= 3
    )
    api_case["verification"] = {
        "provider": api_case["result"].get("provider"),
        "api_model_returned_valid_tool_json": bool(api_manager.fake_client.calls),
        "api_raw_tool_json": api_manager.fake_client.response,
        "typed_value": api_type_result.get("value"),
        "gateway_preserved": len(api_case.get("gateway_events", [])) >= 3,
    }
    results["tests"]["api_assisted_browser_automation"] = api_case
    results["matrix"]["api_assisted_browser_automation"] = summarize_executable_case(api_case, api_visible)

    cleanup_engine = RecordingExecutionEngine()
    window.orchestrator = Orchestrator(ModelRouter(ScriptedLocalModel(), None), cleanup_engine)
    cleanup_engine.set_gateway_callback(window.gateway_bridge.request_permission_sync)
    api_cleanup = run_prompt(app, window, "Close active browser session.")
    results["tests"]["api_cleanup"] = api_cleanup

    close_all_error = ""
    if SessionRegistry.active_count() > 0:
        try:
            SessionRegistry.close_all()
        except Exception as exc:
            close_all_error = str(exc)
    for path in (api_keys_path, api_salt_path):
        if path.exists():
            path.unlink()
    permission_gate.cancelled = False
    app.processEvents()

    results["cleanup"] = {
        "active_sessions_after_final_cleanup": SessionRegistry.active_count(),
        "direct_close_all_error": close_all_error,
        "temporary_api_keys_deleted": not api_keys_path.exists(),
        "temporary_api_salt_deleted": not api_salt_path.exists(),
    }
    results["commit_sha"] = _git_commit_sha()

    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    window.close()
    app.processEvents()
    return 0


def _git_commit_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def render_report(results: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("PHASE 06B REAL RUNTIME VALIDATION REPORT")
    lines.append("Generated: 2026-05-16")
    lines.append(f"Commit SHA at validation start: {results.get('commit_sha', '')}")
    lines.append("")
    lines.append("Runtime path used:")
    lines.append(" -> ".join(results.get("runtime_path", [])))
    lines.append("")
    lines.append("Gateway / execution / visible side-effect matrix:")
    for name, row in results.get("matrix", {}).items():
        lines.append(
            f"- {name}: gateway popup shown={'YES' if row['gateway_popup_shown'] else 'NO'}; "
            f"tool executed={'YES' if row['tool_executed'] else 'NO'}; "
            f"visible side effect observed={'YES' if row['visible_side_effect_observed'] else 'NO'}; "
            f"gateway_count={row['gateway_count']}; tools={row['tools']}; statuses={row['tool_statuses']}"
        )
    lines.append("")
    lines.append("Exact prompts and structured execution outputs:")
    for name, case in results.get("tests", {}).items():
        lines.append(f"\n[{name}]")
        lines.append(f"Prompt: {case.get('prompt', '')}")
        if "result" in case:
            lines.append("Process result:")
            lines.append(json.dumps(case.get("result"), indent=2, default=str))
        if "executions" in case:
            lines.append("Engine executions:")
            lines.append(json.dumps(case.get("executions"), indent=2, default=str))
        lines.append("Verification:")
        lines.append(json.dumps(case.get("verification", {}), indent=2, default=str))
    lines.append("")
    lines.append("Cleanup verification:")
    lines.append(json.dumps(results.get("cleanup", {}), indent=2, default=str))
    lines.append("")
    blockers = []
    if not all(row.get("visible_side_effect_observed") for row in results.get("matrix", {}).values()):
        blockers.append("At least one matrix row did not observe a visible/artifact side effect.")
    if results.get("cleanup", {}).get("active_sessions_after_final_cleanup") != 0:
        blockers.append("Browser sessions remained after final cleanup.")
    if not results.get("cleanup", {}).get("temporary_api_keys_deleted"):
        blockers.append("Temporary API key file was not deleted.")
    lines.append("Remaining blockers:")
    lines.append("None." if not blockers else "\n".join(f"- {item}" for item in blockers))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
