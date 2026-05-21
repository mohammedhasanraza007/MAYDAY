"""
M.A.Y.D.A.Y System Validation Report
====================================
Verifies model load, inference, tools, and RAM cleanup.
"""
import os
import sys
import psutil
import time
import logging
from pathlib import Path

# Setup logging
log_path = Path("logs/system_validation_report.txt")
log_path.parent.mkdir(exist_ok=True)
logging.basicConfig(filename=log_path, level=logging.INFO, format='%(message)s', filemode='w')

def log(msg):
    print(msg)
    logging.info(msg)

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

def run_checks():
    log("=== M.A.Y.D.A.Y SYSTEM VALIDATION ===")
    log(f"Time: {time.ctime()}")
    
    # 1. Environment Check
    log(f"\n[1] Environment: {sys.executable}")
    
    # 2. Model Backend Check
    try:
        from llama_cpp import Llama
        log("[2] llama-cpp-python: INSTALLED")
    except ImportError:
        log("[2] llama-cpp-python: MISSING")
        return

    # 3. Isolated Worker Check
    try:
        from model.inference import InferenceEngine
        engine = InferenceEngine()
        log("[3] InferenceEngine: INITIALIZED")
        
        ram_before = get_ram()
        log(f"RAM Before: {ram_before:.2f} MB")
        
        # Test model exists
        model_path = Path("models/tier1.gguf")
        if model_path.exists():
            log(f"[4] Testing Tier 1 Model Load: {model_path}")
            if engine.load_model(model_path):
                log("Load: SUCCESS")
                res = engine.generate("Hello", max_tokens=10)
                log(f"Inference Test: {res[:50]}...")
            else:
                log("Load: FAILED")
        else:
            log("[4] Tier 1 Model: MISSING (Skipping load test)")
            
        engine.kill_worker()
        time.sleep(1)
        ram_after = get_ram()
        log(f"RAM After Cleanup: {ram_after:.2f} MB")
        
    except Exception as e:
        log(f"[ERROR] Inference test failed: {e}")

    # 4. Tool Check
    try:
        from tools.physical_tools import FileTools
        ft = FileTools()
        res = ft.execute({"action": "list", "path": "."})
        log(f"\n[5] Tool Execution Test (File List): {len(res)} items found")
    except Exception as e:
        log(f"[ERROR] Tool test failed: {e}")

    log("\n=== VALIDATION COMPLETE ===")
    log(f"Report saved to {log_path}")

if __name__ == "__main__":
    run_checks()
