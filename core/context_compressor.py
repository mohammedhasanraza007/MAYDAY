"""
M.A.Y.D.A.Y Context Compressor — Memory Discipline Engine
==========================================================
Prevents context-window overflow by compressing messages and tool results
before they are fed back into the model.

Addresses E101 (context cascade), E106 (tool response bloat).
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("mayday.compressor")

# ~1500 tokens ≈ 6000 chars — hard budget for active context
MAX_CONTEXT_CHARS = 6000

# Fields to preserve when compressing tool results
_ESSENTIAL_RESULT_KEYS = {
    "status", "error", "path", "project_dir", "url", "title",
    "returncode", "bytes_written", "count", "session_id",
    "classification", "attempts", "final_url", "completed_steps",
}

# Fields that are always discarded from tool results
_DISCARD_RESULT_KEYS = {
    "screenshot", "html", "page_source", "raw_html", "cookies",
    "headers", "debug", "trace", "logs",
}


class ContextCompressor:
    """Namespace class containing all context compression routines."""

    @staticmethod
    def compress_tool_result(result: dict[str, Any]) -> str:
        """Reduce a tool result dict to a compact JSON string.

        Keeps essential status/error/path fields, discards verbose data
        like screenshots, raw HTML, debug traces, and HTTP headers.
        """
        if not isinstance(result, dict):
            return str(result)[:300]

        compressed: dict[str, Any] = {}

        # Always keep essential fields
        for key in _ESSENTIAL_RESULT_KEYS:
            if key in result:
                value = result[key]
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "…"
                compressed[key] = value

        # For multi_tool_call results, compress each sub-result
        if "results" in result and isinstance(result["results"], list):
            sub_results = []
            for entry in result["results"][:5]:  # cap at 5 sub-results
                if isinstance(entry, dict):
                    sub = {}
                    for k, v in entry.items():
                        if k in _DISCARD_RESULT_KEYS:
                            continue
                        if isinstance(v, dict):
                            v = ContextCompressor.compress_tool_result(v)
                        elif isinstance(v, str) and len(v) > 150:
                            v = v[:150] + "…"
                        sub[k] = v
                    sub_results.append(sub)
            compressed["results"] = sub_results

        # Summarize stdout/stderr for shell results
        for stream_key in ("stdout", "stderr"):
            if stream_key in result:
                text = str(result[stream_key]).strip()
                if len(text) > 200:
                    text = text[:100] + "\n...\n" + text[-100:]
                if text:
                    compressed[stream_key] = text

        if not compressed:
            compressed["status"] = result.get("status", "unknown")

        return json.dumps(compressed, default=str)

    @staticmethod
    def compress_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Trim the message list to fit within MAX_CONTEXT_CHARS.

        Strategy:
        - Always keep the first message (system prompt)
        - Always keep the second message (original user prompt)
        - From the remaining messages, keep only the most recent ones
          that fit the budget
        - Older messages are replaced with a single summary line
        """
        if not messages:
            return messages

        # Always preserve system + user prompt (first 2 messages)
        preserved_count = min(2, len(messages))
        preserved = messages[:preserved_count]
        remaining = messages[preserved_count:]

        if not remaining:
            return preserved

        # Calculate budget
        preserved_chars = sum(len(m.get("content", "")) for m in preserved)
        budget = MAX_CONTEXT_CHARS - preserved_chars

        if budget <= 0:
            # System + user already exceed budget — truncate system prompt
            if preserved and len(preserved[0].get("content", "")) > 2000:
                preserved[0] = {
                    "role": preserved[0]["role"],
                    "content": preserved[0]["content"][:2000],
                }
            return preserved

        # Walk backwards through remaining messages, keeping recent ones
        kept: list[dict[str, str]] = []
        chars_used = 0

        for msg in reversed(remaining):
            content = msg.get("content", "")
            msg_chars = len(content)

            if chars_used + msg_chars > budget:
                # Truncate this message if it's the last one we can partially fit
                remaining_budget = budget - chars_used
                if remaining_budget > 100 and not kept:
                    kept.append({
                        "role": msg["role"],
                        "content": content[:remaining_budget] + "…[truncated]",
                    })
                break

            kept.append(msg)
            chars_used += msg_chars

        kept.reverse()

        # If we dropped messages, add a summary marker
        dropped_count = len(remaining) - len(kept)
        if dropped_count > 0:
            summary = {
                "role": "system",
                "content": f"[{dropped_count} earlier messages compressed to save context]",
            }
            return preserved + [summary] + kept

        return preserved + kept

    @staticmethod
    def compress_assistant_output(raw: str) -> str:
        """Compress a raw assistant response for context replay.

        Strips verbose JSON, keeps only the action + key parameters.
        """
        if not raw or len(raw) <= 300:
            return raw

        # Try to parse as JSON and extract just the action skeleton
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                action = parsed.get("action", "")
                skeleton: dict[str, Any] = {"action": action}

                if action == "tool_call":
                    skeleton["tool_name"] = parsed.get("tool_name", "")
                    params = parsed.get("parameters", {})
                    # Keep param keys but truncate long values
                    skeleton["parameters"] = {
                        k: (v[:80] + "…" if isinstance(v, str) and len(v) > 80 else v)
                        for k, v in (params.items() if isinstance(params, dict) else [])
                    }
                elif action == "multi_tool_call":
                    tools = parsed.get("tools", [])
                    skeleton["tools"] = [
                        {"tool_name": t.get("tool_name", "")}
                        for t in tools
                        if isinstance(t, dict)
                    ]
                elif action == "respond":
                    text = parsed.get("text", parsed.get("response", ""))
                    if isinstance(text, str) and len(text) > 200:
                        text = text[:200] + "…"
                    skeleton["text"] = text

                return json.dumps(skeleton, default=str)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        # Fallback: truncate raw text
        return raw[:300] + "…[truncated]"
