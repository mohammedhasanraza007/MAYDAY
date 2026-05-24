from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


SchemaValidator = Callable[[dict[str, Any]], tuple[bool, str]]
FILE_WRITE_TEMPLATES = frozenset({"blank_xlsx", "blank_csv", "blank_json", "blank_txt"})


@dataclass(frozen=True)
class ToolContract:
    name: str
    capability: str
    atomic: bool
    validator: SchemaValidator
    max_chain: int = 1


def _ok(_: dict[str, Any]) -> tuple[bool, str]:
    return True, ""


def _non_empty_string(field: str) -> SchemaValidator:
    def validate(parameters: dict[str, Any]) -> tuple[bool, str]:
        value = parameters.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, f"{field} must be a non-empty string"
        return True, ""

    return validate


def _path_like(*fields: str) -> SchemaValidator:
    def validate(parameters: dict[str, Any]) -> tuple[bool, str]:
        for field in fields:
            value = parameters.get(field)
            if isinstance(value, str) and value.strip():
                return True, ""
        return False, f"one of {', '.join(fields)} must be a non-empty string"

    return validate


def _browser_type(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("selector")(parameters)
    if not valid:
        return valid, reason
    if not isinstance(parameters.get("text"), str):
        return False, "text must be a string"
    return True, ""


def _browser_click(parameters: dict[str, Any]) -> tuple[bool, str]:
    selector = parameters.get("selector")
    if isinstance(selector, str) and selector.strip():
        return True, ""
    x = parameters.get("x")
    y = parameters.get("y")
    if isinstance(x, int) and isinstance(y, int):
        return True, ""
    return False, "browser_click requires selector or integer x,y coordinates"


def _browser_wait(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("selector")(parameters)
    if not valid:
        return valid, reason
    timeout_ms = parameters.get("timeout_ms", parameters.get("timeout", 10000))
    if not isinstance(timeout_ms, int) or timeout_ms <= 0 or timeout_ms > 30000:
        return False, "timeout_ms must be an integer between 1 and 30000"
    return True, ""


def _browser_get_text(parameters: dict[str, Any]) -> tuple[bool, str]:
    selector = parameters.get("selector", "body")
    if not isinstance(selector, str) or not selector.strip():
        return False, "selector must be a non-empty string when provided"
    return True, ""


def _browser_get_page_content(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("url")(parameters)
    if not valid:
        return valid, reason
    selector = parameters.get("selector", "body")
    if selector is not None and (not isinstance(selector, str) or not selector.strip()):
        return False, "selector must be a non-empty string when provided"
    return True, ""


def _browser_verify(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("condition")(parameters)
    if not valid:
        return valid, reason
    return True, ""


def _browser_screenshot(parameters: dict[str, Any]) -> tuple[bool, str]:
    path = parameters.get("path")
    if path is not None and not isinstance(path, str):
        return False, "path must be a string when provided"
    return True, ""


def _calendar_create_event(parameters: dict[str, Any]) -> tuple[bool, str]:
    for field in ("title", "start_datetime"):
        valid, reason = _non_empty_string(field)(parameters)
        if not valid:
            return valid, reason
    end_datetime = parameters.get("end_datetime")
    if end_datetime is not None and (not isinstance(end_datetime, str) or not end_datetime.strip()):
        return False, "end_datetime must be a non-empty string when provided"
    attendees = parameters.get("attendees", [])
    if attendees is not None and not isinstance(attendees, list):
        return False, "attendees must be a list when provided"
    return True, ""


def _calendar_list_events(parameters: dict[str, Any]) -> tuple[bool, str]:
    days_ahead = parameters.get("days_ahead", 7)
    max_results = parameters.get("max_results", 10)
    if not isinstance(days_ahead, int) or days_ahead < 1 or days_ahead > 365:
        return False, "days_ahead must be an integer between 1 and 365"
    if not isinstance(max_results, int) or max_results < 1 or max_results > 50:
        return False, "max_results must be an integer between 1 and 50"
    return True, ""


def _gmail_get_unread(parameters: dict[str, Any]) -> tuple[bool, str]:
    max_results = parameters.get("max_results", 10)
    if not isinstance(max_results, int) or max_results < 1 or max_results > 50:
        return False, "max_results must be an integer between 1 and 50"
    for field in ("sender_filter", "subject_filter"):
        value = parameters.get(field, "")
        if value is not None and not isinstance(value, str):
            return False, f"{field} must be a string when provided"
    return True, ""


def _gmail_get_email_body(parameters: dict[str, Any]) -> tuple[bool, str]:
    return _non_empty_string("email_id")(parameters)


def _browser_scroll(parameters: dict[str, Any]) -> tuple[bool, str]:
    amount = parameters.get("amount", parameters.get("delta_y", 600))
    if not isinstance(amount, int):
        return False, "amount must be an integer"
    if abs(amount) > 5000:
        return False, "amount must be between -5000 and 5000"
    return True, ""


def _file_write(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _path_like("path", "file_path")(parameters)
    if not valid:
        return valid, reason
    template = parameters.get("template")
    if template is not None:
        if template not in FILE_WRITE_TEMPLATES:
            return False, "template must be one of blank_xlsx, blank_csv, blank_json, blank_txt"
        return True, ""
    if not isinstance(parameters.get("content"), str):
        return False, "content must be a string unless template is provided"
    if not parameters.get("content", "").strip():
        return False, "content must be a non-empty string unless template is provided"
    return True, ""


def _excel_data(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _path_like("path", "file_path")(parameters)
    if not valid:
        return valid, reason
    data = parameters.get("data", [])
    if not isinstance(data, list):
        return False, "data must be a list of rows"
    for row_index, row in enumerate(data):
        if not isinstance(row, list):
            return False, f"data[{row_index}] must be a list"
    sheet = parameters.get("sheet", "Sheet1")
    if sheet is not None and not isinstance(sheet, str):
        return False, "sheet must be a string when provided"
    return True, ""


def _scaffold(parameters: dict[str, Any]) -> tuple[bool, str]:
    for field in ("project_name", "stack", "files"):
        if field not in parameters:
            return False, f"Missing required field: {field}"
    if not isinstance(parameters["project_name"], str) or not parameters["project_name"].strip():
        return False, "project_name must be a non-empty string"
    if not isinstance(parameters["stack"], str) or not parameters["stack"].strip():
        return False, "stack must be a non-empty string"
    files = parameters["files"]
    if not isinstance(files, list) or not files:
        return False, "files must be a non-empty list"
    for index, file_spec in enumerate(files):
        if not isinstance(file_spec, dict):
            return False, f"files[{index}] must be an object"
        if not isinstance(file_spec.get("path"), str) or not file_spec["path"].strip():
            return False, f"files[{index}].path must be a non-empty string"
        if not isinstance(file_spec.get("content"), str):
            return False, f"files[{index}].content must be a string"
    return True, ""


def _powershell_python_script(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("script_path")(parameters)
    if not valid:
        return valid, reason
    args = parameters.get("args", [])
    if not isinstance(args, list):
        return False, "args must be a list"
    return True, ""


def _server_launch(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _path_like("project_dir", "path")(parameters)
    if not valid:
        return valid, reason
    stack = parameters.get("stack", "flask")
    if not isinstance(stack, str) or not stack.strip():
        return False, "stack must be a non-empty string"
    return True, ""


def _system_click(parameters: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(parameters.get("x"), int) or not isinstance(parameters.get("y"), int):
        return False, "x and y must be integers"
    return True, ""


def _system_hotkey(parameters: dict[str, Any]) -> tuple[bool, str]:
    keys = parameters.get("keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(key, str) and key for key in keys):
        return False, "keys must be a non-empty list of strings"
    return True, ""


def _web_search(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("query")(parameters)
    if not valid:
        return valid, reason
    provider = parameters.get("provider")
    if provider is not None and not isinstance(provider, str):
        return False, "provider must be a string when provided"
    return True, ""


def _web_fetch(parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = _non_empty_string("url")(parameters)
    if not valid:
        return valid, reason
    extract = parameters.get("extract")
    if extract is not None and not isinstance(extract, str):
        return False, "extract must be a string when provided"
    return True, ""


BROWSER_ATOMIC_TOOLS = frozenset(
    {
        "browser_open",
        "browser_click",
        "browser_type",
        "browser_wait",
        "browser_wait_for_element",
        "browser_get_text",
        "browser_get_page_content",
        "browser_screenshot",
        "browser_verify",
        "browser_close",
        "browser_scroll",
    }
)

PLANNER_PSEUDO_TOOLS = frozenset(
    {
        "browser_act",
        "browser_chain",
        "browser_multi",
        "browser_sequence",
        "browser_plan",
        "browser_steps",
        "multi_browser",
        "automation_chain",
    }
)

_CONTRACTS: dict[str, ToolContract] = {
    "browser_open": ToolContract("browser_open", "internet_only", True, _non_empty_string("url")),
    "browser_click": ToolContract("browser_click", "internet_only", True, _browser_click),
    "browser_type": ToolContract("browser_type", "internet_only", True, _browser_type),
    "browser_wait": ToolContract("browser_wait", "internet_only", True, _browser_wait),
    "browser_wait_for_element": ToolContract("browser_wait_for_element", "internet_only", True, _browser_wait),
    "browser_get_text": ToolContract("browser_get_text", "internet_only", True, _browser_get_text),
    "browser_get_page_content": ToolContract("browser_get_page_content", "internet_only", True, _browser_get_page_content),
    "browser_screenshot": ToolContract("browser_screenshot", "internet_only", True, _browser_screenshot),
    "browser_verify": ToolContract("browser_verify", "internet_only", True, _browser_verify),
    "browser_close": ToolContract("browser_close", "internet_only", True, _ok),
    "browser_scroll": ToolContract("browser_scroll", "internet_only", True, _browser_scroll),
    "calendar_create_event": ToolContract("calendar_create_event", "internet_only", True, _calendar_create_event),
    "calendar_list_events": ToolContract("calendar_list_events", "internet_only", True, _calendar_list_events),
    "excel_create": ToolContract("excel_create", "sandbox_only", True, _excel_data),
    "excel_read": ToolContract("excel_read", "sandbox_only", True, _path_like("path", "file_path")),
    "excel_write": ToolContract("excel_write", "sandbox_only", True, _excel_data),
    "file_delete": ToolContract("file_delete", "sandbox_only", True, _path_like("path", "file_path")),
    "file_list": ToolContract("file_list", "sandbox_only", True, _path_like("path", "directory")),
    "file_read": ToolContract("file_read", "sandbox_only", True, _path_like("path", "file_path")),
    "file_write": ToolContract("file_write", "sandbox_only", True, _file_write),
    "gmail_get_unread": ToolContract("gmail_get_unread", "internet_only", True, _gmail_get_unread),
    "gmail_get_email_body": ToolContract("gmail_get_email_body", "internet_only", True, _gmail_get_email_body),
    "powershell_python_script": ToolContract("powershell_python_script", "restricted", True, _powershell_python_script),
    "powershell_run": ToolContract("powershell_run", "restricted", True, _non_empty_string("command")),
    "project": ToolContract("project", "sandbox_only", True, _scaffold),
    "scaffold": ToolContract("scaffold", "sandbox_only", True, _scaffold),
    "scaffold_engine": ToolContract("scaffold_engine", "sandbox_only", True, _scaffold),
    "server_launch": ToolContract("server_launch", "restricted", True, _server_launch),
    "server_runner": ToolContract("server_runner", "restricted", True, _server_launch),
    "server_status": ToolContract("server_status", "restricted", True, _path_like("project_dir", "path")),
    "server_stop": ToolContract("server_stop", "restricted", True, _path_like("project_dir", "path")),
    "shell_run": ToolContract("shell_run", "restricted", True, _non_empty_string("command")),
    "system_click": ToolContract("system_click", "restricted", True, _system_click),
    "system_hotkey": ToolContract("system_hotkey", "restricted", True, _system_hotkey),
    "system_info": ToolContract("system_info", "restricted", True, _ok),
    "system_screenshot": ToolContract("system_screenshot", "restricted", True, _ok),
    "system_type": ToolContract("system_type", "restricted", True, _non_empty_string("text")),
    "web_fetch": ToolContract("web_fetch", "internet_only", True, _web_fetch),
    "web_search": ToolContract("web_search", "internet_only", True, _web_search),
}

REGISTERED_TOOLS: Mapping[str, ToolContract] = MappingProxyType(_CONTRACTS)
KNOWN_TOOLS = frozenset(_CONTRACTS)


def validate_tool_name(tool_name: str) -> tuple[bool, str]:
    if not isinstance(tool_name, str) or not tool_name.strip():
        return False, "tool_name must be a non-empty string"
    if tool_name not in REGISTERED_TOOLS:
        return False, f"Unknown or uncontracted tool: {tool_name}"
    return True, ""


def validate_payload(tool_name: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    valid, reason = validate_tool_name(tool_name)
    if not valid:
        return valid, reason
    if not isinstance(parameters, dict):
        return False, "parameters must be an object"
    return REGISTERED_TOOLS[tool_name].validator(parameters)


def validate_capability(tool_name: str, intent_family: str) -> tuple[bool, str]:
    valid, reason = validate_tool_name(tool_name)
    if not valid:
        return valid, reason
    capability = REGISTERED_TOOLS[tool_name].capability
    allowed_by_family = {
        "WEB_ACCESS": {"internet_only"},
        "PROJECT_CREATION": {"sandbox_only", "restricted", "internet_only"},
        "EXECUTION": {"sandbox_only", "restricted", "internet_only"},
        "AUTOMATION": {"internet_only"},
        "FILE_OPS": {"sandbox_only", "restricted"},
    }
    allowed = allowed_by_family.get(intent_family, set())
    if capability not in allowed:
        return False, f"{tool_name} capability {capability} is not allowed for {intent_family}"
    return True, ""


def structural_validate(action: Any) -> tuple[bool, str]:
    """Validate JSON shape before translation without accepting runtime names."""
    if not isinstance(action, dict):
        return False, "action must be an object"
    action_name = action.get("action")
    if not isinstance(action_name, str) or not action_name.strip():
        return False, "action must be a non-empty string"
    if action_name == "respond":
        text = action.get("text", action.get("response", action.get("content", "")))
        return (True, "") if isinstance(text, str) else (False, "respond text must be a string")
    if action_name == "tool_call":
        if not isinstance(action.get("tool_name"), str) or not action["tool_name"].strip():
            return False, "tool_call.tool_name must be a non-empty string"
        if not isinstance(action.get("parameters"), dict):
            return False, "tool_call.parameters must be an object"
        return True, ""
    if action_name == "multi_tool_call":
        tools = action.get("tools", action.get("tool_calls", action.get("steps")))
        if not isinstance(tools, list) or not tools:
            return False, "multi_tool_call tools must be a non-empty list"
        for index, entry in enumerate(tools):
            if not isinstance(entry, dict):
                return False, f"multi_tool_call.tools[{index}] must be an object"
            if not isinstance(entry.get("tool_name", entry.get("name", entry.get("tool"))), str):
                return False, f"multi_tool_call.tools[{index}].tool_name must be a string"
            params = entry.get("parameters", entry.get("args", {}))
            if not isinstance(params, dict):
                return False, f"multi_tool_call.tools[{index}].parameters must be an object"
        return True, ""
    if action_name in PLANNER_PSEUDO_TOOLS:
        parameters = action.get("parameters")
        steps = action.get("steps")
        if isinstance(parameters, dict) and "steps" in parameters:
            steps = parameters.get("steps")
        if steps is not None and not isinstance(steps, list):
            return False, f"{action_name}.steps must be a list"
        return True, ""
    if action_name in KNOWN_TOOLS:
        return True, ""
    return False, f"Unknown action type before translation: {action_name}"
