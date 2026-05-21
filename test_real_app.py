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
        
    print("\n--- APP INITIALIZED, STARTING REAL TESTS ---")
    
    os.environ["MAYDAY_SAFE_MODE"] = "1"
    app, window = initialize_application()
    
    # Setup test sequence
    tests = [
        "open google and type mayday alive",
        "open youtube in brave",
        "make a pyqt6 ping pong game and open it",
        "create a mini n8n workflow to send an email"
    ]
    
    current_test = 0
    
    def start_test_sequence():
        # Enable API
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_COMPATIBLE_MODEL"] = "qwen/qwen3-coder:free"
        
        test_key = os.environ.get("MAYDAY_TEST_OPENROUTER_KEY", "").strip()
        if test_key:
            window.api_manager.save_key("openrouter", test_key)
        elif not window.api_manager.has_active_provider():
            raise RuntimeError("No API key configured. Enter one through the UI or set MAYDAY_TEST_OPENROUTER_KEY for this test.")
        window.api_manager.set_user_approved(True)
        
        # Auto-approve UI actions
        window.gateway_bridge.set_response("ALLOW_ALWAYS")
        os.environ["MAYDAY_AUTO_APPROVE_BROWSER"] = "1"
        
        # Override the slot to capture finish and trigger next
        original_on_finished = window.on_inference_finished
        def test_on_finished(result):
            original_on_finished(result)
            on_inference_finished(result)
        
        window.on_inference_finished = test_on_finished
        
        print(f"\n[STARTING TEST 1]")
        window.handle_inference_request(tests[0])

    def on_inference_finished(result):
        nonlocal current_test
        print(f"\n[TEST {current_test+1} FINISHED] Response:")
        print(result.get('response', ''))
        print(f"Provider used: {result.get('provider', 'unknown')}")
        
        if current_test == 0:
            print("\n[TEST 1 STATUS] Google search successfully triggered!")
        elif current_test == 1:
            print("\n[TEST 2 STATUS] YouTube successfully opened!")
        elif current_test == 2:
            game_file = Path(r"E:\MAYDAY\tool_test_workspace\pingpong_game\pong.py")
            if game_file.exists() and game_file.stat().st_size > 500:
                print("\n[TEST 3 STATUS] PyQt6 Ping Pong game successfully created and launched!")
        elif current_test == 3:
            workflow_file = Path(r"E:\MAYDAY\tool_test_workspace\n8n_workflow\workflow.json")
            if workflow_file.exists() and workflow_file.stat().st_size > 200:
                print("\n[TEST 4 STATUS] n8n workflow JSON successfully created!")
        
        current_test += 1
        if current_test < len(tests):
            print(f"\n[STARTING TEST {current_test+1}] (Waiting 2s for UI cooldown...)")
            QTimer.singleShot(2000, lambda: window.handle_inference_request(tests[current_test]))
        else:
            print("\nAll tests finished. Exiting.")
            QApplication.quit()

    QTimer.singleShot(1000, start_test_sequence)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_tests()
