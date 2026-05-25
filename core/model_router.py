"""
M.A.Y.D.A.Y Model Router — v6.0 Stabilized Routing
=====================================================
v6.0 changes:
- E103: Microstep extraction for local AUTOMATION responses
- E104: Provider cooldown integration (respects Retry-After)
- E105: Context trimming for local model (max 8000 chars)
- E107: Escalation circuit breaker (prevents local↔API ping-pong)
"""
import concurrent.futures
import gc
import json
import logging
import os
import threading
import time

import psutil

from core.exceptions import PermissionDeniedError, ProviderFailureError, InferenceTimeoutError
from core.intent_router import classify, is_executable_intent
from runtime.provider_cooldown import provider_cooldown
from runtime.health_monitor import runtime_health_monitor

logger = logging.getLogger("mayday.router")

LOCAL_TIMEOUT_WITH_API = 90
LOCAL_TIMEOUT_NO_API = 180
COMPLEXITY_THRESHOLD = 0.35
API_FIRST_COMPLEX_FAMILIES = {"PROJECT_CREATION", "AUTOMATION"}

# E105: Max chars for context fed to local model
LOCAL_CONTEXT_CHAR_LIMIT = 8000
API_ROUTE_COMPLEXITY_THRESHOLD = 0.85
HALLUCINATION_RETRY_LIMIT = 2

# E107: Circuit breaker — if both providers fail within this window, pause
CIRCUIT_BREAKER_WINDOW = 60  # seconds
CIRCUIT_BREAKER_MAX_FAILURES = 3


class TaskComplexityAnalyzer:
    def score(self, prompt: str) -> float:
        text = (prompt or "").lower()
        family = classify(prompt)
        if is_executable_intent(prompt):
            base_by_family = {
                "AUTOMATION": 0.45,
                "WEB_ACCESS": 0.35,
                "FILE_OPS": 0.35,
                "EXECUTION": 0.50,
                "PROJECT_CREATION": 0.78,
            }
            score = base_by_family.get(family or "", 0.45)
            if any(k in text for k in ("full stack", "multi-step", "complex", "system", "workflow", "backend", "database")):
                score += 0.20
            if len(prompt.split()) > 80:
                score += 0.10
            return round(min(score, 1.0), 3)
        factors = []
        tokens = len(prompt.split())
        factors.append(min(tokens / 300, 1.0))
        multi_kw = ["project", "app", "website", "api", "full stack", "multi"]
        factors.append(1.0 if any(k in prompt.lower() for k in multi_kw) else 0.0)
        code_kw = ["implement", "build", "create", "design", "architect", "system"]
        factors.append(0.6 if any(k in prompt.lower() for k in code_kw) else 0.0)
        reason_kw = ["explain why", "compare", "analyse", "best approach", "trade-off"]
        factors.append(0.5 if any(k in prompt.lower() for k in reason_kw) else 0.0)
        return round(sum(factors) / len(factors), 3)


class _EscalationCircuitBreaker:
    """Prevents destructive local↔API ping-pong loops (E107).

    Tracks recent failures for each provider. If both local AND API have
    failed within the time window, the breaker trips and forces a cooldown
    response instead of infinite retries.
    """

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {"local": [], "api": []}

    def record_failure(self, provider: str) -> None:
        key = "api" if provider not in ("local", "local_fallback") else "local"
        now = time.time()
        self._failures[key].append(now)
        # Prune old entries
        cutoff = now - CIRCUIT_BREAKER_WINDOW
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]

    def is_tripped(self) -> bool:
        now = time.time()
        cutoff = now - CIRCUIT_BREAKER_WINDOW
        local_recent = [t for t in self._failures.get("local", []) if t > cutoff]
        api_recent = [t for t in self._failures.get("api", []) if t > cutoff]
        return (
            len(local_recent) >= CIRCUIT_BREAKER_MAX_FAILURES
            and len(api_recent) >= CIRCUIT_BREAKER_MAX_FAILURES
        )

    def reset(self) -> None:
        self._failures = {"local": [], "api": []}


