from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = MAYDAY_ROOT / "logs"
AUDIT_PATH = LOGS_DIR / "browser_audit.jsonl"


def record(action: str, target: Any, session_id: str | None, screenshot_path: str | Path | None, user_approved: bool = True) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "target": target,
        "session_id": session_id,
        "screenshot": str(screenshot_path) if screenshot_path else None,
        "user_approved": bool(user_approved),
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def read_recent(n: int = 100) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-max(1, n):]
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
