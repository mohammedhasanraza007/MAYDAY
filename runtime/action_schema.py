from __future__ import annotations

from typing import Any

from runtime.execution_registry import KNOWN_TOOLS, validate_payload


def validate(action: dict[str, Any]) -> tuple[bool, str]:
    action_name = action.get("action", "")
    if action_name == "respond":
        text = action.get("text", action.get("response", action.get("content", "")))
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
    return validate_payload(tool_name, parameters)


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