def _get_ram_mb() -> float:
    """Get current process RSS in MB."""
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


class LocalValidationError(RuntimeError):
    """Local model returned parseable output that failed the tool contract."""


class ModelRouter:
    def __init__(self, inference_engine, api_manager=None):
        self.inference = inference_engine
        self.api = api_manager
        self.analyzer = TaskComplexityAnalyzer()
        self._last_provider = "local"
        self._route_log: list[dict] = []
        self._breaker = _EscalationCircuitBreaker()
        self._route_epoch = 0
        self._api_lock = threading.RLock()
        self._api_failed_epochs: set[int] = set()

    def route(self, prompt, context: str = "") -> tuple[str, str]:
        self._route_epoch += 1
        route_epoch = self._route_epoch
        api_messages = prompt if isinstance(prompt, list) else None
        if isinstance(prompt, list):
            prompt, context = self._split_messages(prompt)
        score = self.analyzer.score(prompt)
        has_api = self.api.has_active_provider() if self.api else False
        ram_before = _get_ram_mb()
        logger.info(
            "Complexity: %.2f, API available: %s, RAM: %.1f MB",
            score, has_api, ram_before,
        )

        log_entry = {
            "prompt_preview": prompt[:60],
            "score": score,
            "has_api": has_api,
            "route_epoch": route_epoch,
            "timestamp": time.time(),
            "ram_before_mb": round(ram_before, 1),
        }

        # ── E107: Circuit breaker check ──────────────────────────────
        if self._breaker.is_tripped():
            wait = provider_cooldown.seconds_remaining(
                self.api.active_provider_name() if self.api else "none"
            )
            msg = (
                f"Both local and API providers have failed repeatedly. "
                f"Please wait {max(wait, 10):.0f} seconds before retrying."
            )
            logger.warning("Circuit breaker tripped: %s", msg)
            log_entry.update({"provider": "circuit_breaker", "reason": "both_failed"})
            self._route_log.append(log_entry)
            return json.dumps({"action": "respond", "text": msg}), "circuit_breaker"

        # ── Simple tasks — local only, no timeout ────────────────────
        if score < COMPLEXITY_THRESHOLD:
            result = self.inference.generate(prompt, context)
            self._last_provider = "local"
            ram_after = _get_ram_mb()
            log_entry.update({
                "provider": "local",
                "reason": "low_complexity",
                "ram_after_mb": round(ram_after, 1),
            })
            self._route_log.append(log_entry)
            self._breaker.reset()
            gc.collect()
            return result, "local"

        intent_family = classify(prompt)

        # ── E104: Check cooldown before API calls ────────────────────
        # Helper to dynamically check if API is currently ready
        def is_api_currently_available() -> bool:
            if runtime_health_monitor.is_safe_mode():
                logger.warning("Runtime safe mode active; suppressing API escalation")
                return False
            if route_epoch in self._api_failed_epochs:
                logger.info("API blocked for route_epoch=%s after prior same-route failure", route_epoch)
                return False
            if not self.api or not self.api.has_active_provider():
                return False
            api_provider_name = self.api.active_provider_name()
            if not provider_cooldown.is_cooled_down(api_provider_name):
                remaining = provider_cooldown.seconds_remaining(api_provider_name)
                runtime_health_monitor.record("cooldown")
                logger.info(
                    "API in cooldown for %s (%.1fs remaining) - routing to LOCAL",
                    api_provider_name, remaining
                )
                return False
            return True

        # ── API-first for complex executable tasks ───────────────────
        if (
            self._should_route_to_api(prompt, score, intent_family, route_epoch)
            and is_api_currently_available()
            and is_executable_intent(prompt)
            and intent_family in API_FIRST_COMPLEX_FAMILIES
        ):
            try:
                logger.info("Complex executable %s routed directly to approved API provider", intent_family)
                result = self._call_api(api_messages, prompt, context, route_epoch)
                provider = self.api.active_provider_name()
                self._last_provider = provider
                log_entry.update({"provider": provider, "reason": "api_first_complex_executable"})
                self._route_log.append(log_entry)
                self._breaker.reset()
                return result, provider
            except PermissionDeniedError:
                log_entry.update({"provider": "api_blocked", "reason": "approval_required"})
                logger.info("API approval unavailable - routing to LOCAL")
                gc.collect()
            except ProviderFailureError as e:
                self._handle_api_failure(e, self.api.active_provider_name() if self.api else "none", route_epoch)
                gc.collect()

        # ── Complex tasks — timeout-based local routing ──────────────
        timeout = LOCAL_TIMEOUT_WITH_API if has_api else LOCAL_TIMEOUT_NO_API

        # E105: Trim context for local model
        trimmed_context = self._trim_context_for_local(context)

        try:
            result = self._run_validated_local(prompt, trimmed_context, timeout, intent_family)
            self._last_provider = "local"
            ram_after = _get_ram_mb()
            log_entry.update({
                "provider": "local",
                "reason": "local_success",
                "ram_after_mb": round(ram_after, 1),
            })
            self._route_log.append(log_entry)
            self._breaker.reset()
            gc.collect()
            return result, "local"
        except concurrent.futures.TimeoutError:
            logger.warning("Local timed out - destroying unresponsive worker before escalation")
            self._breaker.record_failure("local")
            try:
                if hasattr(self.inference, "kill_worker"):
                    self.inference.kill_worker()
                elif hasattr(self.inference, "destroy_model"):
                    self.inference.destroy_model()
            except Exception as e:
                logger.error("Model cleanup on timeout failed: %s", e)
            gc.collect()
        except LocalValidationError as e:
            logger.warning("Persistent local schema failure - escalating without destroying model: %s", e)
            self._breaker.record_failure("local")
            gc.collect()
        except Exception as e:
            logger.warning("Local model threw exception: %s. Escalating to API.", e)
            self._breaker.record_failure("local")
            gc.collect()

        # ── API escalation ───────────────────────────────────────────
        if self._should_route_to_api(prompt, score, intent_family, route_epoch) and is_api_currently_available():
            try:
                result = self._call_api(api_messages, prompt, context, route_epoch)
                logger.info("API ESCALATION SUCCESS.")
                provider = self.api.active_provider_name()
                self._last_provider = provider
                log_entry.update({"provider": provider, "reason": "api_escalation"})
                self._route_log.append(log_entry)
                self._breaker.reset()
                return result, provider
            except PermissionDeniedError:
                log_entry.update({"provider": "api_blocked", "reason": "approval_required"})
                logger.info("API approval unavailable during escalation - keeping LOCAL fallback")
                gc.collect()
            except ProviderFailureError as e:
                self._handle_api_failure(e, self.api.active_provider_name() if self.api else "none", route_epoch)

        # ── Final fallback — reload model (only if breaker not tripped) ─
        if self._breaker.is_tripped():
            msg = "All providers temporarily unavailable. Please retry in 30 seconds."
            log_entry.update({"provider": "exhausted", "reason": "circuit_breaker"})
            self._route_log.append(log_entry)
            return json.dumps({"action": "respond", "text": msg}), "exhausted"

        if getattr(self.inference, "loader", None) is None:
            msg = self._all_paths_failed_message()
            log_entry.update({"provider": "exhausted", "reason": "local_loader_missing"})
            self._route_log.append(log_entry)
            return json.dumps({"action": "respond", "text": msg}), "exhausted"
        if self.inference.loader.is_loaded():
            logger.info("Using already-loaded model for final fallback attempt")
        else:
            logger.info("Loading model for final fallback attempt...")
            self.inference.loader.load_best_available()

        # E105: Use trimmed context for fallback too
        result = self.inference.generate(prompt, trimmed_context)

        # E103: Microstep enforcement for local fallback
        if intent_family == "AUTOMATION":
            result = self._enforce_microstep(result)

        if is_executable_intent(prompt) and not self._validate_local_result(result, intent_family or "", True):
            msg = self._all_paths_failed_message()
            log_entry.update({"provider": "exhausted", "reason": "invalid_local_fallback"})
            self._route_log.append(log_entry)
            return json.dumps({"action": "respond", "text": msg}), "exhausted"

        self._last_provider = "local_fallback"
        log_entry.update({"provider": "local_fallback", "reason": "all_failed"})
        self._route_log.append(log_entry)
        gc.collect()
        return result, "local_fallback"

    def _all_paths_failed_message(self) -> str:
        provider = self.api.active_provider_name() if self.api and self.api.has_active_provider() else "openai_compatible"
        remaining = provider_cooldown.seconds_remaining(provider)
        wait = max(remaining, 60.0 if remaining > 0 else 0.0)
        if wait > 0:
            return (
                "I was unable to complete this task. The API is in a cooldown period "
                f"and the local model could not generate a valid action. Please try again in {wait:.0f} seconds "
                "or simplify the request."
            )
        return (
            "I was unable to complete this task because the local model could not generate a valid action "
            "and no API fallback was available. Please simplify the request and try again."
        )

    def _call_api(self, api_messages, prompt: str, context: str, route_epoch: int) -> str:
        """Unified API call with cooldown-aware error handling."""
        if not self.api or not self.api.has_active_provider():
            raise ProviderFailureError("No active API provider is currently available")
        provider_name = self.api.active_provider_name()
        with self._api_lock:
            if route_epoch in self._api_failed_epochs:
                raise ProviderFailureError("API already failed in this route epoch")
            snapshot = provider_cooldown.snapshot(provider_name)
            if not snapshot["cooled_down"]:
                runtime_health_monitor.record("cooldown")
                raise ProviderFailureError(
                    f"API provider {provider_name} is on cooldown "
                    f"({snapshot['seconds_remaining']:.1f}s remaining)"
                )
            if api_messages is not None and hasattr(self.api, "complete_messages"):
                return self.api.complete_messages(api_messages)
            return self.api.complete(prompt, context)

    def _handle_api_failure(self, error: ProviderFailureError, provider_name: str, route_epoch: int) -> None:
        """Record API failure and update cooldown if rate-limited (E104)."""
        from runtime.provider_clients.openai_compatible_client import RateLimitError

        self._breaker.record_failure("api")
        self._api_failed_epochs.add(route_epoch)
        runtime_health_monitor.record("failure")

        if isinstance(error, RateLimitError):
            provider_cooldown.record_rate_limit(provider_name, error.retry_after)
            remaining = provider_cooldown.seconds_remaining(provider_name)
            logger.warning(
                "API rate-limited: cooldown %.1fs for %s",
                remaining, provider_name,
            )
        else:
            logger.warning("API provider failed: %s. Falling back.", error)

    def _should_route_to_api(self, prompt: str, complexity: float, intent_family: str | None, route_epoch: int) -> bool:
        if route_epoch in self._api_failed_epochs:
            return False
        if not self.api or not self.api.has_active_provider():
            return False
        provider_name = self.api.active_provider_name()
        recent_429s = provider_cooldown.failures_in_last(provider_name, minutes=5)
        if recent_429s >= 3:
            logger.info("API has %d recent 429s - preferring LOCAL", recent_429s)
            return False
        if complexity < API_ROUTE_COMPLEXITY_THRESHOLD:
            logger.info(
                "Complexity %.2f below API threshold %.2f - routing to LOCAL",
                complexity, API_ROUTE_COMPLEXITY_THRESHOLD,
            )
            return False
        if not provider_cooldown.is_cooled_down(provider_name):
            remaining = provider_cooldown.seconds_remaining(provider_name)
            logger.info("API in cooldown for %s (%.1fs remaining) - routing to LOCAL", provider_name, remaining)
            return False
        if intent_family == "AUTOMATION" and complexity < 0.85:
            logger.info("Automation complexity %.2f is local-suitable - routing to LOCAL", complexity)
            return False
        return True

    def _run_validated_local(self, prompt: str, context: str, timeout: int, intent_family: str | None) -> str:
        is_exec = is_executable_intent(prompt)
        next_context = context
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            for attempt in range(HALLUCINATION_RETRY_LIMIT + 1):
                future = ex.submit(self.inference.generate, prompt, next_context)
                try:
                    result = future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    raise

                if self._validate_local_result(result, intent_family or "", is_exec):
                    if intent_family == "AUTOMATION":
                        result = self._enforce_microstep(result)
                    return result

                if attempt < HALLUCINATION_RETRY_LIMIT:
                    logger.warning("Hallucinated or invalid tool schema - retrying with stricter system prompt")
                    next_context = self._inject_strict_tool_contract(context, intent_family)
                else:
                    logger.warning("Persistent hallucination - escalating to API/local fallback without destroy")
        raise LocalValidationError(f"invalid local tool schema for {intent_family}")

    def _inject_strict_tool_contract(self, context: str, intent_family: str | None) -> str:
        from runtime.execution_registry import REGISTERED_TOOLS

        tool_names = sorted(REGISTERED_TOOLS)
        contract = (
            "STOP. Your previous response was invalid JSON or contained an unknown tool name.\n\n"
            "You MUST output ONLY a JSON object. No text before it. No text after it.\n"
            "No markdown. No code fences. No explanation.\n\n"
            "VALID TOOL NAMES (use EXACTLY one of these, spelled exactly as shown):\n"
            + ", ".join(tool_names)
            + "\n\n"
            "REQUIRED OUTPUT FORMAT:\n"
            "{\"action\":\"tool_call\",\"tool_name\":\"TOOL_NAME_HERE\",\"parameters\":{\"KEY\":\"VALUE\"}}\n\n"
            "OR for a text response:\n"
            "{\"action\":\"respond\",\"text\":\"YOUR_RESPONSE_HERE\"}\n\n"
            "Return exactly one atomic tool_call. Wait for tool results before planning another action.\n"
            "Common required fields: file_write path+non-empty content OR path+template; "
            "web_search query; web_fetch url; browser_open url; shell_run command; "
            "browser_get_page_content url; calendar_create_event title+start_datetime (end_datetime optional); "
            "gmail_get_unread max_results; gmail_get_email_body email_id; scaffold project_name+stack+files.\n"
            "For blank file creation use file_write template one of blank_xlsx, blank_csv, blank_json, blank_txt.\n"
            "For browser page reading use browser_get_page_content(url) or browser_get_text on an opened page. "
            "Do not invent page_fetcher, browser_wait_for, browser_wait_for_selector, browser_check, browser_extract, or browser_act.\n"
            f"Intent family: {intent_family or 'UNKNOWN'}.\n"
        )
        budget = max(0, LOCAL_CONTEXT_CHAR_LIMIT - len(contract))
        tail = context[-budget:] if budget and len(context) > budget else context
        return contract + tail

    def _trim_context_for_local(self, context: str) -> str:
        """E105: Truncate context to prevent local model context overflow.

        Keeps the most recent content up to LOCAL_CONTEXT_CHAR_LIMIT.
        """
        if not context or len(context) <= LOCAL_CONTEXT_CHAR_LIMIT:
            return context

        # Keep the tail (most recent messages)
        trimmed = context[-LOCAL_CONTEXT_CHAR_LIMIT:]

        # Try to break at a message boundary
        boundary = trimmed.find("\n")
        if boundary > 0 and boundary < 200:
            trimmed = trimmed[boundary + 1:]

        logger.info(
            "Context trimmed for local model: %d → %d chars",
            len(context), len(trimmed),
        )
        return "[earlier context trimmed]\n" + trimmed

    def _enforce_microstep(self, raw: str) -> str:
        """E103: If local model produced a multi-step plan, extract only the first step.

        This prevents the local 7B model from generating giant browser chains
        that always fail to parse.
        """
        try:
            # Strip markdown fences if present
            text = raw.strip()
            if text.startswith("```"):
                first_nl = text.find("\n")
                if first_nl != -1:
                    text = text[first_nl + 1:]
                if text.endswith("```"):
                    text = text[:-3].strip()

            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return raw

            action = parsed.get("action", "")

            from core.composite_translator import CompositeActionTranslator
            from runtime.execution_registry import structural_validate
            from runtime.action_schema import validate

            valid, _reason = structural_validate(parsed)
            if not valid:
                return raw
            translated = CompositeActionTranslator.translate(parsed, enforce_microstep=True)
            if translated is None:
                return raw
            valid, _reason = validate(translated)
            if valid:
                return json.dumps(translated)

        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        return raw

    def get_last_provider(self) -> str:
        return self._last_provider

    def get_route_log(self) -> list[dict]:
        return list(self._route_log)

    def _split_messages(self, messages: list[dict]) -> tuple[str, str]:
        latest_user = ""
        fixed_parts: list[str] = []
        history_parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            if role == "user":
                latest_user = content
            elif role == "system" and content:
                fixed_parts.append(f"{role}: {content}")
            elif content:
                history_parts.append(f"{role}: {content}")

        fixed_context = "\n".join(fixed_parts)
        history_context = "\n".join(history_parts)
        budget = LOCAL_CONTEXT_CHAR_LIMIT - len(fixed_context) - 1
        if budget < 500:
            logger.error("Tool/system block exceeds local context budget; local model may fail")
            budget = max(0, budget)
        if len(history_context) > budget:
            original_len = len(history_context)
            history_context = history_context[-budget:] if budget else ""
            boundary = history_context.find("\n")
            if 0 < boundary < 200:
                history_context = history_context[boundary + 1:]
            history_context = "[earlier context trimmed]\n" + history_context
            logger.info(
                "Context trimmed for local model: %d -> %d chars (system/tools preserved)",
                original_len, len(history_context),
            )

        raw_context = "\n".join(part for part in (fixed_context, history_context) if part)
        return latest_user, raw_context

    def _validate_local_result(self, result: str, intent_family: str, is_executable: bool) -> bool:
        try:
            from core.json_parser import parse_model_output
            from runtime.action_schema import validate
            
            parsed = parse_model_output(result)
            if not parsed or not isinstance(parsed, dict):
                return False
            
            # If it's a fallback safe response because parsing failed
            if parsed.get("meta", {}).get("fallback") is True:
                return False
                
            action_name = parsed.get("action")
            if action_name == "respond":
                # Executable intents must not return simple responses
                if is_executable:
                    return False
                return True
                
            # Perform exact schema validation
            valid, reason = validate(parsed)
            if not valid:
                logger.warning("Local result failed exact schema validation: %s", reason)
                return False
                
            # Additional check: make sure the intent family matches the action type
            if intent_family == "AUTOMATION":
                # Must be a browser/system automation tool call
                tools = []
                if action_name == "tool_call":
                    tools.append(parsed.get("tool_name"))
                elif action_name == "multi_tool_call":
                    for t in parsed.get("tools", []):
                        if isinstance(t, dict):
                            tools.append(t.get("tool_name"))
                else:
                    tools.append(action_name)
                
                automation_tool_prefixes = ("browser_", "system_", "calendar_", "gmail_")
                if not tools or not all(isinstance(t, str) and t.startswith(automation_tool_prefixes) for t in tools):
                    return False
                    
            elif intent_family == "PROJECT_CREATION":
                tools = []
                if action_name == "tool_call":
                    tools.append(parsed.get("tool_name"))
                elif action_name == "multi_tool_call":
                    for t in parsed.get("tools", []):
                        if isinstance(t, dict):
                            tools.append(t.get("tool_name"))
                else:
                    tools.append(action_name)
                
                # Project creation must use scaffold, project, or file_write tools
                proj_tools = {"scaffold", "project", "file_write"}
                if not tools or not all(isinstance(t, str) and t in proj_tools for t in tools):
                    return False
                    
            return True
        except Exception as e:
            logger.warning("Error during exact local validation: %s", e)
            return False
