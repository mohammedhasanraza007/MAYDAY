from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = MAYDAY_ROOT / "runtime" / "world_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorldState:
    """Small persistent runtime state ledger for executor awareness.

    This is intentionally conservative: it stores state MAYDAY has verified
    through tool results, not inferred wishes from a prompt.
    """

    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._load()

    def record_tool_result(self, tool_name: str, result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return
        with self._lock:
            state = self._load()
            state["updated_at"] = _now()
            state["last_tool"] = {
                "tool_name": tool_name,
                "status": result.get("status", "unknown"),
                "timestamp": state["updated_at"],
            }
            self._update_browser_state(state, tool_name, result)
            self._update_filesystem_state(state, tool_name, result)
            self._update_permission_state(state, tool_name, result)
            history = state.setdefault("task_progress", [])
            history.append(
                {
                    "timestamp": state["updated_at"],
                    "tool_name": tool_name,
                    "status": result.get("status", "unknown"),
                    "summary": self._summarize_result(result),
                }
            )
            del history[:-100]
            self._write(state)

    def set_permission_blocked(self, scope: str, reason: str) -> None:
        with self._lock:
            state = self._load()
            blocked = state.setdefault("permissions", {}).setdefault("blocked", {})
            blocked[scope] = {"reason": reason, "timestamp": _now()}
            state["updated_at"] = _now()
            self._write(state)

    def clear_permission_blocks(self) -> None:
        with self._lock:
            state = self._load()
            state.setdefault("permissions", {})["blocked"] = {}
            state["updated_at"] = _now()
            self._write(state)

    def _default(self) -> dict[str, Any]:
        return {
            "created_at": _now(),
            "updated_at": _now(),
            "browser": {
                "active": False,
                "active_sessions": 0,
                "session_id": "",
                "current_url": "",
                "title": "",
                "profile_dir": "",
                "headless": None,
                "login_state": "unknown",
                "tabs": [],
            },
            "desktop": {"focused_window": "", "last_process": {}},
            "filesystem": {"current_project_path": "", "verified_files": []},
            "permissions": {"blocked": {}},
            "task_progress": [],
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default()
        if not isinstance(data, dict):
            return self._default()
        default = self._default()
        for key, value in default.items():
            data.setdefault(key, value)
        return data

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def _update_browser_state(self, state: dict[str, Any], tool_name: str, result: dict[str, Any]) -> None:
        if not tool_name.startswith("browser_"):
            return
        browser = state.setdefault("browser", {})
        status = result.get("status")
        if tool_name == "browser_close" and status == "success":
            browser.update(
                {
                    "active": bool(result.get("active_sessions", 0)),
                    "active_sessions": int(result.get("active_sessions", 0) or 0),
                    "session_id": "",
                    "current_url": "",
                    "title": "",
                    "tabs": [],
                }
            )
            return
        if status == "success":
            url = result.get("url") or result.get("final_url") or browser.get("current_url", "")
            title = result.get("title") or browser.get("title", "")
            session_id = result.get("session_id") or browser.get("session_id", "")
            active_sessions = int(result.get("active_sessions", browser.get("active_sessions", 0)) or 0)
            browser.update(
                {
                    "active": active_sessions > 0 or bool(session_id),
                    "active_sessions": active_sessions,
                    "session_id": session_id,
                    "current_url": url,
                    "title": title,
                    "profile_dir": result.get("profile_dir", browser.get("profile_dir", "")),
                    "headless": result.get("headless", browser.get("headless")),
                    "login_state": result.get("login_state", browser.get("login_state", "unknown")),
                }
            )
            if url:
                tabs = browser.setdefault("tabs", [])
                tab = {"session_id": session_id, "url": url, "title": title, "timestamp": _now()}
                tabs.append(tab)
                del tabs[:-20]

    def _update_filesystem_state(self, state: dict[str, Any], tool_name: str, result: dict[str, Any]) -> None:
        fs = state.setdefault("filesystem", {})
        if tool_name in {"file_write", "scaffold", "scaffold_engine", "project"} and result.get("status") == "success":
            path = result.get("path") or result.get("project_dir")
            if isinstance(path, str) and path:
                target = Path(path)
                fs["current_project_path"] = str(target.parent if target.suffix else target)
            verified_files = fs.setdefault("verified_files", [])
            if isinstance(result.get("path"), str):
                verified_files.append({"path": result["path"], "timestamp": _now(), "sha256": result.get("sha256", "")})
            for file_path in result.get("files_written", []) if isinstance(result.get("files_written"), list) else []:
                verified_files.append({"path": str(file_path), "timestamp": _now(), "sha256": ""})
            del verified_files[:-100]

    def _update_permission_state(self, state: dict[str, Any], tool_name: str, result: dict[str, Any]) -> None:
        scope = tool_name.split("_", 1)[0] or "tool"
        if result.get("status") == "success":
            blocked = state.setdefault("permissions", {}).setdefault("blocked", {})
            blocked.pop(scope, None)
        if result.get("status") == "cancelled":
            blocked = state.setdefault("permissions", {}).setdefault("blocked", {})
            blocked[scope] = {
                "reason": str(result.get("reason") or result.get("error") or "user_denied"),
                "timestamp": _now(),
            }

    def _summarize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "path",
            "project_dir",
            "url",
            "final_url",
            "title",
            "session_id",
            "returncode",
            "error",
            "reason",
            "validation",
        )
        return {key: result[key] for key in keys if key in result}


world_state = WorldState()
