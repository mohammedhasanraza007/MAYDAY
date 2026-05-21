"""
M.A.Y.D.A.Y PyTorch Hardened Rebuild Script
==========================================
Purges and reinstalls a deterministic CPU-only Torch environment.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
RUNTIME_PY = ROOT_DIR / "runtime" / "python" / "python.exe"

def log(msg): print(f"[TORCH-FIX] {msg}")

def fix():
    log("Starting Torch Environment Purge...")
    
    # 1. Physical Removal of potentially corrupted packages
    site_packages = ROOT_DIR / "runtime" / "python" / "Lib" / "site-packages"
    corrupted = ["torch", "torchvision", "torchaudio", "_torch", "c10", "torch-2.12.0+cpu.dist-info"]
    
    for folder in corrupted:
        target = site_packages / folder
        if target.exists():
            log(f"Deleting: {target}")
            shutil.rmtree(target, ignore_errors=True)

    # 2. Force Clean Reinstall (CPU-ONLY)
    log("Installing Deterministic CPU-ONLY Torch (v2.1.2)...")
    # Using 2.1.2 as it's very stable for embeddable environments
    cmd = [
        str(RUNTIME_PY), "-m", "pip", "install", 
        "torch==2.1.2+cpu", "torchvision==0.16.2+cpu", "torchaudio==2.1.2+cpu",
        "--index-url", "https://download.pytorch.org/whl/cpu",
        "--no-cache-dir", "--force-reinstall"
    ]
    
    subprocess.run(cmd, check=True)
    
    # 3. Final Verification
    log("Running Runtime Validation...")
    verify_cmd = [str(RUNTIME_PY), "-c", "import torch; print(f'Success: Torch {torch.__version__} - Device: {torch.device(\"cpu\")} - Tensor: {torch.rand(2,2)}')"]
    result = subprocess.run(verify_cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        log("VALIDATION SUCCESSFUL.")
        print(result.stdout)
    else:
        log("VALIDATION FAILED.")
        print(result.stderr)
        sys.exit(1)

if __name__ == "__main__":
    fix()
