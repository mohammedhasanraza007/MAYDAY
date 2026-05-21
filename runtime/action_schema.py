from __future__ import annotations

from typing import Any


KNOWN_TOOLS = {
    "browser_click",
    "browser_close",
    "browser_get_text",
    "browser_act",
    "browser_navigate",
    "browser_open",
    "browser_screenshot",
    "browser_type",
    "file_delete",
    "file_list",
    "file_read",
    "file_write",
    "powershell_python_script",
    "powershell_run",
    "project",
    "scaffold",
    "scaffold_engine",
    "server_launch",
    "server_runner",
    "server_status",
    "server_stop",
    "shell_run",
    "system_click",
    "system_hotkey",
    "system_info",
    "system_screenshot",
    "system_type",
    "web_fetch",
    "web_search",
}


def validate(action: dict[str, Any]) -> tuple[bool, str]:
    action_name = action.get("action", "")
    if action_name == "respond":
        text = action.get("text", action.get("response", ""))
        if not isinstance(text, str):
            return False, "respond text must be a string"
        return True, ""

    if action_name == "tool_call":
        tool_name = action.get("tool_name")
        parameters = action.get("parameters")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return False, "tool_call.tool_name must be a non-empty string"
        if not isinstance(parameters, dict):
            return False, "tool_call.parameters must be an object"
        return validate_action(tool_name, parameters)

    if action_name == "multi_tool_call":
        tools = action.get("tools")
        if not isinstance(tools, list) or not tools:
            return False, "multi_tool_call.tools must be a non-empty list"
        seen: set[str] = set()
        for index, entry in enumerate(tools):
            if not isinstance(entry, dict):
                return False, f"multi_tool_call.tools[{index}] must be an object"
            tool_name = entry.get("tool_name")
            parameters = entry.get("parameters")
            if not isinstance(tool_name, str) or not tool_name.strip():
                return False, f"multi_tool_call.tools[{index}].tool_name must be non-empty"
            if not isinstance(parameters, dict):
                return False, f"multi_tool_call.tools[{index}].parameters must be an object"
            fingerprint = repr((tool_name, sorted(parameters.items(), key=lambda item: str(item[0]))))
            if fingerprint in seen:
                return False, f"duplicate tool call in multi_tool_call: {tool_name}"
            seen.add(fingerprint)
            valid, reason = validate_action(tool_name, parameters)
            if not valid:
                return False, reason
        return True, ""

    if isinstance(action_name, str) and action_name.strip():
        params = {k: v for k, v in action.items() if k != "action"}
        return validate_action(action_name, params)

    return False, "action must be a non-empty string"


