"""
M.A.Y.D.A.Y Context Compressor - Memory Discipline Engine
=========================================================
Keeps active planning context bounded with layered semantic memory.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("mayday.compressor")

TARGET_CONTEXT_CHARS = 6000
MAX_CONTEXT_CHARS = 8000

_ESSENTIAL_RESULT_KEYS = {
    "status",
    "state",
    "error",
    "path",
    "project_dir",
    "url",
    "title",
    "returncode",
    "bytes_written",
    "count",
    "session_id",
    "screenshot",
    "headless",
    "classification",
    "attempts",
    "final_url",
    "completed_steps",
    "text",
    "body",
    "truncated",
    "total_chars",
    "events",
    "emails",
    "note",
    "tool_name",
    "tools",
    "ready",
    "next_step",
    "actionable",
    "query",
    "event_id",
    "start",
    "end",
    "timezone",
    "chars_written",
    "content",
    "schema_failures",
    "minimum_chars",
    "generation_attempts",
}

_DISCARD_RESULT_KEYS = {
    "screenshot",
    "html",
    "page_source",
    "raw_html",
    "cookies",
    "headers",
    "debug",
    "trace",
    "logs",
}


@dataclass(frozen=True)
class LayeredMemoryItem:
    role: str
    content: str
    layer: str
    priority_score: float
    relevance_score: float
    decay_rate: float
    created_at: float

    def effective_score(self, now: float) -> float:
        age_minutes = max((now - self.created_at) / 60.0, 0.0)
        return max(0.0, (self.priority_score + self.relevance_score) - (self.decay_rate * age_minutes))


class ContextCompressor:
    @staticmethod
    def compress_tool_result(result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return str(result)[:300]

        compressed: dict[str, Any] = {}
        for key in _ESSENTIAL_RESULT_KEYS:
            if key in result:
                value = result[key]
                if isinstance(value, str):
                    limit = 3000 if key in {"text", "body"} else 200
                    if len(value) > limit:
                        value = value[:limit] + "..."
                compressed[key] = value

        if "results" in result and isinstance(result["results"], list):
            sub_results = []
            for entry in result["results"][:5]:
                if not isinstance(entry, dict):
                    continue
                sub = {}
                for key, value in entry.items():
                    if key in _DISCARD_RESULT_KEYS:
                        continue
                    if isinstance(value, dict):
                        value = ContextCompressor.compress_tool_result(value)
                    elif isinstance(value, str) and len(value) > 150:
                        value = value[:150] + "..."
                    sub[key] = value
                sub_results.append(sub)
            compressed["results"] = sub_results

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
        if not messages:
            return messages

        preserved_count = min(2, len(messages))
        preserved = messages[:preserved_count]
        remaining = messages[preserved_count:]
        if not remaining:
            return preserved

        preserved_chars = sum(len(m.get("content", "")) for m in preserved)
        budget = TARGET_CONTEXT_CHARS - preserved_chars
        if budget <= 0:
            logger.error(
                "Pinned context exceeds target budget (%d chars); preserving system/tools block intact",
                preserved_chars,
            )
            return preserved

        now = time.time()
        base_time = now - len(remaining)
        ranked: list[tuple[int, LayeredMemoryItem]] = []
        for index, msg in enumerate(remaining):
            ranked.append(
                (
                    index,
                    ContextCompressor._memory_item(
                        role=msg.get("role", "system"),
                        content=msg.get("content", ""),
                        created_at=base_time + index,
                    ),
                )
            )

        selected_indexes: set[int] = set()
        chars_used = 0
        latest_tool_index = next(
            (
                index
                for index in range(len(remaining) - 1, -1, -1)
                if remaining[index].get("role") == "tool"
            ),
            None,
        )
        pinned_indexes: set[int] = set()
        latest_tool_content = ""
        if latest_tool_index is not None:
            latest_item = ranked[latest_tool_index][1]
            latest_compact = ContextCompressor._compress_layer_content(latest_item)
            latest_tool_content = latest_compact
            selected_indexes.add(latest_tool_index)
            pinned_indexes.add(latest_tool_index)
            chars_used += len(latest_compact)
            if latest_tool_index > 0 and remaining[latest_tool_index - 1].get("role") == "assistant":
                action_item = ranked[latest_tool_index - 1][1]
                action_compact = ContextCompressor._compress_layer_content(action_item)
                selected_indexes.add(latest_tool_index - 1)
                pinned_indexes.add(latest_tool_index - 1)
                chars_used += len(action_compact)

        for index, item in ranked:
            if index in selected_indexes:
                continue
            if item.layer != "failure":
                continue
            compact = ContextCompressor._compress_layer_content(item)
            if chars_used + len(compact) <= budget:
                selected_indexes.add(index)
                chars_used += len(compact)

        for index, item in sorted(ranked, key=lambda entry: entry[1].effective_score(now), reverse=True):
            if index in selected_indexes:
                continue
            compact = ContextCompressor._compress_layer_content(item)
            if chars_used + len(compact) > budget:
                continue
            selected_indexes.add(index)
            chars_used += len(compact)

        kept_pairs = [
            (index, {"role": item.role, "content": ContextCompressor._compress_layer_content(item)})
            for index, item in ranked
            if index in selected_indexes
        ]

        while kept_pairs and preserved_chars + sum(len(m.get("content", "")) for _index, m in kept_pairs) > MAX_CONTEXT_CHARS:
            if kept_pairs[0][0] in pinned_indexes:
                break
            kept_pairs.pop(0)

        kept = [message for _index, message in kept_pairs]

        dropped_count = len(remaining) - len(kept)
        if dropped_count > 0:
            summary = {
                "role": "system",
                "content": f"[{dropped_count} earlier messages semantically compressed: failures/goals preserved, repetitive execution logs decayed]",
            }
            return preserved + [summary] + kept
        return preserved + kept

    @staticmethod
    def _memory_item(role: str, content: str, created_at: float) -> LayeredMemoryItem:
        lowered = content.lower()
        if any(marker in lowered for marker in ("error", "failed", "failure", "timeout", "rate limit", "429", "denied")):
            return LayeredMemoryItem(role, content, "failure", 0.95, 0.9, 0.01, created_at)
        if any(marker in lowered for marker in ("goal", "user", "request", "required", "intent")):
            return LayeredMemoryItem(role, content, "goal", 0.9, 0.75, 0.02, created_at)
        if any(marker in lowered for marker in ("browser_", "session_id", "url", "selector", "screenshot", "filesystem")):
            return LayeredMemoryItem(role, content, "environment", 0.55, 0.45, 0.08, created_at)
        return LayeredMemoryItem(role, content, "execution", 0.35, 0.25, 0.18, created_at)

    @staticmethod
    def _compress_layer_content(item: LayeredMemoryItem) -> str:
        content = item.content
        if item.layer == "failure":
            return content[:1200] if len(content) > 1200 else content
        if item.layer == "goal":
            return content[:900] + ("...[goal compressed]" if len(content) > 900 else "")
        if item.layer == "environment":
            return ContextCompressor._semantic_environment_summary(content)
        if len(content) > 350:
            return content[:180] + "\n...[execution spam decayed]...\n" + content[-120:]
        return content

    @staticmethod
    def _semantic_environment_summary(content: str) -> str:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                keep = {
                    key: value
                    for key, value in parsed.items()
                    if key in {
                        "status",
                        "tool_name",
                        "tools",
                        "url",
                        "title",
                        "session_id",
                        "selector",
                        "final_url",
                        "completed_steps",
                        "error",
                        "ready",
                        "next_step",
                        "path",
                        "chars_written",
                        "count",
                        "emails",
                        "events",
                    }
                }
                if keep:
                    return json.dumps(keep, default=str)
        except Exception:
            pass
        if len(content) > 500:
            return content[:250] + "\n...[browser/filesystem state summarized]...\n" + content[-150:]
        return content

    @staticmethod
    def compress_assistant_output(raw: str) -> str:
        if not raw or len(raw) <= 300:
            return raw
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                action = parsed.get("action", "")
                skeleton: dict[str, Any] = {"action": action}
                if action == "tool_call":
                    skeleton["tool_name"] = parsed.get("tool_name", "")
                    params = parsed.get("parameters", {})
                    skeleton["parameters"] = {
                        key: (value[:80] + "..." if isinstance(value, str) and len(value) > 80 else value)
                        for key, value in (params.items() if isinstance(params, dict) else [])
                    }
                elif action == "multi_tool_call":
                    tools = parsed.get("tools", [])
                    skeleton["tools"] = [
                        {"tool_name": tool.get("tool_name", "")}
                        for tool in tools
                        if isinstance(tool, dict)
                    ]
                elif action == "respond":
                    text = parsed.get("text", parsed.get("response", ""))
                    if isinstance(text, str) and len(text) > 200:
                        text = text[:200] + "..."
                    skeleton["text"] = text
                return json.dumps(skeleton, default=str)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return raw[:300] + "...[truncated]"
