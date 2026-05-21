"""
M.A.Y.D.A.Y Model Router — v6.0 Stabilized Routing
=====================================================
v6.0 changes:
- E103: Microstep extraction for local AUTOMATION responses
- E104: Provider cooldown integration (respects Retry-After)
- E105: Context trimming for local model (max 2000 chars)
- E107: Escalation circuit breaker (prevents local↔API ping-pong)
"""
import concurrent.futures
import gc
import json
import logging
import os
import time

import psutil

from core.exceptions import PermissionDeniedError, ProviderFailureError, InferenceTimeoutError
from core.intent_router import classify, is_executable_intent
from runtime.provider_cooldown import provider_cooldown

logger = logging.getLogger("mayday.router")

LOCAL_TIMEOUT_WITH_API = 90
LOCAL_TIMEOUT_NO_API = 180
COMPLEXITY_THRESHOLD = 0.35
API_FIRST_COMPLEX_FAMILIES = {"PROJECT_CREATION", "AUTOMATION"}

# E105: Max chars for context fed to local model
LOCAL_CONTEXT_CHAR_LIMIT = 2000

# E107: Circuit breaker — if both providers fail within this window, pause
CIRCUIT_BREAKER_WINDOW = 60  # seconds
CIRCUIT_BREAKER_MAX_FAILURES = 3


class TaskComplexityAnalyzer:
    def score(self, prompt: str) -> float:
        if is_executable_intent(prompt):
            return 1.0
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


