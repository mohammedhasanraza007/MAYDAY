"""
MAYDAY Hierarchical Condenser - replaces flat word-count truncation.
Three tiers: working memory, episode summaries, and archive files.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("mayday.memory.condenser")

WORKING_MEMORY_SIZE = 20
EPISODE_SUMMARY_EVERY = 20
EPISODE_DIR = Path("memory/episodes")


class HierarchicalCondenser:
    def __init__(self, model_router=None, max_tokens: int = 6000):
        self.model_router = model_router
        self.max_tokens = max_tokens
        self._summaries: list[str] = []
        EPISODE_DIR.mkdir(parents=True, exist_ok=True)

    def compress(self, history: list[dict]) -> list[dict]:
        """Return compressed history while never dropping pinned entries."""
        if not history:
            return []

        pinned = [
            entry
            for entry in history
            if entry.get("pinned") or entry.get("role") == "tool"
        ]
        recent = history[-WORKING_MEMORY_SIZE:]
        older = history[:-WORKING_MEMORY_SIZE]

        token_estimate = sum(
            len(json.dumps(entry, default=str)) // 4 for entry in recent + pinned
        )
        if token_estimate < self.max_tokens and not older:
            return recent

        if older:
            summary_text = self._summarise(older)
            if summary_text:
                self._summaries.append(summary_text)
                self._save_episode(summary_text)

        result = []
        if self._summaries:
            combined = "PRIOR SESSION SUMMARY:\n" + "\n---\n".join(self._summaries[-3:])
            result.append({"role": "system", "content": combined, "pinned": True})

        result.extend(pinned)
        result.extend(recent)
        return result

    def _summarise(self, entries: list[dict]) -> str:
        text_block = "\n".join(
            f"{entry.get('role', '?')}: {str(entry.get('content', ''))[:200]}"
            for entry in entries[-10:]
        )
        if self.model_router:
            try:
                prompt = (
                    "Summarise these conversation turns in 3 sentences, preserving "
                    f"key file paths and outcomes:\n{text_block}"
                )
                result = self.model_router.route(prompt, context=[])
                return result.get("response", text_block[:300])
            except Exception as exc:
                logger.warning("Summarisation failed, falling back: %s", exc)
        words = text_block.split()
        if len(words) > 60:
            return " ".join(words[:30]) + " [...] " + " ".join(words[-30:])
        return text_block

    def _save_episode(self, summary: str) -> None:
        ts = int(time.time())
        path = EPISODE_DIR / f"episode_{ts}.json"
        try:
            path.write_text(json.dumps({"summary": summary, "timestamp": ts}), encoding="utf-8")
        except Exception:
            pass

    def add_frozen_summary(self, summary: str) -> None:
        self._summaries.append(summary)

    def get_architecture_context(self) -> str:
        return "\n".join(self._summaries)


class FailureMemory:
    """Records tool failures by context signature."""

    def __init__(self):
        self._failures: dict[str, int] = {}

    def _key(self, tool_name: str, parameters: dict) -> str:
        import hashlib

        raw = tool_name + json.dumps(parameters, sort_keys=True, default=str)[:120]
        return hashlib.md5(raw.encode()).hexdigest()

    def record(self, tool_name: str, parameters: dict) -> None:
        key = self._key(tool_name, parameters)
        self._failures[key] = self._failures.get(key, 0) + 1

    def should_skip(self, tool_name: str, parameters: dict, threshold: int = 2) -> bool:
        key = self._key(tool_name, parameters)
        return self._failures.get(key, 0) >= threshold

    def reset(self) -> None:
        self._failures.clear()
