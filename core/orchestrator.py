"""
M.A.Y.D.A.Y Orchestrator — Phase 04 Agentic Loop
=================================================
R11 intent routing + R10 guard for executable intents.
"""
from __future__ import annotations

import gc
import json
import logging
from typing import Any, Callable

from core.exceptions import (
    HardRuleViolationError,
    RecursiveCallError,
    SchemaValidationError,
    SessionLimitError,
)
from core.intent_router import classify, is_executable_intent, required_tools_for
from core.json_parser import parse_model_output, safe_response_object
from core.session import SessionManager
from core.tool_recovery import FINALIZE_AFTER_TOOL, recover_action_from_prompt
from core.context_compressor import ContextCompressor
from runtime.task_graph import TaskGraphExecutor

logger = logging.getLogger("mayday.orchestrator")

MAX_STEPS = 50
MAX_INFERENCE_DEPTH = 1
MAX_IDENTICAL_ACTION_REPEATS = 2
ChatOnlyOutputError = HardRuleViolationError


import threading

class Orchestrator:
    def __init__(self, router: Any, engine: Any, session: SessionManager | None = None):
        self.router = router
        self.engine = engine
        self.session = session or SessionManager()
        self._inference_depth = 0
        self._cancelled = False
        self._on_step: Callable | None = None
        self._on_tool_call: Callable | None = None
        self._on_response: Callable | None = None
        self._last_provider = "unknown"
        self._tools_used: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def set_callbacks(
        self,
        on_step: Callable | None = None,
        on_tool_call: Callable | None = None,
        on_response: Callable | None = None,
    ) -> None:
        self._on_step = on_step
        self._on_tool_call = on_tool_call
        self._on_response = on_response

    def cancel(self) -> None:
        self._cancelled = True

    def run(self, user_prompt: str) -> str:
        self._cancelled = False
        self._tools_used = []
        intent = self._build_validated_intent(user_prompt)
        executable = intent["executable"]
        required = intent["required_tools"]
        system_prompt = self._system_prompt(intent)
        last_action_fingerprint = ""
        repeated_action_count = 0
        last_tool_result: dict[str, Any] | None = None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.session.add_to_history("user", user_prompt)

        for step in range(MAX_STEPS):
            if self._cancelled:
                return "[Cancelled by user]"

            import threading
            logger.info("LOOP-STEP %d: thread=%s, depth=%d", step + 1, threading.current_thread().name, self._inference_depth)

            if self._inference_depth > MAX_INFERENCE_DEPTH:
                raise RecursiveCallError(f"Model attempted recursive self-call (depth={self._inference_depth} > {MAX_INFERENCE_DEPTH})")

            if self._on_step:
                self._on_step(step + 1, "Running agent step")

            self._inference_depth += 1
            try:
                # E101: Compress messages to stay within token context window
                compressed_messages = ContextCompressor.compress_messages(messages)
                raw, provider = self._route(compressed_messages, user_prompt)
                self._last_provider = provider
            finally:
                self._inference_depth -= 1

            action = parse_model_output(raw)
            from core.composite_translator import CompositeActionTranslator
            enforce_micro = (provider in ("local", "local_fallback"))
            action = CompositeActionTranslator.translate(action, enforce_microstep=enforce_micro)
            action_name = action.get("action")
            if executable:
                recovered = recover_action_from_prompt(user_prompt, intent, action)
                if recovered is not None:
                    action = recovered
                    action_name = action.get("action")

            if executable and step == 0 and action_name == "respond":
                raise ChatOnlyOutputError(
                    "Executable intent detected but model returned respond — required tools were: "
                    + ", ".join(required)
                )

            if action_name == "respond":
                return self._build_final_response(action)

            if not self._action_allowed_for_intent(action, intent):
                return self._build_final_response(
                    {
                        "action": "respond",
                        "text": "Execution was blocked because the request intent was not validated for tool use.",
                    }
                )

            action_fingerprint = self._action_fingerprint(action)
            if action_fingerprint == last_action_fingerprint:
                repeated_action_count += 1
            else:
                repeated_action_count = 1
                last_action_fingerprint = action_fingerprint

            if repeated_action_count >= MAX_IDENTICAL_ACTION_REPEATS and not self._allowed_recovery_repeat(
                action, last_tool_result, repeated_action_count
            ):
                return self._build_final_response(
                    {
                        "action": "respond",
                        "text": (
                            "Execution stopped after repeated identical actions "
                            "to prevent a routing loop."
                        ),
                    }
                )

            result = self._execute_action(action, intent)
            last_tool_result = result
            self._assert_real_execution(result)
            if result.get("status") == "cancelled":
                return self._build_final_response(
                    {
                        "action": "respond",
                        "text": (
                            "Execution stopped because the user denied permission. "
                            "That denial is now treated as a terminal blocked state until permissions are explicitly reset."
                        ),
                    }
                )
            if self._should_return_tool_evidence(action, result):
                return self._build_tool_evidence_response(action, result)

            # E101/E106: Compress assistant output and tool results to maintain token discipline
            compressed_raw = ContextCompressor.compress_assistant_output(raw)
            compressed_result = ContextCompressor.compress_tool_result(result)
            
            messages.append({"role": "assistant", "content": compressed_raw})
            messages.append({"role": "tool", "content": compressed_result})
            
            self.session.add_to_history("tool", compressed_result)

        raise SessionLimitError(f"Session exceeded {self.session.max_steps} agent loop steps")

    def process_prompt(self, user_prompt: str) -> dict[str, Any]:
        with self._lock:
            try:
                text = self.run(user_prompt)
                if self._on_response:
                    self._on_response(text, self._last_provider)
                self.session.add_to_history("assistant", text)
                return {
                    "response": text,
                    "provider": self._last_provider,
                    "steps": self.session.step_count,
                    "tools_used": list(self._tools_used),
                    "continuation_rounds": self.session.step_count,
                }
            except Exception as exc:
                self._emergency_cleanup()
                safe = safe_response_object(str(exc))
                text = safe.get("text", "")
                self.session.add_to_history("assistant", text)
                return {
                    "response": text,
                    "provider": self._last_provider,
                    "steps": self.session.step_count,
                    "tools_used": list(self._tools_used),
                    "continuation_rounds": self.session.step_count,
                    "status": "error",
                    "error": str(exc),
                }
            finally:
                gc.collect()

    def _route(self, messages: list[dict[str, str]], user_prompt: str) -> tuple[str, str]:
        try:
            result = self.router.route(messages)
        except TypeError:
            context = self.session.get_context_string()
            result = self.router.route(user_prompt, context)

        if isinstance(result, tuple) and len(result) == 2:
            return str(result[0]), str(result[1])
        if isinstance(result, str):
            return result, "unknown"
        raise SchemaValidationError("Router returned unsupported payload")

    def _execute_action(self, action: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        action_name = action.get("action", "")

        if action_name == "tool_call":
            tool_name = action.get("tool_name", "")
            params = action.get("parameters", {})
            result = self._engine_execute(tool_name, params, intent)
            self._tools_used.append({"tool": tool_name, "status": result.get("status", "unknown")})
            return result

        if action_name == "multi_tool_call":
            def execute_node(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
                tool_result = self._engine_execute(tool_name, params, intent)
                self._tools_used.append(
                    {"tool": tool_name, "status": tool_result.get("status", "unknown")}
                )
                return tool_result

            graph = TaskGraphExecutor(action.get("tools", []))
            return graph.run(execute_node)

        payload = dict(action)
        payload.pop("action", None)
        result = self._engine_execute(action_name, payload, intent)
        self._tools_used.append({"tool": action_name, "status": result.get("status", "unknown")})
        return result

    def _engine_execute(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        if self._on_tool_call:
            self._on_tool_call(tool_name, parameters)

        safe_params = dict(parameters or {})
        safe_params.setdefault("_sandbox_mode", False)
        safe_params.setdefault("_intent_family", intent["family"])

        try:
            if hasattr(self.engine, "execute"):
                result = self.engine.execute(tool_name, safe_params)
            elif hasattr(self.engine, "execute_tool"):
                result = self.engine.execute_tool(tool_name, safe_params)
            else:
                return {"status": "error", "error": "Engine has no execution entrypoint"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        if isinstance(result, dict):
            return result
        return {"status": "error", "error": f"Engine returned non-dict result: {type(result).__name__}"}

    def _assert_real_execution(self, result: dict[str, Any]) -> None:
        checker = getattr(self.engine, "assert_real_execution", None)
        if callable(checker):
            checker(result)

    def _system_prompt(self, intent: dict[str, Any] | None = None) -> str:
        if intent is not None and not intent.get("executable", False):
            return "You are M.A.Y.D.A.Y, a professional AI coding assistant. Reply concisely."
        getter = getattr(self.engine, "get_system_prompt", None)
        if callable(getter):
            value = getter()
            if isinstance(value, str):
                return value
        return ""

    def _emergency_cleanup(self) -> None:
        try:
            if hasattr(self.router, "inference") and hasattr(self.router.inference, "loader"):
                self.router.inference.loader.destroy_model()
        except Exception as exc:  # pragma: no cover - best effort
            logger.error("Emergency cleanup failed: %s", exc)
        gc.collect()
        gc.collect()

    def _build_validated_intent(self, user_prompt: str) -> dict[str, Any]:
        family = classify(user_prompt)
        required = required_tools_for(user_prompt)
        executable = is_executable_intent(user_prompt)
        return {
            "raw_input": user_prompt,
            "family": family or "CHAT",
            "required_tools": required,
            "executable": executable,
        }

    def _action_allowed_for_intent(self, action: dict[str, Any], intent: dict[str, Any]) -> bool:
        action_name = action.get("action", "")
        if action_name == "respond":
            return True

        if not intent["executable"]:
            return False

        family = intent["family"]
        allowed_actions_by_family: dict[str, set[str]] = {
            "WEB_ACCESS": {"tool_call", "multi_tool_call", "web_search", "web_fetch"},
            "PROJECT_CREATION": {
                "tool_call",
                "multi_tool_call",
                "scaffold",
                "scaffold_engine",
                "file_write",
                "file_read",
                "shell_run",
                "powershell_run",
            },
            "EXECUTION": {
                "tool_call",
                "multi_tool_call",
                "shell_run",
                "powershell_run",
                "server_launch",
                "scaffold",
                "scaffold_engine",
                "file_write",
                "file_read",
            },
            "AUTOMATION": {
                "tool_call",
                "multi_tool_call",
                "browser_open",
                "browser_navigate",
                "browser_click",
                "browser_type",
                "browser_act",
                "browser_screenshot",
                "browser_get_text",
                "browser_close",
            },
            "FILE_OPS": {"tool_call", "multi_tool_call", "file_read", "file_write"},
        }
        allowed = allowed_actions_by_family.get(family)
        if not allowed or action_name not in allowed:
            return False

        if action_name == "tool_call":
            return self._tool_allowed_for_intent(action.get("tool_name", ""), family)

        if action_name == "multi_tool_call":
            for tool_entry in action.get("tools", []):
                tool_name = tool_entry.get("tool_name", "")
                if not self._tool_allowed_for_intent(tool_name, family):
                    return False
        return True

    def _tool_allowed_for_intent(self, tool_name: str, family: str) -> bool:
        base = (tool_name or "").split(".", 1)[0].split("_", 1)[0].lower()
        allowed_tool_bases_by_family: dict[str, set[str]] = {
            "WEB_ACCESS": {"web", "page", "browser", "playwright"},
            "PROJECT_CREATION": {"scaffold", "file", "project", "shell", "powershell", "browser", "playwright", "server"},
            "EXECUTION": {"shell", "server", "system", "powershell", "scaffold", "file", "project", "browser", "playwright"},
            "AUTOMATION": {"browser", "playwright", "shell", "powershell", "file", "web", "page"},
            "FILE_OPS": {"file", "shell", "powershell"},
        }
        allowed = allowed_tool_bases_by_family.get(family, set())
        return base in allowed

    def _action_fingerprint(self, action: dict[str, Any]) -> str:
        try:
            return json.dumps(action, sort_keys=True, default=str)
        except Exception:
            return str(action)

    def _allowed_recovery_repeat(
        self,
        action: dict[str, Any],
        last_result: dict[str, Any] | None,
        repeat_count: int,
    ) -> bool:
        if repeat_count > 2:
            return False
        if not isinstance(last_result, dict) or last_result.get("status") != "error":
            return False
        error_text = str(last_result.get("error", "")).lower()
        if any(marker in error_text for marker in ("denied", "permission", "could not resolve", "not found", "safety")):
            return False
        action_name = action.get("action", "")
        tool_names: list[str] = []
        if action_name == "tool_call":
            tool_names.append(str(action.get("tool_name", "")))
        elif action_name == "multi_tool_call":
            for entry in action.get("tools", []):
                if isinstance(entry, dict):
                    tool_names.append(str(entry.get("tool_name", "")))
        else:
            tool_names.append(str(action_name))
        transient = any(
            marker in error_text
            for marker in ("timeout", "timed out", "closed", "crash", "net::err", "navigation")
        )
        return transient and any(name.startswith(("browser_", "playwright_")) for name in tool_names)

    def _build_final_response(self, action: dict[str, Any]) -> str:
        text = action.get("text", action.get("response", ""))
        if not isinstance(text, str):
            text = str(text)
        return text

    def _should_return_tool_evidence(self, action: dict[str, Any], result: dict[str, Any]) -> bool:
        if action.get(FINALIZE_AFTER_TOOL) is True:
            return True
        return False

    def _build_tool_evidence_response(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        tool_name = action.get("tool_name", action.get("action", "tool"))
        status = result.get("status", "unknown")
        if status != "success":
            if action.get("action") == "multi_tool_call":
                return f"multi_tool_call failed: {json.dumps(result, default=str)}"
            error = result.get("error", "tool execution failed")
            return f"{tool_name} failed: {error}"

        if tool_name == "file_write":
            return (
                "file_write executed: "
                f"path={result.get('path', '')}; bytes_written={result.get('bytes_written', '')}"
            )
        if tool_name in {"shell_run", "powershell_run"}:
            stdout = str(result.get("stdout", "")).strip()
            stderr = str(result.get("stderr", "")).strip()
            return (
                "shell_run executed: "
                f"returncode={result.get('returncode', '')}; stdout={stdout}; stderr={stderr}"
            )
        if tool_name == "web_search":
            results = result.get("results", [])
            first = results[0] if isinstance(results, list) and results else {}
            return (
                "web_search executed: "
                f"count={result.get('count', 0)}; title={first.get('title', '')}; url={first.get('url', '')}"
            )
        if tool_name == "web_fetch":
            return (
                "web_fetch executed: "
                f"status_code={result.get('status_code', '')}; title={result.get('title', '')}; "
                f"url={result.get('url', '')}"
            )
        if tool_name == "browser_open":
            return (
                "browser_open executed: "
                f"title={result.get('title', '')}; url={result.get('url', '')}; "
                f"session_id={result.get('session_id', '')}; screenshot={result.get('screenshot', '')}; "
                f"headless={result.get('headless', '')}"
            )
        if tool_name.startswith("browser_"):
            return f"{tool_name} executed: {json.dumps(result, default=str)}"
        if action.get("action") == "multi_tool_call":
            parts = []
            for entry in result.get("results", []):
                if not isinstance(entry, dict):
                    continue
                name = entry.get("tool", "tool")
                tool_result = entry.get("result", {})
                if isinstance(tool_result, dict):
                    fields = "; ".join(
                        f"{key}={value}"
                        for key, value in tool_result.items()
                        if key in {
                            "status",
                            "path",
                            "project_dir",
                            "returncode",
                            "stdout",
                            "url",
                            "title",
                            "selector",
                            "text",
                            "value",
                            "browser",
                            "headless",
                            "session_id",
                            "screenshot",
                            "final_url",
                            "completed_steps",
                            "active_sessions",
                        }
                    )
                    parts.append(f"{name}({fields})")
            return "multi_tool_call executed: " + " | ".join(parts)
        return f"{tool_name} executed: {json.dumps(result, default=str)}"
