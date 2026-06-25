"""
M.A.Y.D.A.Y Main Window — v5.0 Fully Integrated
==================================================
Compliance: Sidebar navigation, Chat, Model Manager, API, Dashboard.
Thread cleanup on finish. RAM tracking via psutil.
"""
import gc
import logging
import os

import psutil
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QStackedWidget, QStatusBar, QFrame, QLabel, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer

from ui.theme import THEME, FONTS, SIDEBAR_STYLE, SIDEBAR_BTN_STYLE
from ui.panels import (ChatPanel, ModelManagerPanel, LogsPanel,
                       DashboardPanel, APIManagerPanel)
from ui.bridge import InferenceThread, LogSignalHandler, DownloadThread, GatewaySignalBridge
from model.downloader import DOWNLOAD_TARGETS
from runtime.permission_gate import permission_gate
from runtime.provider_config import provider_config

logger = logging.getLogger("mayday.ui")


class MainWindow(QMainWindow):
    def __init__(self, orchestrator=None, loader=None, downloader=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.loader = loader
        self.downloader = downloader
        self.api_manager = None
        self.active_threads: list = []

        self.gateway_bridge = GatewaySignalBridge()
        self.gateway_bridge.permission_requested.connect(self._show_permission_dialog)

        # Inject gateway callback to engine if available
        if self.orchestrator and hasattr(self.orchestrator, 'engine'):
            self.orchestrator.engine.set_gateway_callback(self.gateway_bridge.request_permission_sync)

        self.setWindowTitle("M.A.Y.D.A.Y v5.0 — CPU Quantized Coding Agent")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(f"background-color: {THEME.BG}; color: {THEME.TEXT}; font-family: '{FONTS['primary']}';")

        # 1. Root Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 2. Components
        self._setup_sidebar()
        self._setup_content_area()
        self._setup_status_bar()
        self._setup_logging_bridge()
        self._setup_stats_timer()

        # Initial Page
        self.switch_panel(0)

    def _setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setStyleSheet(SIDEBAR_STYLE)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(20, 40, 20, 20)
        layout.setSpacing(8)

        title = QLabel("M.A.Y.D.A.Y")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {THEME.ACCENT_GREEN}; margin-bottom: 20px;")
        layout.addWidget(title)

        self.nav_buttons = []
        nav_items = [
            ("Factory Dashboard", 0),
            ("Chat Assistant", 1),
            ("Model Manager", 2),
            ("API Configuration", 3),
            ("System Logs", 4)
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setStyleSheet(SIDEBAR_BTN_STYLE)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _, i=index: self.switch_panel(i))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()
        version = QLabel("v5.0 CPU GGUF Build")
        version.setStyleSheet(f"color: {THEME.DIM}; font-size: 11px;")
        layout.addWidget(version)

        self.main_layout.addWidget(self.sidebar)

    def _setup_content_area(self):
        self.content_stack = QStackedWidget()

        # Panels
        self.pane_dashboard = DashboardPanel()
        self.pane_chat = ChatPanel()
        self.pane_models = ModelManagerPanel(DOWNLOAD_TARGETS)
        self.pane_api = APIManagerPanel()
        self.pane_logs = LogsPanel()

        # Connections — Chat & Model Manager
        self.pane_chat.send_prompt.connect(self.handle_inference_request)
        self.pane_models.download_model.connect(self.handle_download_request)
        self.pane_models.load_model.connect(self.handle_load_request)



        self.pane_api.api_keys_saved.connect(self.handle_api_key_save)
        self.pane_api.api_approval_changed.connect(self.handle_api_approval_changed)
        self.pane_api.provider_config_saved.connect(self.handle_provider_config_save)
        self.pane_api.permission_blocks_reset.connect(self.handle_permission_blocks_reset)

        # Add to stack in order of nav_items
        self.content_stack.addWidget(self.pane_dashboard)
        self.content_stack.addWidget(self.pane_chat)
        self.content_stack.addWidget(self.pane_models)
        self.content_stack.addWidget(self.pane_api)
        self.content_stack.addWidget(self.pane_logs)

        self.main_layout.addWidget(self.content_stack)

    def _setup_status_bar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("System Operational")

    def _setup_logging_bridge(self):
        self.log_handler = LogSignalHandler()
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.log_handler.new_log.connect(self.pane_logs.append_log)
        logging.getLogger().addHandler(self.log_handler)

    def _setup_stats_timer(self):
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_dashboard_stats)
        self.stats_timer.start(2000)  # Every 2 seconds

    def _update_dashboard_stats(self):
        # Clean up finished threads (prevent accumulation)
        self.active_threads = [t for t in self.active_threads if t.isRunning()]

        # Process RAM (not system RAM — more useful for leak detection)
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / (1024 * 1024)
        ram_str = f"{ram_mb:.0f} MB"

        # Model State
        model_name = "None"
        if self.loader and self.loader.is_loaded():
            tier = self.loader.active_tier_info
            if tier:
                model_name = f"{tier['name']} ({tier.get('quantization', 'Q4')})"
            else:
                model_name = "Generic Loaded"

        # Runtime Status
        status = "ONLINE"
        if not self.loader or not self.loader.is_loaded():
            status = "SAFE MODE"
        elif self.orchestrator and hasattr(self.orchestrator.router, "inference"):
            inference = self.orchestrator.router.inference
            if getattr(inference, "_active_model_path", None) is not None and not inference.verify_health():
                status = "BACKEND ERROR"

        # Routing State
        routing = "IDLE"
        if any(t.isRunning() for t in self.active_threads):
            routing = "PROCESSING"

        self.pane_dashboard.update_stats(ram_str, model_name, status, routing)

    @pyqtSlot(int)
    def switch_panel(self, index):
        self.content_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        if index == 2:
            self._refresh_model_status()

    def _refresh_model_status(self):
        if self.downloader:
            try:
                status_map = self.downloader.check_available()
                for tier_id, exists in status_map.items():
                    label = "Downloaded" if exists else "Missing"
                    # If currently loaded, mark as ACTIVE
                    if self.loader and self.loader.is_loaded() and self.loader.active_tier_info:
                        if self.loader.active_tier_info.get("tier") == tier_id:
                            label = "ACTIVE"
                    self.pane_models.update_tier_status(tier_id, label)
            except Exception as e:
                logger.error(f"Failed to refresh model status: {e}")

    # ── Chat / Inference Handlers ─────────────────────────────────────────

    def handle_inference_request(self, prompt):
        self.status.showMessage("Assistant is thinking...")
        
        # Trigger actual UI input state as if user typed it
        self.pane_chat.append_message("User", prompt)
        
        thread = InferenceThread(self.orchestrator, prompt)
        thread.finished.connect(self.on_inference_finished)
        thread.error.connect(lambda e: self.pane_chat.append_message("System", f"Error: {e}"))
        thread.start()
        self.active_threads.append(thread)

    def on_inference_finished(self, result):
        self.pane_chat.append_message("Assistant", result['response'])
        self.status.showMessage("Inference complete.")
        gc.collect()  # Post-inference cleanup

    @pyqtSlot(str, str)
    def _show_permission_dialog(self, action_type, details):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("MAYDAY Safety Gateway: Action Requested")
        msg.setText(f"<b>Action Type:</b> {action_type}")
        
        # Limit details length to prevent massive dialogs
        display_details = details if len(details) < 800 else details[:800] + "\n... [TRUNCATED]"
        msg.setInformativeText(display_details)
        
        btn_allow = msg.addButton("Allow", QMessageBox.ButtonRole.AcceptRole)
        btn_allow_always = msg.addButton("Allow Always", QMessageBox.ButtonRole.AcceptRole)
        btn_deny = msg.addButton("Deny", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_deny)
        
        msg.exec()
        
        if msg.clickedButton() == btn_allow:
            self.gateway_bridge.set_response("ALLOW")
        elif msg.clickedButton() == btn_allow_always:
            self.gateway_bridge.set_response("ALLOW_ALWAYS")
        else:
            self.gateway_bridge.set_response("DENY")

    # ── Model Download / Load Handlers ────────────────────────────────────

    def handle_download_request(self, tier):
        self.status.showMessage(f"Starting download for Tier {tier}...")
        thread = DownloadThread(self.downloader, tier)
        thread.progress.connect(self.pane_models.on_download_progress)
        thread.finished.connect(self._on_download_finished)
        thread.start()
        self.active_threads.append(thread)

    def _on_download_finished(self, tier, ok, message):
        self._refresh_model_status()
        if ok:
            self.status.showMessage(f"Tier {tier} download complete.")
        else:
            self.status.showMessage(f"Tier {tier} download failed: {message}")

    def handle_load_request(self, tier):
        self.status.showMessage(f"Loading Model Tier {tier}...")
        if self.loader:
            success = self.loader.load_tier(tier)
            if success:
                # CRITICAL: Real inference test after load
                self.status.showMessage(f"Verifying Tier {tier}...")
                if self.orchestrator and hasattr(self.orchestrator.router, "inference"):
                    # Ensure worker also loads it
                    path = self.loader.model_dir / self.loader.active_tier_info["gguf_file"]
                    worker_ok = self.orchestrator.router.inference.load_model(path)
                    if worker_ok:
                        test_ok, test_res = self.orchestrator.router.inference.run_inference_test()
                        if test_ok:
                            self.status.showMessage(f"Model Tier {tier} Loaded and Verified.")
                            self._refresh_model_status()
                            self.pane_models.update_tier_status(tier, "ACTIVE")
                            return
                        else:
                            self.status.showMessage(f"Verification FAILED: {test_res[:50]}")
                    else:
                        self.status.showMessage("Worker process failed to load model.")
                else:
                    self.status.showMessage(f"Model Tier {tier} Loaded (In-Process Only).")
                    self._refresh_model_status()
                    self.pane_models.update_tier_status(tier, "ACTIVE")
                    return

            self.loader.destroy_model()
            self.status.showMessage(f"Failed to load/verify Tier {tier}.")
            self._refresh_model_status()



    # ── Public API ────────────────────────────────────────────────────────

    def handle_api_key_save(self, keys: dict):
        if self.api_manager is None:
            self.pane_api.update_status("Runtime not ready; keys were not saved")
            self.status.showMessage("API runtime not ready.")
            return

        saved = []
        try:
            for provider, key in keys.items():
                self.api_manager.save_key(provider, key)
                saved.append(provider)
        except Exception as e:
            self.pane_api.update_status(f"Key save failed: {e}")
            self.status.showMessage("API key save failed.")
            return

        providers = ", ".join(saved)
        self.pane_api.update_status(f"Encrypted key saved for: {providers}")
        self.status.showMessage("API key saved to encrypted backend store.")

    def handle_api_approval_changed(self, allowed: bool):
        if self.api_manager is None:
            self.pane_api.update_status("Runtime not ready; approval was not changed")
            self.status.showMessage("API runtime not ready.")
            return

        self.api_manager.set_user_approved(allowed)
        if allowed:
            self.pane_api.update_status("API fallback approved for this session")
            self.status.showMessage("API fallback approved for this session.")
        else:
            self.pane_api.update_status("API fallback disabled")
            self.status.showMessage("API fallback disabled.")

    def handle_provider_config_save(self, config: dict):
        try:
            if self.api_manager is not None:
                self.api_manager.save_provider_config(config)
            else:
                provider_config.save(config)
            self.pane_api.update_status("Runtime provider configuration saved")
            self.status.showMessage("Runtime provider configuration saved.")
        except Exception as e:
            self.pane_api.update_status(f"Provider config save failed: {e}")
            self.status.showMessage("Provider config save failed.")

    def handle_permission_blocks_reset(self):
        self.gateway_bridge.reset_denials()
        permission_gate.reset()
        if self.orchestrator and hasattr(self.orchestrator, "engine"):
            gateway = getattr(self.orchestrator.engine, "gateway", None)
            reset = getattr(gateway, "reset_denials", None)
            if callable(reset):
                reset()
        self.pane_api.update_status("Permission blocks reset; future actions will ask again")
        self.status.showMessage("Permission blocks reset.")

    def update_model_status(self, text):
        self.status.showMessage(text)