class ModelRouter:
    def __init__(self, inference_engine, api_manager=None):
        self.inference = inference_engine
        self.api = api_manager
        self.analyzer = TaskComplexityAnalyzer()
        self._last_provider = "local"
        self._route_log: list[dict] = []
        self._breaker = _EscalationCircuitBreaker()

    def route(self, prompt, context: str = "") -> tuple[str, str]:
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
        api_provider_name = self.api.active_provider_name() if self.api else "none"

        # Helper to dynamically check if API is currently ready
        def is_api_currently_available() -> bool:
            if not has_api:
                return False
            if not provider_cooldown.is_cooled_down(api_provider_name):
                remaining = provider_cooldown.seconds_remaining(api_provider_name)
                logger.info(
                    "API provider %s is on cooldown (%.1fs remaining)",
                    api_provider_name, remaining
                )
                return False
            return True

        # ── API-first for complex executable tasks ───────────────────
        if is_api_currently_available() and is_executable_intent(prompt) and intent_family in API_FIRST_COMPLEX_FAMILIES:
            try:
                logger.info("Complex executable %s routed directly to approved API provider", intent_family)
                result = self._call_api(api_messages, prompt, context)
                provider = self.api.active_provider_name()
                self._last_provider = provider
                log_entry.update({"provider": provider, "reason": "api_first_complex_executable"})
                self._route_log.append(log_entry)
                self._breaker.reset()
                return result, provider
            except PermissionDeniedError:
                log_entry.update({"provider": "api_blocked", "reason": "approval_required"})
                self._route_log.append(log_entry)
                raise
            except ProviderFailureError as e:
                self._handle_api_failure(e, api_provider_name)
                gc.collect()

        # ── Complex tasks — timeout-based local routing ──────────────
        timeout = LOCAL_TIMEOUT_WITH_API if has_api else LOCAL_TIMEOUT_NO_API

        # E105: Trim context for local model
        trimmed_context = self._trim_context_for_local(context)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self.inference.generate, prompt, trimmed_context)
            try:
                result = future.result(timeout=timeout)
                
                # Rigid exact structural and payload auditing
                is_exec = is_executable_intent(prompt)
                if not self._validate_local_result(result, intent_family, is_exec):
                    logger.warning("Local model generated invalid/hallucinated response for %s, escalating", intent_family)
                    raise concurrent.futures.TimeoutError("Forced escalation due to invalid/hallucinated local tool schema")

                # E103: Microstep enforcement for local AUTOMATION responses
                if intent_family == "AUTOMATION":
                    result = self._enforce_microstep(result)

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
                future.cancel()
                logger.warning("Local timed out or generated invalid layout — DESTROYING model before escalation")
                self._breaker.record_failure("local")
                # CRITICAL: Destroy model on timeout (no zombie models)
                try:
                    if hasattr(self.inference, "destroy_model"):
                        self.inference.destroy_model()
                    elif getattr(self.inference, "loader", None) is not None:
                        self.inference.loader.destroy_model()
                except Exception as e:
                    logger.error("Model destroy on timeout failed: %s", e)
                gc.collect()
            except Exception as e:
                logger.warning("Local model threw exception: %s. Escalating to API.", e)
                self._breaker.record_failure("local")
                gc.collect()

        # ── API escalation ───────────────────────────────────────────
        if is_api_currently_available():
            try:
                result = self._call_api(api_messages, prompt, context)
                logger.info("API ESCALATION SUCCESS.")
                provider = self.api.active_provider_name()
                self._last_provider = provider
                log_entry.update({"provider": provider, "reason": "api_escalation"})
                self._route_log.append(log_entry)
                self._breaker.reset()
                return result, provider
            except PermissionDeniedError:
                log_entry.update({"provider": "api_blocked", "reason": "approval_required"})
                self._route_log.append(log_entry)
                raise
            except ProviderFailureError as e:
                self._handle_api_failure(e, api_provider_name)

        # ── Final fallback — reload model (only if breaker not tripped) ─
        if self._breaker.is_tripped():
            msg = "All providers temporarily unavailable. Please retry in 30 seconds."
            log_entry.update({"provider": "exhausted", "reason": "circuit_breaker"})
            self._route_log.append(log_entry)
            return json.dumps({"action": "respond", "text": msg}), "exhausted"

        logger.info("Reloading model for final fallback attempt...")
        if getattr(self.inference, "loader", None) is None:
            raise InferenceTimeoutError("Local fallback unavailable: inference loader is not configured")
        self.inference.loader.load_best_available()

        # E105: Use trimmed context for fallback too
        result = self.inference.generate(prompt, trimmed_context)

        # E103: Microstep enforcement for local fallback
        if intent_family == "AUTOMATION":
            result = self._enforce_microstep(result)

        self._last_provider = "local_fallback"
        log_entry.update({"provider": "local_fallback", "reason": "all_failed"})
        self._route_log.append(log_entry)
        gc.collect()
        return result, "local_fallback"

    def _call_api(self, api_messages, prompt: str, context: str) -> str:
        """Unified API call with cooldown-aware error handling."""
        if api_messages is not None and hasattr(self.api, "complete_messages"):
            return self.api.complete_messages(api_messages)
        return self.api.complete(prompt, context)

    def _handle_api_failure(self, error: ProviderFailureError, provider_name: str) -> None:
        """Record API failure and update cooldown if rate-limited (E104)."""
        from runtime.provider_clients.openai_compatible_client import RateLimitError

        self._breaker.record_failure("api")

        if isinstance(error, RateLimitError):
            provider_cooldown.record_rate_limit(provider_name, error.retry_after)
            logger.warning(
                "API rate-limited: cooldown %.1fs for %s",
                error.retry_after, provider_name,
            )
        else:
            logger.warning("API provider failed: %s. Falling back.", error)

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

            # If it's a multi_tool_call or browser_act with many steps, reduce
            if action == "multi_tool_call":
                tools = parsed.get("tools", [])
                if len(tools) > 2:
                    logger.info("Microstep: reducing multi_tool_call from %d to 1 step", len(tools))
                    parsed["tools"] = tools[:1]
                    return json.dumps(parsed)

            if action == "browser_act":
                steps = parsed.get("parameters", {}).get("steps", [])
                if not steps:
                    steps = parsed.get("steps", [])
                if len(steps) > 2:
                    logger.info("Microstep: reducing browser_act from %d to 2 steps", len(steps))
                    if "parameters" in parsed and "steps" in parsed["parameters"]:
                        parsed["parameters"]["steps"] = steps[:2]
                    elif "steps" in parsed:
                        parsed["steps"] = steps[:2]
                    return json.dumps(parsed)

        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        return raw

    def get_last_provider(self) -> str:
        return self._last_provider

    def get_route_log(self) -> list[dict]:
        return list(self._route_log)

    def _split_messages(self, messages: list[dict]) -> tuple[str, str]:
        latest_user = ""
        context_parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            if role == "user":
                latest_user = content
            elif content:
                context_parts.append(f"{role}: {content}")

        # E105: Trim context for _split_messages path
        raw_context = "\n".join(context_parts)
        if len(raw_context) > LOCAL_CONTEXT_CHAR_LIMIT:
            raw_context = raw_context[-LOCAL_CONTEXT_CHAR_LIMIT:]
            boundary = raw_context.find("\n")
            if 0 < boundary < 200:
                raw_context = raw_context[boundary + 1:]
            raw_context = "[earlier context trimmed]\n" + raw_context

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
                
                # All tools in the automation intent must start with browser_ or system_
                if not tools or not all(isinstance(t, str) and (t.startswith("browser_") or t.startswith("system_")) for t in tools):
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
                proj_tools = {"scaffold", "scaffold_engine", "project", "file_write"}
                if not tools or not all(isinstance(t, str) and t in proj_tools for t in tools):
                    return False
                    
            return True
        except Exception as e:
            logger.warning("Error during exact local validation: %s", e)
            return False
