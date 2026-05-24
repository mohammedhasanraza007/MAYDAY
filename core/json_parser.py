"""
M.A.Y.D.A.Y JSON Parser
=======================
Phase 04 parser flow:
1) json.loads(raw) directly
2) repair common malformed JSON and retry
3) regex extract first {...} block, then repair and retry
4) resilient fallback wrapper if parsing still fails
Then validate with runtime.action_schema.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

from runtime import action_schema
from runtime.execution_registry import structural_validate


CODEBLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

_parser_logger = __import__("logging").getLogger("mayday.parser")


def _pre_sanitize(raw: str) -> str:
    """Strip markdown code fences and surrounding whitespace before parsing.

    This handles the most common local-model failure: returning
    ```json\n{...}\n``` instead of raw JSON.
    """
    text = raw.strip()
    # Strip leading ```json or ``` and trailing ```
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]  # bare ``` with no newline
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def extract_first_json_block(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    
    # Collect all indices of '}' from right to left
    indices = []
    for i in range(len(text) - 1, start, -1):
        if text[i] == "}":
            indices.append(i)
            
    # Try parsing substrings from right to left to find the largest valid JSON block
    for idx in indices:
        candidate = text[start:idx+1]
        try:
            # We use json.loads directly or _try_parse_with_repair to check validity
            if _try_parse_with_repair(candidate) is not None:
                return candidate
        except Exception:
            continue
            
    return None


def parse_model_output(raw: str) -> dict[str, Any]:
    text = normalize_model_output(raw)
    if not text:
        return safe_response_object("")

    # Pre-sanitize: strip markdown fences before first parse attempt
    text = _pre_sanitize(text)

    parsed = _try_parse_with_repair(text)
    if parsed is None:
        block = CODEBLOCK_PATTERN.search(text)
        if block is not None:
            parsed = _try_parse_with_repair(block.group(1).strip())

    if parsed is None:
        block = extract_first_json_block(text)
        if block is not None:
            parsed = _try_parse_with_repair(block)

    if parsed is None:
        # Only log after ALL repair strategies are exhausted
        reason = "truncated" if _looks_truncated_json(text) else "invalid"
        _parser_logger.warning(
            "JSON output %s after all repair attempts for text: %r",
            reason,
            text[:200],
        )
        return safe_response_object(text)

    action_obj = _normalize_action_object(parsed, text)
    if not isinstance(action_obj, dict):
        return safe_response_object(text)

    if _is_valid_action_object(action_obj):
        return action_obj

    # Never break the pipeline on malformed action objects.
    if action_obj.get("action") == "respond":
        return _ensure_respond_keys(action_obj)
    return safe_response_object(text)


def normalize_model_output(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    try:
        return json.dumps(raw, ensure_ascii=False).strip()
    except Exception:
        return str(raw).strip()


def safe_response_object(text: str) -> dict[str, Any]:
    return {
        "action": "respond",
        "text": text or "",
        "response": text or "",
        "meta": {"fallback": True},
    }


def _try_load_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _try_parse_with_repair(text: str) -> Any | None:
    parsed = _try_load_json(text)
    if parsed is not None:
        return parsed

    repaired = _repair_json_text(text)
    if repaired != text:
        parsed = _try_load_json(repaired)
        if parsed is not None:
            return parsed

    parsed = _try_literal_eval(text)
    if parsed is not None:
        return parsed

    if repaired != text:
        parsed = _try_literal_eval(repaired)
        if parsed is not None:
            return parsed

    return None


def _repair_json_text(text: str) -> str:
    candidate = text.strip()
    if not candidate:
        return candidate

    if not candidate.startswith("{") and ":" in candidate and not candidate.startswith("["):
        candidate = "{" + candidate + "}"

    # Remove trailing commas in objects/arrays.
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    # Normalize common python-style primitives.
    candidate = re.sub(r"\bNone\b", "null", candidate)
    candidate = re.sub(r"\bTrue\b", "true", candidate)
    candidate = re.sub(r"\bFalse\b", "false", candidate)

    # Repair invalid escape sequences (e.g. \', \*, \_)
    candidate = re.sub(r'(?<!\\)\\(?!["/bfnrtu\\])', r'\\\\', candidate)

    # Standardize non-standard keys/actions generated by third-party APIs
    candidate = re.sub(r'"action"\s*:\s*"(?:tool_code|tool)"', '"action": "tool_call"', candidate)
    candidate = re.sub(r'"tool_name"\s*:\s*"shell"', '"tool_name": "shell_run"', candidate)

    return candidate


def _looks_truncated_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    opens = stripped.count("{") + stripped.count("[")
    closes = stripped.count("}") + stripped.count("]")
    if opens > closes:
        return True
    return stripped.endswith((",", ":", "{", "["))


def _try_literal_eval(text: str) -> Any | None:
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _normalize_action_object(parsed: Any, raw_text: str) -> dict[str, Any]:
    if isinstance(parsed, str):
        return safe_response_object(parsed)
    if not isinstance(parsed, dict):
        return safe_response_object(raw_text)

    normalized = dict(parsed)
    action = normalized.get("action")

    if isinstance(action, str) and action.strip() in action_schema.KNOWN_TOOLS:
        tool_name = action.strip()
        params = normalized.get("parameters")
        if not isinstance(params, dict):
            params = {k: v for k, v in normalized.items() if k not in {"action", "tool_name"}}
        normalized = {
            "action": "tool_call",
            "tool_name": tool_name,
            "parameters": params
        }
        action = "tool_call"

    if not isinstance(action, str) or not action.strip():
        if "tool_name" in normalized and "parameters" in normalized:
            normalized["action"] = "tool_call"
        elif {"project_name", "stack", "files"}.issubset(normalized.keys()):
            normalized["action"] = "scaffold"
        elif "text" in normalized or "response" in normalized or "content" in normalized:
            normalized["action"] = "respond"
        else:
            return safe_response_object(raw_text)

    if normalized.get("action") == "respond":
        return _ensure_respond_keys(normalized)
    if normalized.get("action") == "multi_tool_call":
        normalized = _repair_multi_tool_call_alias(normalized)
    if normalized.get("action") == "multi_tool_call" and "tools" not in normalized:
        if "tool_name" in normalized and "parameters" in normalized:
            normalized["action"] = "tool_call"
    if normalized.get("action") == "tool_call":
        normalized = _repair_tool_call_alias(normalized)
    return normalized


def _repair_multi_tool_call_alias(action: dict[str, Any]) -> dict[str, Any]:
    tool_code = action.get("tool_code")
    tools = action.get("tools", action.get("tool_calls", action.get("calls")))
    
    if not isinstance(tools, list) and isinstance(tool_code, str):
        # Parse Python-like tool calls from tool_code string using AST
        import ast
        extracted_tools = []
        try:
            tree = ast.parse(tool_code.strip())
            for stmt in tree.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call_node = stmt.value
                    if isinstance(call_node.func, ast.Name):
                        tool_name = call_node.func.id
                        params = {}
                        for kw in call_node.keywords:
                            try:
                                params[kw.arg] = ast.literal_eval(kw.value)
                            except Exception:
                                pass
                        extracted_tools.append({
                            "tool_name": tool_name,
                            "parameters": params
                        })
            tools = extracted_tools
        except Exception as e:
            _parser_logger.warning("AST-based tool_code parsing failed: %s", e)

    if not isinstance(tools, list):
        return action

    repaired_tools: list[dict[str, Any]] = []
    for entry in tools:
        if not isinstance(entry, dict):
            repaired_tools.append(entry)
            continue
        tool_name = entry.get("tool_name", entry.get("name", entry.get("tool")))
        parameters = entry.get("parameters", entry.get("args", entry.get("input", {})))
        repaired_tools.append({"tool_name": tool_name, "parameters": parameters})
    action["tools"] = repaired_tools
    action.pop("tool_calls", None)
    action.pop("calls", None)
    action.pop("tool_code", None)
    return action


def _repair_tool_call_alias(action: dict[str, Any]) -> dict[str, Any]:
    tool_name = action.get("tool_name")
    parameters = action.get("parameters")
    
    # Handle single tool call returned with tool_code or where parameters itself contains tool_code
    tool_code = action.get("tool_code")
    if not isinstance(tool_code, str) and isinstance(parameters, dict):
        tool_code = parameters.get("tool_code")

    if isinstance(tool_code, str) and (not isinstance(tool_name, str) or not isinstance(parameters, dict)):
        import ast
        try:
            tree = ast.parse(tool_code.strip())
            for stmt in tree.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call_node = stmt.value
                    if isinstance(call_node.func, ast.Name):
                        action["tool_name"] = call_node.func.id
                        params = {}
                        for kw in call_node.keywords:
                            try:
                                params[kw.arg] = ast.literal_eval(kw.value)
                            except Exception:
                                pass
                        action["parameters"] = params
                        action.pop("tool_code", None)
                        tool_name = action["tool_name"]
                        parameters = action["parameters"]
                        break
        except Exception as e:
            _parser_logger.warning("AST-based tool_code parsing failed in single tool_call: %s", e)

    if not isinstance(tool_name, str) or not isinstance(parameters, dict):
        return action

    normalized = tool_name.strip().lower()
    if normalized in {"file_system_tools", "file_tools"}:
        files = parameters.get("files")
        if isinstance(files, list) and len(files) == 1 and isinstance(files[0], dict):
            file_spec = files[0]
            path = file_spec.get("path")
            content = file_spec.get("content")
            if isinstance(path, str) and isinstance(content, str):
                action["tool_name"] = "file_write"
                action["parameters"] = {"path": path, "content": content}
    elif normalized in {"shell", "powershell"} and isinstance(parameters.get("command"), str):
        action["tool_name"] = "shell_run"
    elif normalized == "shell_run" or normalized == "shell":
        action["tool_name"] = "shell_run"
        commands = parameters.get("commands", parameters.get("command"))
        if isinstance(commands, list):
            parameters["command"] = "; ".join(str(cmd) for cmd in commands)
            parameters.pop("commands", None)
    elif normalized in {"web", "search"} and isinstance(parameters.get("query"), str):
        action["tool_name"] = "web_search"
    elif normalized in {"fetch", "page_fetch"} and isinstance(parameters.get("url"), str):
        action["tool_name"] = "web_fetch"
    return action


def _ensure_respond_keys(action: dict[str, Any]) -> dict[str, Any]:
    text = action.get("text", action.get("response", action.get("content", "")))
    if not isinstance(text, str):
        text = str(text)
    action["text"] = text
    action["response"] = text
    action["content"] = text
    return action


def _is_valid_action_object(parsed: dict[str, Any]) -> bool:
    action = parsed.get("action", "")

    valid, _reason = structural_validate(parsed)
    return valid
