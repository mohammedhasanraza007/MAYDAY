"""Print a host Python executable path for bootstrap (stdout, one line)."""
from __future__ import annotations

import shutil
import subprocess
import sys


def candidates():
    for argv in (
        ["py", "-3.10", "-c", "import sys; print(sys.executable)"],
        ["py", "-3", "-c", "import sys; print(sys.executable)"],
    ):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=45)
            if r.returncode == 0 and r.stdout.strip():
                yield r.stdout.strip().splitlines()[-1]
        except (OSError, subprocess.TimeoutExpired):
            continue
    w = shutil.which("python3") or shutil.which("python")
    if w:
        yield w
    if sys.executable:
        yield sys.executable


def main() -> None:
    for path in candidates():
        print(path, end="")
        return
    raise SystemExit(1)


if __name__ == "__main__":
    main()
