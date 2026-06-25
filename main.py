"""
M.A.Y.D.A.Y Physical Startup Engine — v5.0
=============================================
CPU Quantized GGUF Coding Agent.
No torch. No transformers. llama-cpp-python only.
Compliance: Non-blocking PyQt6 initialization, Safe-Mode, Asynchronous Loading.
"""
import sys
import os
import gc
import logging
import traceback
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Path Injection for Embedded Runtime
MAYDAY_ROOT = Path(__file__).resolve().parent
ROOT_DIR = MAYDAY_ROOT
sys.path.insert(0, str(MAYDAY_ROOT))

# Win32: register embedded DLL dirs before any native imports downstream
try:
    from mayday_runtime.paths import prepare_windows_dll_search_paths

    prepare_windows_dll_search_paths(MAYDAY_ROOT)
except Exception:
    pass

# Logging Configuration
LOG_DIR = MAYDAY_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
STARTUP_LOG = LOG_DIR / "startup_trace.log"
MAYDAY_LOG = LOG_DIR / "mayday.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(STARTUP_LOG), mode="w", encoding="utf-8"),
        logging.FileHandler(str(MAYDAY_LOG), mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger("mayday.main")
for noisy_logger in ("httpcore", "httpx"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

def run_verification():
    """Run a headless verification of the model backend."""
    logger.info("Running headless verification...")
    try:
        from model.loader import ModelLoader
        from model.inference import InferenceEngine
        
        loader = ModelLoader()
        available = loader.get_available_models()
        if not available:
            print("VERIFY: FAILED - No models found.")
            return False
            
        print("VERIFY: Selecting best viable local tier...")

        if not loader.load_best_available():
            print("VERIFY: FAILED - Could not load any viable local tier.")
            return False
            
        inference = InferenceEngine(loader)
        path = loader.model_dir / loader.active_tier_info["gguf_file"]
        if not inference.load_model(path):
            print("VERIFY: FAILED - Worker process failed to load.")
            return False
            
        ok, res = inference.run_inference_test()
        if ok:
            print(f"VERIFY: SUCCESS - Model generated: {res[:50]}...")
            return True
        else:
            print(f"VERIFY: FAILED - Inference test failed: {res}")
            return False
    except Exception as e:
        print(f"VERIFY: FAILED - Exception: {e}")
        logger.error(traceback.format_exc())
        return False
    finally:
        gc.collect()

def validate_runtime():
    """Physical check of the environment."""
    logger.info(f"CWD: {os.getcwd()}")
    logger.info(f"Exec: {sys.executable}")
    for p in ["core", "ui", "model", "tools"]:
        if not (MAYDAY_ROOT / p).exists():
            logger.error(f"Missing physical path: {p}")
            return False
    return True

def initialize_application():
    """PHYSICAL STARTUP ORDER: UI FIRST, THEN SERVICES."""
    logger.info("Initializing Physical Startup Flow (v5.0 GGUF)...")

    if not validate_runtime():
        print("CRITICAL: Runtime integrity check failed. See logs/startup_trace.log")
        sys.exit(1)

    # 1. Create QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("MAYDAY v5.0 Coding Agent")

    # 2. Early UI Initialization (Safe Mode Support)
    logger.info("Creating UI components...")
    from ui.main_window import MainWindow
    from model.downloader import ModelDownloader
    downloader = ModelDownloader()
    window = MainWindow(downloader=downloader)
    window.show()

    # 3. Deferred Services Initialization (non-blocking model load)
    def start_background_services():
        logger.info("Starting background services...")
        try:
            from core.orchestrator import Orchestrator
            from model.loader import ModelLoader
            from model.inference import InferenceEngine
            from runtime.engine import ExecutionEngine
            from runtime.api_manager import ApiManager
            from runtime.server_runner import ServerRunner
            from runtime import web_access
            from tools.file_tools import FileTools
            from tools.excel_tools import ExcelTools
            from tools.browser_tools import BrowserTools
            from tools.system_tools import SystemTools
            from tools.project_tools import ProjectTools
            from tools.powershell_tools import PowerShellTools
            from ui.bridge import ModelLoadThread

            loader = ModelLoader()
            window.loader = loader

            available = loader.get_available_models()

            def wire_orchestrator() -> None:
                web_access.configure_search()
                web_access.set_web_enabled(True)
                engine = ExecutionEngine()
                powershell_tool = PowerShellTools()
                engine.register_tools({
                    "file": FileTools(),
                    "excel": ExcelTools(),
                    "browser": BrowserTools(),
                    "system": SystemTools(),
                    "project": ProjectTools(),
                    "powershell": powershell_tool,
                    "shell": powershell_tool,
                    "server": ServerRunner(),
                })
                api = ApiManager()
                window.api_manager = api
                inference = InferenceEngine(loader)
                from core.model_router import ModelRouter

                router = ModelRouter(inference, api)
                window.orchestrator = Orchestrator(router, engine)
                if hasattr(engine, "set_gateway_callback"):
                    engine.set_gateway_callback(window.gateway_bridge.request_permission_sync)
                logger.info("Background services online.")
                gc.collect()

            if not available:
                window.update_model_status("Safe Mode: No models detected.")
                wire_orchestrator()
                return

            candidates = loader._select_load_candidates(available)
            best = candidates[0] if candidates else min(available, key=lambda t: t["tier"])
            quant = best.get("quantization", "Q4_K_M")
            window.update_model_status(
                f"Loading {best['name']} ({quant}) in background..."
            )

            def on_model_ready(ok: bool, message: str) -> None:
                if ok and loader.active_tier_info:
                    tier = loader.active_tier_info
                    window.update_model_status(
                        f"Online: {tier['name']} ({tier.get('quantization', 'Q4')})"
                    )
                else:
                    window.update_model_status(
                        f"Safe Mode: model load failed — {message or 'see logs'}"
                    )
                wire_orchestrator()
                gc.collect()

            mlt = ModelLoadThread(loader)
            mlt.finished_ok.connect(on_model_ready)
            mlt.start()
            window._model_load_thread = mlt

        except Exception as e:
            logger.error(f"Background service failure: {e}")
            logger.error(traceback.format_exc())
            window.update_model_status("Error: Service failure.")

    # Execute background services after UI event loop starts
    QTimer.singleShot(100, start_background_services)

    # 4. Return instances instead of blocking
    logger.info("Application initialized. Returning handles.")
    return app, window

if __name__ == "__main__":
    if "--verify" in sys.argv:
        if run_verification():
            sys.exit(0)
        else:
            sys.exit(1)

    try:
        app, window = initialize_application()
        logger.info("Entering PyQt6 event loop.")
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"FATAL STARTUP EXCEPTION: {e}")
        logger.critical(traceback.format_exc())
        print(f"FATAL: {e}")
        sys.exit(1)