def validate_action(tool_name: str, parameters: dict) -> tuple[bool, str]:
    if not isinstance(tool_name, str) or not tool_name.strip():
        return False, "tool_name must be a non-empty string"
    if not isinstance(parameters, dict):
        return False, "parameters must be an object"

    normalized = tool_name.strip()
    if normalized not in KNOWN_TOOLS:
        return False, f"Unknown or uncontracted tool: {tool_name}"

    if normalized in {"scaffold", "scaffold_engine"}:
        return _validate_scaffold(normalized, parameters)
    if normalized == "project":
        return _validate_project(normalized, parameters)
    if normalized in {"shell_run", "powershell_run"}:
        return _require_non_empty_string(normalized, parameters, "command")
    if normalized == "powershell_python_script":
        valid, reason = _require_non_empty_string(normalized, parameters, "script_path")
        if not valid:
            return valid, reason
        args = parameters.get("args", [])
        if not isinstance(args, list):
            return False, "args must be a list"
        return True, ""
    if normalized in {"server_launch", "server_runner"}:
        valid, reason = _require_path_like(normalized, parameters, ("project_dir", "path"))
        if not valid:
            return valid, reason
        stack = parameters.get("stack", "flask")
        if not isinstance(stack, str) or not stack.strip():
            return False, "stack must be a non-empty string"
        return True, ""
    if normalized in {"server_status", "server_stop"}:
        return _require_path_like(normalized, parameters, ("project_dir", "path"))
    if normalized in {"file_read", "file_delete"}:
        return _require_path_like(normalized, parameters, ("path", "file_path"))
    if normalized == "file_write":
        valid, reason = _require_path_like(normalized, parameters, ("path", "file_path"))
        if not valid:
            return valid, reason
        if not isinstance(parameters.get("content"), str):
            return False, "content must be a string"
        return True, ""
    if normalized == "file_list":
        return _require_path_like(normalized, parameters, ("path", "directory"))
    if normalized in {"browser_navigate", "browser_open"}:
        return _require_non_empty_string(normalized, parameters, "url")
    if normalized == "browser_act":
        steps = parameters.get("steps")
        if not isinstance(steps, list) or not steps:
            return False, "browser_act.steps must be a non-empty list"
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                return False, f"browser_act.steps[{index}] must be an object"
            action = step.get("action")
            if action not in {
                "open",
                "navigate",
                "click",
                "type",
                "wait_for",
                "press",
                "screenshot",
                "extract_meet_link",
                "detect_login_state",
                "get_text",
            }:
                return False, f"browser_act.steps[{index}].action is unsupported"
            if action in {"open", "navigate"}:
                valid, reason = _require_non_empty_string("browser_act step", step, "url")
                if not valid:
                    return False, reason
            if action in {"click", "type", "wait_for"}:
                valid, reason = _require_non_empty_string("browser_act step", step, "selector")
                if not valid:
                    return False, reason
                if action == "type" and not isinstance(step.get("text", step.get("value")), str):
                    return False, "browser_act type step requires text or value"
            if action == "press":
                valid, reason = _require_non_empty_string("browser_act step", step, "key")
                if not valid:
                    return False, reason
        return True, ""
    if normalized in {"browser_click", "browser_type"}:
        valid, reason = _require_non_empty_string(normalized, parameters, "selector")
        if not valid:
            return valid, reason
        if normalized == "browser_type" and not isinstance(parameters.get("text"), str):
            return False, "text must be a string"
        return True, ""
    if normalized in {"browser_screenshot", "browser_get_text", "browser_close"}:
        return True, ""
    if normalized == "system_click":
        if not isinstance(parameters.get("x"), int) or not isinstance(parameters.get("y"), int):
            return False, "x and y must be integers"
        return True, ""
    if normalized == "system_type":
        return _require_non_empty_string(normalized, parameters, "text")
    if normalized == "system_hotkey":
        keys = parameters.get("keys")
        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
            return False, "keys must be a non-empty list of strings"
        return True, ""
    if normalized in {"system_info", "system_screenshot"}:
        return True, ""
    if normalized == "web_search":
        valid, reason = _require_non_empty_string(normalized, parameters, "query")
        if not valid:
            return valid, reason
        provider = parameters.get("provider")
        if provider is not None and not isinstance(provider, str):
            return False, "provider must be a string when provided"
        return True, ""
    if normalized == "web_fetch":
        valid, reason = _require_non_empty_string(normalized, parameters, "url")
        if not valid:
            return valid, reason
        extract = parameters.get("extract")
        if extract is not None and not isinstance(extract, str):
            return False, "extract must be a string when provided"
        return True, ""

    return False, f"No schema handler for tool: {tool_name}"


def validate_tool_result(tool_name: str, result: Any) -> tuple[bool, str]:
    if not isinstance(result, dict):
        return False, f"{tool_name} returned non-object result: {type(result).__name__}"
    status = result.get("status")
    if status not in {"success", "error", "cancelled"}:
        return False, f"{tool_name} result.status must be 'success', 'error', or 'cancelled'"
    if status == "error" and not isinstance(result.get("error"), str):
        return False, f"{tool_name} error result requires string error"
    if status == "cancelled" and not isinstance(result.get("reason"), str):
        return False, f"{tool_name} cancelled result requires string reason"
    return True, ""


def _validate_scaffold(tool_name: str, parameters: dict) -> tuple[bool, str]:
    for field in ("project_name", "stack", "files"):
        if field not in parameters:
            return False, f"Missing required field for {tool_name}: {field}"

    if not isinstance(parameters.get("project_name"), str) or not parameters["project_name"].strip():
        return False, "project_name must be a non-empty string"
    if not isinstance(parameters.get("stack"), str) or not parameters["stack"].strip():
        return False, "stack must be a non-empty string"

    files = parameters.get("files")
    if not isinstance(files, list) or not files:
        return False, "files must be a non-empty list"

    for index, file_spec in enumerate(files):
        if not isinstance(file_spec, dict):
            return False, f"files[{index}] must be an object"
        if "path" not in file_spec or "content" not in file_spec:
            return False, f"files[{index}] requires path and content"
        if not isinstance(file_spec["path"], str) or not file_spec["path"].strip():
            return False, f"files[{index}].path must be a non-empty string"
        if not isinstance(file_spec["content"], str):
            return False, f"files[{index}].content must be a string"

    return True, ""


def _validate_project(tool_name: str, parameters: dict) -> tuple[bool, str]:
    valid, reason = _validate_scaffold(tool_name, parameters)
    return valid, reason


def _require_non_empty_string(tool_name: str, parameters: dict, field: str) -> tuple[bool, str]:
    value = parameters.get(field)
    if not isinstance(value, str) or not value.strip():
        return False, f"{tool_name}.{field} must be a non-empty string"
    return True, ""


def _require_path_like(tool_name: str, parameters: dict, fields: tuple[str, ...]) -> tuple[bool, str]:
    if not any(isinstance(parameters.get(field), str) and parameters.get(field).strip() for field in fields):
        return False, f"{tool_name} requires one of: {', '.join(fields)}"
    return True, ""
