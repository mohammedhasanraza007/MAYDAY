"""
M.A.Y.D.A.Y E2E Inference & RAM Cleanup Test
============================================
Tests: Model Load -> Code Generation -> Process Cleanup -> RAM Release.
"""
import os
import sys
import time
import psutil
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(ROOT_DIR))

from model.inference import InferenceEngine

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

def test_e2e():
    print("=== M.A.Y.D.A.Y E2E STRESS TEST ===")
    
    engine = InferenceEngine()
    model_path = ROOT_DIR / "models" / "tier1.gguf"
    
    if not model_path.exists():
        print(f"[FAIL] Model missing: {model_path}")
        return

    ram_start = get_ram()
    print(f"RAM Initial: {ram_start:.2f} MB")

    # 1. Load Model
    print(f"Loading {model_path.name}...")
    if not engine.load_model(model_path):
        print("[FAIL] Model load failed.")
        return
    
    # Check for worker process
    worker_proc = engine._worker_process
    if worker_proc:
        worker_ram = psutil.Process(worker_proc.pid).memory_info().rss / (1024 * 1024)
        print(f"Worker Process ID: {worker_proc.pid}, RAM: {worker_ram:.2f} MB")

    # 2. Generate Code
    prompt = "Write a Python function to calculate the Fibonacci sequence up to N terms."
    print(f"Prompt: {prompt}")
    
    start_time = time.time()
    response = engine.generate(prompt, max_tokens=256)
    duration = time.time() - start_time
    
    print(f"\n--- Model Response ({duration:.2f}s) ---\n")
    print(response)
    print("\n---------------------------\n")

    if "def" in response.lower() and "fibonacci" in response.lower():
        print("[PASS] Generation content verified.")
    else:
        print("[WARN] Generation content might be incomplete.")

    # 3. Cleanup & Verify RAM
    print("\nTriggering hard cleanup...")
    engine.cleanup()
    time.sleep(2) # Wait for OS to reclaim

    # Verify worker is gone
    if worker_proc and not psutil.pid_exists(worker_proc.pid):
        print("[PASS] Worker process terminated.")
    else:
        print("[FAIL] Worker process still alive!")

    ram_end = get_ram()
    print(f"RAM Final: {ram_end:.2f} MB")
    
    if ram_end <= ram_start + 50: # Allow small buffer for python overhead
        print("[PASS] RAM Lifecycle verified (No leak).")
    else:
        print(f"[FAIL] RAM Leak detected: +{ram_end - ram_start:.2f} MB")

if __name__ == "__main__":
    test_e2e()
