"""Shared path helpers for embedded interpreter layout under `<root>/runtime/python/`."""
from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def embedded_python_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "runtime" / "python"


def prepare_windows_dll_search_paths(root: Path | None = None) -> None:
    """Register DLL directories for embedded Python + PyTorch on Windows."""
    if os.name != "nt":
        return
    base = root or project_root()
    py_root = embedded_python_dir(base)
    if not py_root.is_dir():
        return
    try:
        os.add_dll_directory(str(py_root))
    except (OSError, AttributeError):
        pass
    torch_lib = py_root / "Lib" / "site-packages" / "torch" / "lib"
    if torch_lib.is_dir():
        try:
            os.add_dll_directory(str(torch_lib.resolve()))
        except (OSError, AttributeError):
            pass
    # Prefer embedded interpreter earlier on PATH for dependent DLLs
    prev = os.environ.get("PATH", "")
    os.environ["PATH"] = str(py_root) + os.pathsep + prev
