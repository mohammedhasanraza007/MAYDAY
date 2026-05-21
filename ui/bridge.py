"""
M.A.Y.D.A.Y Async Bridge — v4.5 Hardened
========================================
Compliance: Thread exception isolation, Crash-safe workers.
"""
import logging
import traceback
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QObject

class GatewaySignalBridge(QObject):
    permission_requested = pyqtSignal(str, str) # action_type, details
    
    def __init__(self):
        super().__init__()
        self._event = threading.Event()
        self._response = "DENY"
        self._blocked = False
        
    def request_permission_sync(self, action_type: str, details: str) -> str:
        """Called by the background thread (gateway) to block and wait for UI."""
        if self._response == "ALLOW_ALWAYS":
            return "ALLOW_ALWAYS"
        if self._blocked:
            return "DENY"
        self._event.clear()
        self.permission_requested.emit(action_type, details)
        self._event.wait()
        return self._response
        
    def set_response(self, response: str):
        """Called by the UI thread to unblock the background thread."""
        self._response = response
        if response == "DENY":
            self._blocked = True
        elif response in {"ALLOW_ALWAYS", "ALLOW"}:
            self._blocked = False
        self._event.set()

    def reset_denials(self) -> None:
        self._blocked = False
        if self._response == "DENY":
            self._response = "ALLOW"

class InferenceThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, orchestrator, prompt):
        super().__init__()
        self.orchestrator = orchestrator
        self.prompt = prompt

    def run(self):
        try:
            if not self.orchestrator:
                raise RuntimeError("Orchestrator not initialized.")
            
            result = self.orchestrator.process_prompt(self.prompt)
            self.finished.emit(result)
        except Exception as e:
            # Thread exception isolation
            self.error.emit(str(e))

class ModelLoadThread(QThread):
    """Load best local model without blocking the Qt GUI thread."""

    finished_ok = pyqtSignal(bool, str)

    def __init__(self, loader, timeout_sec: int = 7200):
        super().__init__()
        self.loader = loader
        self.timeout_sec = timeout_sec

    def run(self):
        try:
            ok = self.loader.load_best_available()
            self.finished_ok.emit(ok, "" if ok else "Model load returned False")
        except Exception as e:
            self.finished_ok.emit(False, str(e))


class DownloadThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, bool, str) # tier, success, message

    def __init__(self, downloader, tier):
        super().__init__()
        self.downloader = downloader
        self.tier = tier

    def run(self):
        try:
            self.downloader.set_progress_callback(
                lambda t, p, s: self.progress.emit(t, p, s)
            )
            self.downloader.download_tier(self.tier)
            self.finished.emit(self.tier, True, "Download Complete")
        except Exception as e:
            # DL-001 Fix: Isolated exception capture
            self.finished.emit(self.tier, False, str(e))

class LogSignalHandler(logging.Handler, QObject):
    new_log = pyqtSignal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record):
        try:
            msg = self.format(record)
            self.new_log.emit(msg)
        except:
            pass
