import concurrent.futures
from datetime import datetime
from pathlib import Path

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
from tools.excel_tools import ExcelTools
from tools.calendar_tools import CalendarTools
from tools.gmail_tools import GmailTools


TASK_COMPLETION_GUIDE = """
=== TASK COMPLETION RULES - READ BEFORE EVERY ACTION ===

FOR SEARCH TASKS ("search for X", "find X", "look up X"):
  REQUIRED STEPS, do not stop early:
  1. browser_open(url)
  2. browser_click(search_box)
  3. browser_type(query)
  4. browser_press_key("Enter") - DO NOT SKIP
  5. browser_wait_for_navigation() - DO NOT SKIP
  6. browser_get_text()
  7. respond(summary of actual results) - task is done here, not before.
  WRONG: stopping after browser_type. WRONG: returning after browser_open.

FOR YOUTUBE ("play X on YouTube"):
  1. browser_open("https://www.youtube.com")
  2. browser_click("input#search")
  3. browser_type(song_name, "input#search")
  4. browser_press_key("Enter")
  5. browser_wait_for_navigation()
  6. browser_click("ytd-video-renderer:first-of-type h3 a")
  7. respond("Now playing: [title from page.title()]")

FOR EMAIL ("read emails", "check inbox"):
  IF OAuth set up: gmail_get_unread() -> respond(summary)
  IF OAuth error on first occurrence: use browser Gmail fallback -> respond with email summary plus setup instructions.
  WRONG: retrying gmail_get_unread after a credentials error.

FOR CALENDAR ("create meeting", "schedule event"):
  IF OAuth set up: calendar_create_event() -> respond(confirmation)
  IF OAuth not set up: calendar_create_event_via_browser() -> respond("Please click Save")

FOR FILE CREATION ("create document", "write a file", "make a table"):
  1. If research is needed, web_search(topic)
  2. Generate full content: 300+ words for docs, full table for comparisons.
  3. file_write(path, content) - content must be non-empty and over 50 chars.
  4. respond(confirmation plus file path) - task is done here.
  WRONG: file_write with empty content. WRONG: stopping after web_search.

FOR WHATSAPP ("send WhatsApp message to X"):
  1. browser_open("https://web.whatsapp.com")
  2. browser_wait_for_element('[data-testid="side"]', 15000)
  3. Search for contact and click contact.
  4. browser_click('[data-testid="conversation-compose-box-input"]')
  5. browser_type(message)
  6. browser_press_key("Enter")
  7. respond("Message sent to [contact]: [message]")
  NOTE: First use requires QR code scan. After that sessions persist.

HARDWARE RULES:
  For any question about GPUs, CPUs, phones, laptops, or other hardware, always call web_search first with the current year in the query.
  If the user says "50 series", use exactly "50 series" in the web_search query.
  Never recommend a previous generation when the user specifies a current one.

CURRENT DATE/TIME: {current_datetime}
Calculate "tomorrow", "next Friday", and similar relative dates from the above.
===
""".strip()


class ExecutionEngine:
    def __init__(self):
        self._tools = {
            "browser": BrowserAutomation(),
            "excel": ExcelTools(),
            "scaffold": ScaffoldEngine(),
            "web_access": WebAccessTool(),
            "page_fetcher": PageFetchTool(),
            "calendar": CalendarTools(),
            "gmail": GmailTools(),
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
            timeout_seconds = 30
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
        from runtime.execution_registry import KNOWN_TOOLS

        registered = ", ".join(sorted(KNOWN_TOOLS))
        current_time = datetime.now().astimezone().isoformat(timespec="seconds")
        task_guide = TASK_COMPLETION_GUIDE.format(current_datetime=current_time)
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        return (
            "You are M.A.Y.D.A.Y Phase 6a. For executable requests, return exactly one "
            "raw JSON object and no markdown. Use this shape: "
            '{"action":"tool_call","tool_name":"file_write","parameters":{"path":"relative/or/absolute/path","content":"text"}}. '
            f"Current local datetime: {current_time}. Use explicit ISO datetimes for Calendar. "
            f"Python helper scripts should live under {scripts_dir}. "
            "Available browser tools: \n"
            "1) browser_open(url: str) - Opens the visible browser to a URL.\n"
            "2) browser_click(selector: str) - Clicks an element by selector.\n"
            "3) browser_type(selector: str, text: str) - Clicks, clears, and types text into a selector field.\n"
            "4) browser_press_key(key: str='Enter') - Presses a keyboard key in the active browser page.\n"
            "5) browser_wait(selector: str, timeout_ms: int=10000) - Waits for a visible element.\n"
            "6) browser_wait_for_navigation(timeout_ms: int=5000) - Waits for page load after Enter/click navigation.\n"
            "7) browser_wait_for_element(selector: str, timeout_ms: int=10000) - Alias for waiting on a visible element.\n"
            "8) browser_get_text(selector: str='body') - Extracts text and links from the current page.\n"
            "9) browser_get_page_content(url: str, selector: str='body') - Opens a URL and extracts readable page content in one atomic step.\n"
            "10) browser_screenshot(path: str optional) - Saves a screenshot of the current page.\n"
            "11) browser_verify(condition: str) - Verifies current page URL/title/text/selector state.\n"
            "12) browser_scroll(direction: str='down', pixels: int=500) - Scrolls the active page.\n"
            "13) browser_close() - Closes the active browser session.\n"
            "Browser selectors may be CSS selectors or semantic targets such as 'search bar', 'email field', 'first result', or 'New meeting'; the browser tool will resolve dynamic DOM targets adaptively.\n"
            "Never output browser_act, browser_chain, browser_multi, or semantic pseudo-actions; only registered atomic tools are executable.\n"
            "When typing, put only the intended field contents in text/value. Do not include instructions like 'in the search bar', 'then click', or 'press enter' inside the typed text.\n"
            "Use shell_run for commands, web_search for search queries, web_fetch for URLs, file_write with non-empty content or explicit blank_* template, excel_create for tabular .xlsx files, calendar_create_event/calendar_list_events for Calendar, gmail_get_unread/gmail_get_email_body for Gmail, and scaffold for explicit multi-file projects with project_name, stack, and files.\n"
            "Return one atomic tool_call per step, then wait for the tool result before deciding the next action. Do not produce multi-tool plans unless the executor explicitly requests a compatibility fallback.\n"
            "For calendar_create_event, title and start_datetime are required; end_datetime is optional and defaults to one hour after start when omitted.\n"
            "When creating applications that require images or assets (like games), write Python code that programmatically draws or generates placeholders (e.g., using QPainter, solid colors, or QImage) inside the script. NEVER output large base64 strings or binary contents in your response, as it will exceed output token limits and truncate your response.\n"
            "Registered atomic tools: "
            f"{registered}. Do not repeat an identical tool action after a tool result.\n\n"
            f"{task_guide}"
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
        if tool_name.startswith("calendar_"):
            return "calendar"
        if tool_name.startswith("gmail_"):
            return "gmail"
        return base
