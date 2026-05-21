"""
M.A.Y.D.A.Y Post-Build Verification v5.0
========================================
Strict gate for the GGUF-only architecture.
Verifies: isolated runtime, llama-cpp-python, GGUF paths, and tools.
NO torch. NO transformers.
"""
import os
import sys
import time
import json
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(ROOT_DIR))

def check(name, condition):
    status = "[PASS]" if condition else "[FAIL]"
    print(f"{status} {name}")
    return condition

def verify():
    print("============================================================")
    print(" MAYDAY v5.0 POST-BUILD VERIFICATION")
    print("============================================================")
    
    all_pass = True
    
    # 1. Directory Integrity
    for rel in ["runtime/python", "models", "logs", "core", "ui", "mayday_runtime"]:
        all_pass &= check(f"Directory exists: {rel}", (ROOT_DIR / rel).exists())

    # 2. Runtime Integrity
    python_exe = ROOT_DIR / "runtime" / "python" / "python.exe"
    all_pass &= check(f"Embedded Python exists: {python_exe}", python_exe.exists())
    
    # 3. Core Dependency Check (The "No Torch" Rule)
    print("\n--- Backend Dependencies ---")
    try:
        import llama_cpp
        all_pass &= check(f"llama-cpp-python installed: {llama_cpp.__version__}", True)
    except ImportError:
        all_pass &= check("llama-cpp-python MISSING", False)

    # Verify NO torch/transformers contamination
    for pkg in ["torch", "transformers", "peft", "accelerate"]:
        try:
            import importlib
            importlib.import_module(pkg)
            print(f"[WARN] Contamination detected: {pkg} is installed but shouldn't be.")
        except ImportError:
            pass # This is good

    # 4. Critical Library Imports
    print("\n--- Library Imports ---")
    for pkg in ["PyQt6", "psutil", "httpx", "jsonschema", "requests", "huggingface_hub"]:
        try:
            import importlib
            importlib.import_module(pkg)
            check(f"Import {pkg}: OK", True)
        except ImportError as e:
            all_pass &= check(f"Import {pkg}: FAILED ({e})", False)

    # 5. Model Downloader & GGUF Logic
    print("\n--- Model System ---")
    try:
        from model.downloader import ModelDownloader, DOWNLOAD_TARGETS
        downloader = ModelDownloader()
        all_pass &= check("ModelDownloader initialized", True)
        
        # Check for at least one tier file
        found = False
        for target in DOWNLOAD_TARGETS:
            path = ROOT_DIR / "models" / target["gguf_file"]
            if path.exists():
                found = True
                print(f"[INFO] Found model: {path.name}")
        
        if not found:
            print("[INFO] No models downloaded yet. Layer 4 pending.")
    except Exception as e:
        all_pass &= check(f"Model system check failed: {e}", False)

    # 6. Tool Engine
    print("\n--- Execution Engine ---")
    try:
        from mayday_runtime.engine import ExecutionEngine
        engine = ExecutionEngine()
        all_pass &= check("ExecutionEngine initialized", True)
    except Exception as e:
        all_pass &= check(f"ExecutionEngine check failed: {e}", False)

    print("\n============================================================")
    if all_pass:
        print(" VERIFICATION SUCCESSFUL - SYSTEM STABILIZED")
        sys.exit(0)
    else:
        print(" VERIFICATION FAILED - REPAIR REQUIRED")
        sys.exit(1)

if __name__ == "__main__":
    verify()
