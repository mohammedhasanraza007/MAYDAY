"""
M.A.Y.D.A.Y Orchestrator — Phase 04 Agentic Loop
=================================================
R11 intent routing + R10 guard for executable intents.
"""
from __future__ import annotations

import gc
import hashlib
import json
import logging
import re
from collections import deque
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from core.exceptions import (
    HardRuleViolationError,
    RecursiveCallError,
    SchemaValidationError,
    SessionLimitError,
)
from core.intent_router import classify, is_executable_intent, required_tools_for
from core.json_parser import parse_model_output, safe_response_object
from core.session import SessionManager
from core.tool_recovery import FINALIZE_AFTER_TOOL, RECOVERY_SOURCE, recover_action_from_prompt
from core.context_compressor import ContextCompressor
from runtime.task_graph import TaskGraphExecutor
from runtime.action_schema import validate
from runtime.execution_budget import ExecutionBudget, MAX_STEPS_PER_TASK
from runtime.execution_registry import validate_capability, structural_validate
from runtime.health_monitor import runtime_health_monitor
from runtime.state_snapshot import StateSnapshotManager
from runtime.task_lock import route_mutex

logger = logging.getLogger("mayday.orchestrator")

MAX_STEPS = MAX_STEPS_PER_TASK
MAX_INFERENCE_DEPTH = 1
MAX_IDENTICAL_ACTION_REPEATS = 2
MAX_SCHEMA_FAILURES_PER_TASK = 3
MAX_SEMANTIC_FAILURE_REPEATS = 2
ChatOnlyOutputError = HardRuleViolationError


import threading


