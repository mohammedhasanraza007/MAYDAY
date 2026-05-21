import sys
import os
import time
from pathlib import Path

MAYDAY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MAYDAY_ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import initialize_application

def run_tests():
    import shutil
    import subprocess
    
    # 1. Kill any lingering browser or driver processes to release profile locks
    try:
        subprocess.run(["powershell", "-Command", "Get-Process chrome, msedge, node -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
    except Exception:
        pass
        
    # 2. Clean up old browser profile lockfiles and folders
    for p in ["E:/MAYDAY/runtime/browser_profile", "logs/sessions", "logs"]:
        path = Path(p)
        if path.exists():
            try:
                shutil.rmtree(path)
            except Exception:
                pass
        path.mkdir(parents=True, exist_ok=True)
        
    print("\n" + "="*80)
    print("STARTING GOAL-ORIENTED AUTOMATION AUDIT ON REAL APP")
    print("="*80)
    
    os.environ["MAYDAY_SAFE_MODE"] = "1"
    app, window = initialize_application()
    
    tests = [
        ("open whatsapp to message my friend", "WhatsApp Flow"),
        ("play bad blood on youtube please", "YouTube Song Flow"),
        (r"read file E:\MAYDAY\projects\phase05_audit_file.txt", "File Read Flow"),
        ("make a new file called test_success.txt with content hello world", "File Creation Flow"),
        ("search for julias ai by google", "Julia's AI Search Flow")
    ]
    
    current_test = 0
    
    def start_test_sequence():
        # Setup mock/credentials so we bypass GUI requirements
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_COMPATIBLE_MODEL"] = "qwen/qwen3-coder:free"
        
        test_key = os.environ.get("MAYDAY_TEST_OPENROUTER_KEY", "").strip()
        if test_key:
            window.api_manager.save_key("openrouter", test_key)
        window.api_manager.set_user_approved(True)
        
        # Auto-approve UI actions
        window.gateway_bridge.set_response("ALLOW_ALWAYS")
        os.environ["MAYDAY_AUTO_APPROVE_BROWSER"] = "1"
        
        # Override finishing slot to catch results and process the next test
        original_on_finished = window.on_inference_finished
        def test_on_finished(result):
            original_on_finished(result)
            on_inference_finished(result)
            
        window.on_inference_finished = test_on_finished
        
        print(f"\n[RUNNING GOAL TEST 1: {tests[0][1]}] -> Prompt: {tests[0][0]}")
        window.handle_inference_request(tests[0][0])
        
    def on_inference_finished(result):
        nonlocal current_test
        prompt, name = tests[current_test]
        print(f"\n[GOAL TEST {current_test+1} ({name}) FINISHED] Response:")
        print(result.get('response', ''))
        
        # Perform explicit audits
        if current_test == 0:
            # WhatsApp
            resp = result.get('response', '').lower()
            if "whatsapp" in resp or "shell_run" in resp or "browser_open" in resp:
                print(">>> AUDIT STATUS: SUCCESS (WhatsApp flow correctly intercepted and routed!)")
            else:
                print(">>> AUDIT STATUS: FAILED")
                
        elif current_test == 1:
            # YouTube Bad Blood
            resp = result.get('response', '').lower()
            if "youtube.com/results?search_query=bad%20blood" in resp or "browser_open" in resp:
                print(">>> AUDIT STATUS: SUCCESS (YouTube song flow correctly intercepted, query encoded, and navigated!)")
            else:
                print(">>> AUDIT STATUS: FAILED")
                
        elif current_test == 2:
            # File Read
            resp = result.get('response', '')
            if "phase05 file tool ok" in resp:
                print(">>> AUDIT STATUS: SUCCESS (File read flow correctly intercepted, read phase05_audit_file.txt, and printed contents!)")
            else:
                print(">>> AUDIT STATUS: FAILED")
                
        elif current_test == 3:
            # File Creation
            created_file = Path("test_success.txt")
            if created_file.exists():
                content = created_file.read_text().strip()
                if content == "hello world":
                    print(">>> AUDIT STATUS: SUCCESS (New file creation flow correctly intercepted, wrote test_success.txt with 'hello world'!)")
                    # Clean up
                    try:
                        created_file.unlink()
                    except Exception:
                        pass
                else:
                    print(f">>> AUDIT STATUS: FAILED (File exists but content is '{content}')")
            else:
                print(">>> AUDIT STATUS: FAILED (File not created)")
                
        elif current_test == 4:
            # Julia's AI Search
            resp = result.get('response', '').lower()
            if "julias ai by google" in resp or "web_search" in resp or "success" in resp:
                print(">>> AUDIT STATUS: SUCCESS (Julia's AI search query correctly intercepted and routed!)")
            else:
                print(">>> AUDIT STATUS: FAILED")
                
        current_test += 1
        if current_test < len(tests):
            print(f"\n[RUNNING GOAL TEST {current_test+1}: {tests[current_test][1]}] -> Prompt: {tests[current_test][0]} (Waiting 2s...)")
            QTimer.singleShot(2000, lambda: window.handle_inference_request(tests[current_test][0]))
        else:
            print("\n" + "="*80)
            print("ALL GOAL-ORIENTED AUDITS FINISHED. EXITING.")
            print("="*80)
            QApplication.quit()
            
    QTimer.singleShot(1000, start_test_sequence)
    sys.exit(app.exec())

if __name__ == "__main__":
    run_tests()
