"""
M.A.Y.D.A.Y Diagnostic & Cleanup Tools
======================================
Handles process termination and file lock detection.
"""
import os
import sys
import psutil
import signal
import time
from pathlib import Path

def kill_mayday_processes():
    """Terminate any python/pip processes running from the MAYDAY directory."""
    current_pid = os.getpid()
    root_dir = str(Path(__file__).parent.parent.absolute()).lower()
    print(f"[CLEANUP] Searching for processes in {root_dir}...")
    
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            exe_path = proc.info['exe']
            if exe_path and root_dir in exe_path.lower():
                if proc.info['pid'] != current_pid:
                    print(f"[CLEANUP] Killing process {proc.info['pid']} ({proc.info['name']}) at {exe_path}")
                    proc.terminate()
                    # Wait and force kill if needed
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        print(f"[CLEANUP] Force killing {proc.info['pid']}...")
                        proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

def detect_locks(target_path):
    """Attempt to detect which process is locking a file (requires administrative privileges often)."""
    target_path = str(Path(target_path).absolute()).lower()
    print(f"[DIAGNOSTIC] Checking locks for {target_path}...")
    
    locked_by = []
    for proc in psutil.process_iter(['pid', 'name', 'open_files']):
        try:
            for file in proc.info['open_files'] or []:
                if target_path in file.path.lower():
                    locked_by.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return locked_by

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--kill":
        kill_mayday_processes()
        print("[CLEANUP] Process cleanup finished.")
    elif len(sys.argv) > 1 and sys.argv[1] == "--check":
        locks = detect_locks(sys.argv[2] if len(sys.argv) > 2 else ".")
        if locks:
            print(f"[DIAGNOSTIC] Locked by: {', '.join(locks)}")
        else:
            print("[DIAGNOSTIC] No obvious locks detected via psutil.")