def compute_outcome_hash(tool_name: str, result: dict[str, Any]) -> str:
    key_fields: dict[str, Any] = {"tool": tool_name}

    if tool_name in (
        "browser_open",
        "browser_click",
        "browser_wait_for_navigation",
        "browser_press_key",
        "browser_get_text",
        "browser_scroll",
    ):
        url = str(result.get("url", ""))
        parsed = urlparse(url)
        key_fields["url"] = url
        key_fields["netloc"] = parsed.netloc
        key_fields["path"] = parsed.path[:80]
        key_fields["query"] = parsed.query[:120]
        key_fields["state"] = str(result.get("state", ""))

    elif tool_name == "web_search":
        key_fields["query"] = str(result.get("query", result.get("search_query", "")))[:100]

    elif tool_name in ("gmail_get_unread", "gmail_get_email_body"):
        emails = result.get("emails", [])
        key_fields["count"] = str(result.get("count", len(emails) if isinstance(emails, list) else ""))
        if isinstance(emails, list) and emails:
            first = emails[0] if isinstance(emails[0], dict) else {}
            key_fields["first_id"] = str(first.get("id", ""))[:20]

    elif tool_name == "file_write":
        key_fields["path"] = str(result.get("path", result.get("file_path", "")))
        key_fields["chars"] = str(result.get("chars_written", result.get("size", result.get("bytes_written", ""))))

    else:
        key_fields["status"] = str(result.get("status", ""))
        key_fields["data"] = json.dumps(result, sort_keys=True, default=str)[:200]

    raw = json.dumps(key_fields, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


class LoopGuard:
    def __init__(self, maxlen: int = 5) -> None:
        self.recent_actions = deque(maxlen=maxlen)
        self.semantic_counts: dict[str, int] = {}

    def record_and_check(self, action_signature: str, last_result: dict[str, Any] | None) -> bool:
        repeats = self.recent_actions.count(action_signature)
        self.recent_actions.append(action_signature)
        if repeats <= 0:
            return False
        if isinstance(last_result, dict) and last_result.get("status") == "error":
            return repeats >= 2
        return True

    def record_semantic_pattern(self, pattern: str) -> bool:
        if not pattern:
            return False
        count = self.semantic_counts.get(pattern, 0) + 1
        self.semantic_counts[pattern] = count
        return count >= MAX_SEMANTIC_FAILURE_REPEATS


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
        self._snapshot_manager = StateSnapshotManager()

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
        preflight_recovered = recover_action_from_prompt(user_prompt, intent, {})
        if isinstance(preflight_recovered, dict) and preflight_recovered.get("action") == "respond":
            self._last_provider = "prompt_recovery_preflight"
            return self._build_final_response(preflight_recovered)
        if preflight_recovered is not None:
            intent = dict(intent)
            intent["executable"] = True
            intent["family"] = self._family_for_recovered_action(preflight_recovered, intent.get("family", "CHAT"))
            intent["required_tools"] = self._tool_names_for_action(preflight_recovered)
        executable = intent["executable"]
        required = intent["required_tools"]
        system_prompt = self._system_prompt(intent)
        last_action_fingerprint = ""
        repeated_action_count = 0
        last_tool_result: dict[str, Any] | None = None
        loop_guard = LoopGuard()
        budget = ExecutionBudget()
        schema_failures = 0

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.session.add_to_history("user", user_prompt)

        for step in range(MAX_STEPS):
            budget.consume_step()
            if self._cancelled:
                return "[Cancelled by user]"

            import threading
            logger.info("LOOP-STEP %d: thread=%s, depth=%d", step + 1, threading.current_thread().name, self._inference_depth)

            if self._inference_depth > MAX_INFERENCE_DEPTH:
                raise RecursiveCallError(f"Model attempted recursive self-call (depth={self._inference_depth} > {MAX_INFERENCE_DEPTH})")

            if self._on_step:
                self._on_step(step + 1, "Running agent step")

            precovered = preflight_recovered if step == 0 else None
            if precovered is not None:
                raw = json.dumps(precovered)
                provider = "prompt_recovery_preflight"
                logger.info(
                    "Prompt recovery preflight selected: %s",
                    precovered.get(RECOVERY_SOURCE, "unknown"),
                )
                self._last_provider = provider
            else:
                self._inference_depth += 1
                try:
                    # E101: Compress messages to stay within token context window
                    compressed_messages = ContextCompressor.compress_messages(messages)
                    runtime_health_monitor.record("context_chars", sum(len(m.get("content", "")) for m in compressed_messages))
                    raw, provider = self._route(compressed_messages, user_prompt)
                    self._last_provider = provider
                finally:
                    self._inference_depth -= 1

            if not executable:
                return raw.strip()

            try:
                action = self._prepare_action(raw, provider, user_prompt, messages)
            except SchemaValidationError as exc:
                schema_failures += 1
                reason = str(exc)
                logger.warning(
                    "Planner schema failure %d/%d: %s",
                    schema_failures,
                    MAX_SCHEMA_FAILURES_PER_TASK,
                    reason,
                )
                self._append_schema_failure_feedback(messages, raw, reason, schema_failures)
                if schema_failures >= MAX_SCHEMA_FAILURES_PER_TASK:
                    return self._build_schema_failure_response(reason)
                continue
            action_name = action.get("action")
            if executable:
                recovered = recover_action_from_prompt(user_prompt, intent, action)
                if recovered is not None:
                    try:
                        action = self._prepare_action(
                            json.dumps(recovered),
                            "prompt_recovery",
                            user_prompt,
                            messages,
                        )
                    except SchemaValidationError as exc:
                        schema_failures += 1
                        reason = str(exc)
                        logger.warning(
                            "Prompt recovery schema failure %d/%d: %s",
                            schema_failures,
                            MAX_SCHEMA_FAILURES_PER_TASK,
                            reason,
                        )
                        self._append_schema_failure_feedback(messages, json.dumps(recovered), reason, schema_failures)
                        if schema_failures >= MAX_SCHEMA_FAILURES_PER_TASK:
                            return self._build_schema_failure_response(reason)
                        continue
                    action_name = action.get("action")

            if executable and step == 0 and action_name == "respond" and provider not in {"exhausted", "circuit_breaker"} and schema_failures == 0:
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
            if loop_guard.record_and_check(action_fingerprint, last_tool_result):
                logger.warning("Loop repetition detected - forcing termination for repeated action: %s", action_fingerprint)
                return self._build_final_response(
                    {
                        "action": "respond",
                        "text": (
                            "Execution stopped after repeated identical actions "
                            "to prevent a routing loop."
                        ),
                    }
                )
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

            budget.set_chain_lengths(*self._chain_lengths(action))
            snapshot = self._snapshot_manager.capture(self)
            result = self._execute_action(action, intent)
            last_tool_result = result
            if result.get("status") == "error" and self._is_catastrophic_failure(result):
                budget.enter_recovery()
                self._snapshot_manager.rollback(self, snapshot)
                budget.exit_recovery()
            self._assert_real_execution(result)
            assert "status" in result and len(result) > 1, (
                "Tool result must include status plus evidence; bare status is a fake success"
            )
            self._append_execution_feedback(messages, action, result)

            schema_pattern = self._schema_failure_pattern(action, result)
            if schema_pattern:
                schema_failures += 1
                logger.warning(
                    "Tool schema-like failure %d/%d: %s",
                    schema_failures,
                    MAX_SCHEMA_FAILURES_PER_TASK,
                    schema_pattern,
                )
                if schema_failures >= MAX_SCHEMA_FAILURES_PER_TASK:
                    return self._build_schema_failure_response(str(result.get("error", schema_pattern)))

            semantic_pattern = self._semantic_loop_pattern(action, result)
            if semantic_pattern and loop_guard.record_semantic_pattern(semantic_pattern):
                logger.warning("Semantic repetition detected - terminating: %s", semantic_pattern)
                return self._build_final_response(
                    {
                        "action": "respond",
                        "text": (
                            "Execution stopped after repeated near-identical tool outcomes. "
                            "The agent has preserved the latest tool result and needs a clearer next step or corrected inputs."
                        ),
                    }
                )

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
            if self._should_return_tool_evidence(action, result, user_prompt):
                return self._build_tool_evidence_response(action, result)

        return self._build_max_steps_response()

    def process_prompt(self, user_prompt: str) -> dict[str, Any]:
        with route_mutex.acquire(user_prompt), self._lock:
            try:
                text = self.run(user_prompt)
                if text is None or str(text).strip() == "":
                    logger.error("All paths exhausted. Returning fallback message to user.")
                    text = (
                        "I was unable to generate a valid response for this task. "
                        "Try rephrasing the request or breaking it into smaller steps."
                    )
                logger.info(
                    "ASSISTANT-RESPONSE: provider=%s text=%s",
                    self._last_provider,
                    str(text).replace("\n", "\\n")[:2500],
                )
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
                runtime_health_monitor.record("failure")
                if self._exception_requires_cleanup(exc):
                    self._emergency_cleanup()
                else:
                    logger.warning("Soft planning failure - preserving loaded model: %s", exc)
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

    def _prepare_action(
        self,
        raw: str,
        provider: str,
        user_prompt: str = "",
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        action = parse_model_output(raw)
        valid, reason = structural_validate(action)
        if not valid:
            raise SchemaValidationError(f"Planner output failed structural validation: {reason}")
        from core.composite_translator import CompositeActionTranslator

        translated = CompositeActionTranslator.translate(
            action,
            enforce_microstep=(provider in ("local", "local_fallback")),
        )
        if translated is None:
            raise SchemaValidationError("Planner output could not be translated into atomic registered tools")
        if user_prompt:
            translated = self._hydrate_generated_content(translated, user_prompt, messages or [])
        valid, reason = validate(translated)
        if not valid:
            raise SchemaValidationError(f"Translated action failed atomic validation: {reason}")
        return translated

    def _append_execution_feedback(
        self,
        messages: list[dict[str, str]],
        action: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Inject both the assistant tool action and structured result into loop state."""
        action_json = json.dumps(action, sort_keys=True, default=str)
        compressed_action = ContextCompressor.compress_assistant_output(action_json)
        tool_context = self._format_tool_result_context(action, result)
        compressed_result = ContextCompressor.compress_tool_result(tool_context)
        messages.append({"role": "assistant", "content": compressed_action})
        messages.append({"role": "tool", "content": compressed_result})
        self.session.add_to_history("assistant", compressed_action, {"kind": "tool_action"})
        self.session.add_to_history("tool", compressed_result, {"kind": "tool_result"})

    def _append_schema_failure_feedback(
        self,
        messages: list[dict[str, str]],
        raw: str,
        reason: str,
        count: int,
    ) -> None:
        compressed_raw = ContextCompressor.compress_assistant_output(str(raw or ""))
        result = {
            "status": "error",
            "tool_name": "planner",
            "error": reason,
            "schema_failures": count,
            "next_step": (
                "Return one valid JSON tool_call using a registered tool and valid parameters. "
                "Do not repeat the rejected schema."
            ),
        }
        messages.append({"role": "assistant", "content": compressed_raw})
        messages.append({"role": "tool", "content": ContextCompressor.compress_tool_result(result)})

    def _format_tool_result_context(self, action: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        context = dict(result)
        tool_names = self._tool_names_for_action(action)
        if len(tool_names) == 1:
            context.setdefault("tool_name", tool_names[0])
        elif tool_names:
            context.setdefault("tools", tool_names)
        context.setdefault("status", result.get("status", "unknown"))
        context.setdefault("next_step", self._next_step_guidance(action, result))
        context.setdefault("actionable", result.get("status") == "success")
        return context

    def _next_step_guidance(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        status = result.get("status")
        tool_names = self._tool_names_for_action(action)
        primary = tool_names[0] if tool_names else str(action.get("action", "tool"))
        if status == "success":
            if primary == "browser_open":
                return "Use browser_get_text or browser_get_page_content to inspect the page; do not open the same URL again."
            if primary == "gmail_get_unread":
                return "Use an email id from emails with gmail_get_email_body, or answer from the listed unread messages."
            if primary == "file_write":
                return "Report the written path and byte/character count; do not write the same empty file again."
            if primary.startswith("calendar_"):
                return "Use the returned event/list details to answer; do not repeat the same calendar action."
            return "Use this tool result to decide the next single atomic action or final answer."
        if status == "cancelled":
            return "Stop and explain that permission was denied."
        return "Correct the parameters before retrying; do not repeat the same failing schema."

    def _tool_names_for_action(self, action: dict[str, Any]) -> list[str]:
        action_name = str(action.get("action", ""))
        if action_name == "tool_call":
            return [str(action.get("tool_name", ""))]
        if action_name == "multi_tool_call":
            names: list[str] = []
            for entry in action.get("tools", []):
                if isinstance(entry, dict):
                    names.append(str(entry.get("tool_name", "")))
            return [name for name in names if name]
        return [action_name] if action_name else []

    def _family_for_recovered_action(self, action: dict[str, Any], fallback: str) -> str:
        tools = set(self._tool_names_for_action(action))
        if tools & {"web_search", "web_fetch"}:
            return "WEB_ACCESS"
        if any(tool.startswith("browser_") or tool.startswith("gmail_") or tool.startswith("calendar_") for tool in tools):
            return "AUTOMATION"
        if tools & {"shell_run", "powershell_run", "server_launch", "server_runner"}:
            return "EXECUTION"
        if tools & {"file_write", "file_read", "excel_create", "excel_write", "excel_read"}:
            return "FILE_OPS"
        return fallback or "CHAT"

    def _schema_failure_pattern(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        if not isinstance(result, dict) or result.get("status") != "error":
            return ""
        error = self._first_error_text(result)
        if not self._is_schema_like_error(error):
            return ""
        tools = ",".join(self._tool_names_for_action(action)) or "tool"
        return f"{tools}:schema:{self._normalize_error_pattern(error)}"

    def _semantic_loop_pattern(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""
        status = str(result.get("status", "unknown"))
        if status == "error":
            tools = ",".join(self._tool_names_for_action(action)) or "tool"
            error = self._normalize_error_pattern(self._first_error_text(result))
            classification = str(result.get("classification", ""))
            return f"{tools}:error:{classification}:{error}"
        if status == "success":
            if action.get("action") == "multi_tool_call":
                pieces: list[str] = []
                for entry in result.get("results", []):
                    if not isinstance(entry, dict):
                        continue
                    tool_name = str(entry.get("tool", ""))
                    tool_result = entry.get("result", {})
                    if tool_name and isinstance(tool_result, dict):
                        pieces.append(f"{tool_name}:{compute_outcome_hash(tool_name, tool_result)}")
                if pieces:
                    return "|".join(pieces)[:500]
            tool_names = self._tool_names_for_action(action)
            tool_name = tool_names[0] if tool_names else str(action.get("action", "tool"))
            return f"{tool_name}:success:{compute_outcome_hash(tool_name, result)}"
        return ""

    def _first_error_text(self, result: dict[str, Any]) -> str:
        error = result.get("error")
        if isinstance(error, str) and error:
            return error
        results = result.get("results")
        if isinstance(results, list):
            for entry in results:
                if not isinstance(entry, dict):
                    continue
                nested = entry.get("result")
                if isinstance(nested, dict):
                    nested_error = nested.get("error")
                    if isinstance(nested_error, str) and nested_error:
                        return nested_error
        return ""

    def _is_schema_like_error(self, error: str) -> bool:
        text = (error or "").lower()
        return any(
            marker in text
            for marker in (
                "schema",
                "validation",
                "required",
                "must be",
                "unknown or uncontracted",
                "invalid",
                "missing",
                "empty string",
                "content is empty",
            )
        )

    def _normalize_error_pattern(self, error: str) -> str:
        text = (error or "").lower()
        text = re.sub(r"https?://\S+", "<url>", text)
        text = re.sub(r"[a-z]:\\[^\s]+", "<path>", text)
        text = re.sub(r"['\"][^'\"]{1,120}['\"]", "<value>", text)
        text = re.sub(r"\d{1,4}", "<n>", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:180]

    def _primary_target(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        for container in (result, action.get("parameters", {})):
            if isinstance(container, dict):
                for key in ("path", "file_path", "url", "query", "selector", "email_id", "event_id", "title"):
                    value = container.get(key)
                    if isinstance(value, str) and value.strip():
                        return f"{key}={value.strip().lower()[:160]}"
        if action.get("action") == "multi_tool_call":
            tools = []
            for entry in action.get("tools", []):
                if not isinstance(entry, dict):
                    continue
                params = entry.get("parameters", {})
                target = self._primary_target({"parameters": params}, {})
                if target:
                    tools.append(f"{entry.get('tool_name', '')}:{target}")
            if tools:
                return "|".join(tools)[:220]
        return ""

    def _build_schema_failure_response(self, reason: str) -> str:
        return (
            "Execution stopped after repeated invalid tool schemas. "
            f"Last validation error: {reason}. "
            "Please retry with the missing tool fields stated explicitly."
        )

    def _build_max_steps_response(self) -> str:
        return (
            f"Execution stopped after reaching the {MAX_STEPS}-step safety ceiling. "
            "The latest tool result was preserved in the agent context, but the task did not converge cleanly."
        )

    def _hydrate_generated_content(
        self,
        action: dict[str, Any],
        user_prompt: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        action_name = action.get("action")
        if action_name == "tool_call" and action.get("tool_name") == "file_write":
            updated = dict(action)
            updated["parameters"] = self._hydrate_file_write_parameters(
                dict(action.get("parameters", {}) or {}),
                user_prompt,
                messages,
            )
            return updated
        if action_name == "multi_tool_call":
            updated_tools = []
            changed = False
            for entry in action.get("tools", []):
                if not isinstance(entry, dict):
                    updated_tools.append(entry)
                    continue
                updated_entry = dict(entry)
                if updated_entry.get("tool_name") == "file_write":
                    updated_entry["parameters"] = self._hydrate_file_write_parameters(
                        dict(updated_entry.get("parameters", {}) or {}),
                        user_prompt,
                        messages,
                    )
                    changed = True
                updated_tools.append(updated_entry)
            if changed:
                updated = dict(action)
                updated["tools"] = updated_tools
                return updated
        return action

    def _hydrate_file_write_parameters(
        self,
        params: dict[str, Any],
        user_prompt: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        path = str(params.get("path", params.get("file_path", ""))).strip()
        path_lower = path.lower()
        import os
        if path_lower.startswith("c:\\users") or not os.path.isabs(path):
            filename = os.path.basename(path)
            if not filename:
                filename = "notes.txt"
            path = f"E:\\MAYDAY\\output\\{filename}"
            params = dict(params)
            params["path"] = path
            if "file_path" in params:
                params["file_path"] = path

        if params.get("template"):
            return params
        content = params.get("content", "")
        if not isinstance(content, str):
            return params
        threshold = self._minimum_content_length(user_prompt, str(params.get("path", params.get("file_path", ""))))
        if content.strip() and (threshold <= 0 or len(content.strip()) >= threshold):
            return params
        if threshold <= 0 and content.strip():
            return params
        if threshold <= 0:
            raise SchemaValidationError(
                "file_write content is empty; provide non-empty content or use an explicit blank_* template"
            )

        generator = self._content_generator()
        if not callable(generator):
            raise SchemaValidationError("file_write content is empty and no content generator is available")

        path = str(params.get("path", params.get("file_path", ""))).strip()
        minimum = max(threshold, 50)
        generation_prompt = self._content_generation_prompt(user_prompt, path, minimum)
        context = self._content_generation_context(messages)
        best = content.strip()
        max_tokens = self._content_token_budget(user_prompt, path)
        for attempt in range(3):
            generated = generator(
                generation_prompt,
                context=context,
                temp=0.25,
                max_tokens=max_tokens,
            )
            text = self._clean_generated_content(str(generated or ""))
            if text and not text.lower().startswith("error:") and len(text) > len(best):
                best = text
            if len(best.strip()) >= minimum:
                updated = dict(params)
                updated["content"] = best.strip()
                updated["generated_content"] = True
                updated["minimum_chars"] = minimum
                updated["generation_attempts"] = attempt + 1
                return updated
            generation_prompt = (
                f"{generation_prompt}\n\nPrevious output was too short "
                f"({len(best.strip())} chars). Regenerate at least {minimum} useful characters."
            )

        raise SchemaValidationError(
            f"file_write content generation produced {len(best.strip())} chars; minimum is {minimum}"
        )

    def _content_generator(self) -> Callable[..., str] | None:
        inference = getattr(self.router, "inference", None)
        generator = getattr(inference, "generate_content", None)
        return generator if callable(generator) else None

    def _minimum_content_length(self, user_prompt: str, path: str) -> int:
        text = f"{user_prompt} {path}".lower()
        import re
        word_match = re.search(r'(\d+)\s*word', text)
        if word_match:
            word_target = int(word_match.group(1))
            return max(50, word_target * 5)

        suffix = Path(path).suffix.lower()
        if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".yml"}:
            return 50
        if any(marker in text for marker in ("comparison", "compare", "versus", "vs.", "table", "top 5", "top-5")):
            return 201
        if any(marker in text for marker in ("report", "article", "guide", "essay", "research", "document", "summary", "summarize", "summarise", "write about", " about ", "overview")):
            return 401
        if any(marker in text for marker in ("email draft", "draft email", "write an email")):
            return 120
        if any(marker in text for marker in ("notes", "note", "list")):
            return 101
        return 100

    def _content_token_budget(self, user_prompt: str, path: str) -> int:
        minimum = self._minimum_content_length(user_prompt, path)
        if minimum >= 2000:
            return 3000
        if minimum >= 1000:
            return 2400
        if minimum >= 401:
            return 1800
        if minimum >= 201:
            return 1200
        return 900

    def _content_generation_prompt(self, user_prompt: str, path: str, minimum: int) -> str:
        return (
            "Generate only the file content for the requested document. "
            "Do not include markdown fences, tool JSON, explanations, or prefaces.\n"
            f"Target path: {path or 'unspecified'}\n"
            f"Minimum useful characters: {minimum}\n"
            f"User request: {user_prompt}"
        )

    def _content_generation_context(self, messages: list[dict[str, str]]) -> str:
        parts = []
        for message in messages[-6:]:
            role = message.get("role", "")
            content = message.get("content", "")
            if content:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)[-3000:]

    def _clean_generated_content(self, content: str) -> str:
        text = (content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

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
        valid, reason = validate_capability(tool_name, intent["family"])
        if not valid:
            return {"status": "error", "error": reason, "classification": "capability_violation"}

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
            logger.info(
                "TOOL-RESULT: tool=%s status=%s result=%s",
                tool_name,
                result.get("status", "unknown"),
                json.dumps(result, sort_keys=True, default=str)[:800],
            )
            return result
        return {"status": "error", "error": f"Engine returned non-dict result: {type(result).__name__}"}

    def _chain_lengths(self, action: dict[str, Any]) -> tuple[int, int]:
        if action.get("action") == "multi_tool_call":
            tools = [entry.get("tool_name", "") for entry in action.get("tools", []) if isinstance(entry, dict)]
        elif action.get("action") == "tool_call":
            tools = [str(action.get("tool_name", ""))]
        else:
            tools = [str(action.get("action", ""))]
        return len(tools), sum(1 for name in tools if name.startswith("browser_"))

    def _is_catastrophic_failure(self, result: dict[str, Any]) -> bool:
        error = str(result.get("error", "")).lower()
        classification = str(result.get("classification", "")).lower()
        return any(
            marker in f"{error} {classification}"
            for marker in ("corrupt", "deadlock", "recursive", "worker timed out", "invalid argument", "context or browser has been closed")
        )

    def _exception_requires_cleanup(self, exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        return any(
            marker in text
            for marker in (
                "worker timed out",
                "out of memory",
                "memoryerror",
                "deadlock",
                "corrupt",
                "context or browser has been closed",
            )
        )

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

        # LAW-22: Content requested inside chat must respond inline (no file_write
        # fallback) unless the user explicitly asks to save to a file.
        if executable and self._is_inline_content_request(user_prompt):
            logger.info("LAW-22: inline content request detected — forcing CHAT mode")
            family = "CHAT"
            required = []
            executable = False

        return {
            "raw_input": user_prompt,
            "family": family or "CHAT",
            "required_tools": required,
            "executable": executable,
        }

    @staticmethod
    def _is_inline_content_request(user_prompt: str) -> bool:
        """Detect prompts that ask for text content inline (essay, list, explanation)
        without explicit file/save intent.

        Returns True when the model should respond inline instead of using file_write.
        """
        lower = user_prompt.lower()

        # If the user explicitly wants a file, let the tool handle it
        file_keywords = (
            "save", "file", "write to", "save to", "create a file",
            "make a file", "write a file", "to disk", "output to",
            ".txt", ".md", ".py", ".js", ".html", ".csv", ".json",
            ".xlsx", "spreadsheet", "excel",
        )
        if any(kw in lower for kw in file_keywords):
            return False

        # Content-generation verbs that suggest inline response
        content_verbs = (
            "list ", "explain", "describe", "summarize", "summarise",
            "write me", "write a ", "tell me", "give me", "draft ",
            "compare", "what is", "what are", "how to", "why ",
            "define ", "outline", "pros and cons",
        )
        return any(kw in lower for kw in content_verbs)

    def _action_allowed_for_intent(self, action: dict[str, Any], intent: dict[str, Any]) -> bool:
        action_name = action.get("action", "")
        if action_name == "respond":
            return True

        if not intent["executable"]:
            return False

        family = intent["family"]
        allowed_actions_by_family: dict[str, set[str]] = {
            "WEB_ACCESS": {
                "tool_call",
                "multi_tool_call",
                "web_search",
                "web_fetch",
                "file_write",
                "excel_create",
                "excel_write",
            },
            "PROJECT_CREATION": {
                "tool_call",
                "multi_tool_call",
                "scaffold",
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
                "file_write",
                "file_read",
                "excel_create",
                "excel_write",
                "excel_read",
            },
            "AUTOMATION": {
                "tool_call",
                "multi_tool_call",
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
                "calendar_create_event",
                "calendar_create_event_via_browser",
                "calendar_list_events",
                "gmail_get_unread",
                "gmail_get_email_body",
            },
            "FILE_OPS": {"tool_call", "multi_tool_call", "file_read", "file_write", "excel_create", "excel_write", "excel_read"},
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
        valid, _reason = validate_capability(tool_name, family)
        return valid

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
        text = action.get("text", action.get("response", action.get("content", "")))
        if not isinstance(text, str):
            text = str(text)
        return text

    def _should_return_tool_evidence(self, action: dict[str, Any], result: dict[str, Any], user_prompt: str = "") -> bool:
        if action.get(FINALIZE_AFTER_TOOL) is True:
            return True
        if result.get("status") == "success" and self._simple_browser_open_completed(action, user_prompt):
            return True
        return False

    def _simple_browser_open_completed(self, action: dict[str, Any], user_prompt: str) -> bool:
        if action.get("action") != "tool_call" or action.get("tool_name") != "browser_open":
            return False
        text = (user_prompt or "").lower()
        if "open" not in text:
            return False
        follow_up_markers = (
            "tell",
            "what",
            "which",
            "read",
            "summarize",
            "summary",
            "first",
            "title",
            "search",
            "find",
            "click",
            "type",
            "send",
            "play",
            "message",
        )
        return not any(marker in text for marker in follow_up_markers)

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
            url = str(result.get("url", ""))
            prefix = ""
            if "web.whatsapp.com" in url.lower():
                prefix = (
                    "WhatsApp Web opened. If it shows a login screen, scan the QR code in the browser to continue. "
                )
            return (
                f"{prefix}browser_open executed: "
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
            detail = "multi_tool_call executed: " + " | ".join(parts)
            summary = action.get("_recovery_summary", "")
            if isinstance(summary, str) and summary.strip():
                return f"{summary.strip()}\n{detail}"
            return detail
        return f"{tool_name} executed: {json.dumps(result, default=str)}"
