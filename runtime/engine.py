import concurrent.futures

from core.gateway import GatewayPermissionDenied, SafetyViolationError
from core.exceptions import ToolTimeoutError
from core.gateway import ToolGatewayCore
from runtime.action_schema import validate_action, validate_tool_result
from runtime.browser_automation import BrowserAutomation
from runtime.page_fetcher import PageFetchTool
from runtime.retry_policy import retry_policy
from runtime.scaffold_engine import ScaffoldEngine
from runtime.web_access import WebAccessTool
from runtime.world_state import world_state


class ExecutionEngine:
    def __init__(self):
        self._tools = {
            "browser": BrowserAutomation(),
            "scaffold": ScaffoldEngine(),
            "web_access": WebAccessTool(),
            "page_fetcher": PageFetchTool(),
        }
        self.gateway = ToolGatewayCore()

    def set_gateway_callback(self, callback):
        self.gateway.set_permission_callback(callback)

    def register_tools(self, tools: dict):
        for name, tool in tools.items():
            # Protect the real BrowserAutomation from being replaced by
            # any other browser implementation (e.g. BrowserTools).
            if name == "browser" and isinstance(self._tools.get("browser"), BrowserAutomation):
                if not isinstance(tool, BrowserAutomation):
                    continue
            self._tools[name] = tool

    def execute(self, tool_name: str, parameters: dict) -> dict:
        params = dict(parameters or {})
        is_valid, reason = validate_action(tool_name, params)
        if not is_valid:
            return {"status": "error", "error": reason}
        base = self._base_for_tool(tool_name)
        tool = self._tools.get(base)
        if not tool:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
        params = {**params, "_tool_name": tool_name}
        try:
            if params.get("_sandbox_mode") is True:
                self.gateway.validate_safety(base, params)
            else:
                self.gateway.validate_and_request_permission(base, params)
                params["_gateway_approved"] = True
        except GatewayPermissionDenied as exc:
            result = {"status": "cancelled", "reason": "user_denied", "error": str(exc)}
            world_state.record_tool_result(tool_name, result)
            return result
        except SafetyViolationError as exc:
            result = {"status": "error", "error": str(exc), "classification": "safety_violation"}
            world_state.record_tool_result(tool_name, result)
            return result
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
            world_state.record_tool_result(tool_name, result)
            return result
        if base == "browser":
            result = self._execute_browser_with_recovery(tool, tool_name, params)
            valid_result, result_reason = validate_tool_result(tool_name, result)
            if not valid_result:
                result = {"status": "error", "error": result_reason}
            world_state.record_tool_result(tool_name, result)
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(tool.execute, params)
            timeout_seconds = 120 if tool_name == "browser_act" else 30
            try:
                result = fut.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                timeout = ToolTimeoutError(f"{tool_name} exceeded {timeout_seconds}s timeout")
                result = {"status": "error", "error": str(timeout), "classification": "timeout"}
                world_state.record_tool_result(tool_name, result)
                return result
            except Exception as exc:
                result = {"status": "error", "error": str(exc)}
        valid_result, result_reason = validate_tool_result(tool_name, result)
        if not valid_result:
            result = {"status": "error", "error": result_reason}
        world_state.record_tool_result(tool_name, result)
        return result

    def _execute_browser_with_recovery(self, tool, tool_name: str, params: dict) -> dict:
        last_result: dict | None = None
        for attempt in range(retry_policy.max_browser_attempts):
            try:
                result = tool.execute(params)
            except Exception as exc:
                decision = retry_policy.decide(tool_name, attempt, exc=exc)
                if not decision.retry:
                    return {
                        "status": "error",
                        "error": str(exc),
                        "attempts": attempt + 1,
                        "classification": decision.reason,
                    }
                retry_policy.sleep(decision)
                self._recover_browser_sessions()
                continue

            if result.get("status") in {"success", "cancelled"}:
                result.setdefault("attempts", attempt + 1)
                return result
            last_result = result
            decision = retry_policy.decide(tool_name, attempt, result=result)
            if not decision.retry:
                result.setdefault("attempts", attempt + 1)
                result.setdefault("classification", decision.reason)
                return result
            retry_policy.sleep(decision)
            self._recover_browser_sessions()

        if isinstance(last_result, dict):
            last_result.setdefault("attempts", retry_policy.max_browser_attempts)
            last_result.setdefault("classification", "retry_ceiling_reached")
            return last_result
        return {"status": "error", "error": "Browser execution failed", "attempts": retry_policy.max_browser_attempts}

    def _recover_browser_sessions(self) -> None:
        try:
            from runtime.browser_session import SessionRegistry

            SessionRegistry.close_all()
        except Exception:
            return

    def get_system_prompt(self) -> str:
        registered = ", ".join(sorted(self._tools.keys()))
        return (
            "You are M.A.Y.D.A.Y Phase 6a. For executable requests, return exactly one "
            "raw JSON object and no markdown. Use this shape: "
            '{"action":"tool_call","tool_name":"file_write","parameters":{"path":"relative/or/absolute/path","content":"text"}}. '
            "Available browser tools: \n"
            "1) browser_open(url: str) - Opens the visible browser to a URL.\n"
            "2) browser_click(selector: str) - Clicks an element by selector.\n"
            "3) browser_type(selector: str, text: str) - Clicks, clears, and types text into a selector field.\n"
            "4) browser_act(steps: list[dict]) - Runs sequential steps like: [{'action': 'open', 'url': '...'}, {'action': 'wait_for', 'selector': '...'}, {'action': 'click', 'selector': '...'}, {'action': 'type', 'selector': '...', 'value': '...'}]\n"
            "5) browser_get_text(selector: str='body') extracts visible text and links; browser_screenshot captures the active tab.\n"
            "Browser selectors may be CSS selectors or semantic targets such as 'search bar', 'email field', 'first result', or 'New meeting'; the browser tool will resolve dynamic DOM targets adaptively.\n"
            "For Google Meet, use browser_act steps for New meeting/Create a meeting for later, then a get_text or extract_meet_link step and return only a verified meet.google.com URL.\n"
            "When typing, put only the intended field contents in text/value. Do not include instructions like 'in the search bar', 'then click', or 'press enter' inside the typed text.\n"
            "Use shell_run for commands, web_search for search queries, web_fetch for URLs, and scaffold_engine for projects.\n"
            "To perform multiple sequential actions (e.g., writing files/projects and then executing/running them with shell_run), always return a single 'multi_tool_call' containing all the required tool calls in sequence so they can execute together.\n"
            "When creating applications that require images or assets (like games), write Python code that programmatically draws or generates placeholders (e.g., using QPainter, solid colors, or QImage) inside the script. NEVER output large base64 strings or binary contents in your response, as it will exceed output token limits and truncate your response.\n"
            "Registered tool bases: "
            f"{registered}. Do not repeat an identical tool action after a tool result."
        )

    def _base_for_tool(self, tool_name: str) -> str:
        base = tool_name.split("_", 1)[0]
        if base == "shell" and "shell" not in self._tools and "powershell" in self._tools:
            return "powershell"
        if tool_name == "server_runner":
            return "server"
        if tool_name == "web_search":
            return "web_access"
        if tool_name == "web_fetch":
            return "page_fetcher"
        return base
