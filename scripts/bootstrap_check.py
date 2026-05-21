"""
Portable health check. Called by build.bat with one of:
  --install-runtime   legacy no-op (system Python + .venv is used)
  --check-deps        exit 1 if any required package missing
  --check-models      exit 1 if models/ empty or missing
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


def install_runtime() -> int:
    if not (ROOT / "bootstrap" / "gui.py").exists():
        print("SKIPPED_MISSING_SOURCE")
    print("[MAYDAY] --install-runtime is deprecated; using system Python + .venv.")
    return 0


def check_deps() -> int:
    required = [
        "PyQt6",
        "torch",
        "llama_cpp",
        "flask",
        "fastapi",
        "httpx",
        "playwright",
        "cryptography",
        "huggingface_hub",
        "psutil",
    ]
    missing = [module for module in required if importlib.util.find_spec(module) is None]
    return 1 if missing else 0


def check_models() -> int:
    if not MODELS_DIR.exists():
        return 1
    files = [
        file_path
        for file_path in MODELS_DIR.rglob("*")
        if file_path.is_file() and file_path.stat().st_size > 1024 * 1024
    ]
    return 0 if files else 1


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--install-runtime":
        raise SystemExit(install_runtime())
    if arg == "--check-deps":
        raise SystemExit(check_deps())
    if arg == "--check-models":
        raise SystemExit(check_models())
    print("Usage: bootstrap_check.py [--install-runtime|--check-deps|--check-models]")
    raise SystemExit(2)
