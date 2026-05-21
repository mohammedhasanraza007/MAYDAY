from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ALLOWLIST_PATH = SCRIPT_DIR / "allowlist.json"


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _matches_allowed(path: str, rules: list[str]) -> bool:
    for rule in rules:
        normalized_rule = _normalize(rule)
        if normalized_rule.endswith("/"):
            if path.startswith(normalized_rule):
                return True
        elif path == normalized_rule:
            return True
    return False


def _load_allowlist() -> dict:
    if not ALLOWLIST_PATH.exists():
        print(f"[ERROR] Missing allowlist file: {ALLOWLIST_PATH}")
        sys.exit(1)
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def _staged_changes() -> list[tuple[str, list[str]]]:
    result = subprocess.run(
        ["git", "diff", "--name-status", "--cached"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("[ERROR] Failed to read staged diff.")
        print(result.stderr.strip())
        sys.exit(1)

    changes: list[tuple[str, list[str]]] = []
    for raw_line in result.stdout.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        status = parts[0]
        paths = [_normalize(p) for p in parts[1:]]
        changes.append((status, paths))
    return changes


def main() -> int:
    allowlist = _load_allowlist()
    protected = {_normalize(p) for p in allowlist.get("protected", [])}
    allowed_writes = allowlist.get("allowed_writes", [])
    allowed_modifies = {_normalize(p) for p in allowlist.get("allowed_modifies", [])}

    errors: list[str] = []
    changes = _staged_changes()
    if not changes:
        print("[OK] No staged files.")
        return 0

    for status, paths in changes:
        kind = status[0]
        if kind == "R":
            old_path, new_path = paths
            file_paths = [old_path, new_path]
        else:
            file_paths = [paths[0]]

        for path in file_paths:
            if path in protected:
                errors.append(f"[PROTECTED] {path} is protected and cannot be staged.")
                continue

        if kind == "A":
            target = paths[0]
            if not _matches_allowed(target, allowed_writes):
                errors.append(
                    f"[WRITE BLOCKED] New file outside allow-list: {target}"
                )
        elif kind in {"M", "D", "R", "C", "T", "U"}:
            targets = paths if kind == "R" else [paths[0]]
            for target in targets:
                if target not in allowed_modifies:
                    errors.append(
                        f"[MODIFY BLOCKED] File not in allowed_modifies: {target}"
                    )
        else:
            errors.append(f"[UNKNOWN STATUS] {status} for {', '.join(paths)}")

    if errors:
        print("[FAIL] protection_check.py found violations:")
        for error in errors:
            print(error)
        return 1

    print("[OK] All staged files are within phase allow-list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
