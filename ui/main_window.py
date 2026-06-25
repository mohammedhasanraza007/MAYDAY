"""
M.A.Y.D.A.Y Main Window - PyQt6 tab workspace.
"""
from __future__ import annotations

import gc
import logging
import os
from pathlib import Path

import psutil
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from model.downloader import DOWNLOAD_TARGETS
from runtime.permission_gate import permission_gate
from runtime.provider_config import provider_config
from ui.bridge import DownloadThread, GatewaySignalBridge, InferenceThread, LogSignalHandler
from ui.panels import (
    APIManagerPanel,
    AgentStreamPanel,
    ChatPanel,
    DashboardPanel,
    FileExplorerPanel,
    LogsPanel,
    ModelManagerPanel,
    SkillManagerPanel,
    TerminalPanel,
)
from ui.theme import FONTS, THEME

logger = logging.getLogger("mayday.ui")


class MainWindow(QMainWindow):
    def __init__(self, orchestrator=None, loader=None, downloader=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.loader = loader
        self.downloader = downloader
        self.api_manager = None
        self.active_threads: list = []
        self._tree_items_by_tab: dict[int, QStandardItem] = {}

        self.gateway_bridge = GatewaySignalBridge()
        self.gateway_bridge.permission_requested.connect(self._show_permission_dialog)

        if self.orchestrator and hasattr(self.orchestrator, "engine"):
            self.orchestrator.engine.set_gateway_callback(self.gateway_bridge.request_permission_sync)

        self.setWindowTitle("M.A.Y.D.A.Y v5.0 - Coding Agent")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(
            f"background-color: {THEME.BG}; color: {THEME.TEXT}; "
            f"font-family: '{FONTS['primary']}';"
        )

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_splitter_workspace()
        self._setup_status_bar()
        self._setup_logging_bridge()
        self._setup_stats_timer()
        self.switch_panel(0)

    def _setup_splitter_workspace(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.nav_frame = QFrame()
        self.nav_frame.setMinimumWidth(240)
        self.nav_frame.setMaximumWidth(280)
        self.nav_frame.setStyleSheet(
            f"QFrame {{ background-color: {THEME.PANEL_BG}; border-right: 1px solid {THEME.BORDER}; }}"
        )
        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(12, 18, 12, 12)
        nav_layout.setSpacing(10)

        title = QLabel("M.A.Y.D.A.Y")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {THEME.ACCENT_GREEN};"
        )
        nav_layout.addWidget(title)

        self.nav_tree = QTreeView()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setUniformRowHeights(True)
        self.nav_tree.setAnimated(False)
        self.nav_tree.setStyleSheet(
            f"QTreeView {{ background-color: {THEME.PANEL_BG}; color: {THEME.TEXT}; "
            f"border: none; font-size: 13px; outline: 0; }}"
            f"QTreeView::item {{ padding: 6px 4px; }}"
            f"QTreeView::item:selected {{ background-color: {THEME.TAB_ACTIVE}; color: {THEME.ACTION_BLUE}; }}"
        )
        self.nav_model = QStandardItemModel(self.nav_tree)
        self.nav_tree.setModel(self.nav_model)
        self._populate_navigation_tree()
        self.nav_tree.expandAll()
        self.nav_tree.selectionModel().currentChanged.connect(self._handle_nav_selected)
        nav_layout.addWidget(self.nav_tree, 1)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 0; background: {THEME.BG}; }}"
            f"QTabBar::tab {{ background: {THEME.TAB_BG}; color: {THEME.DIM}; "
            f"padding: 10px 14px; border: 0; min-width: 86px; }}"
            f"QTabBar::tab:selected {{ background: {THEME.TAB_ACTIVE}; color: {THEME.TEXT}; "
            f"border-bottom: 2px solid {THEME.ACTION_BLUE}; }}"
        )
        self.tabs.currentChanged.connect(self.switch_panel)
        self._setup_tabs()

        self.splitter.addWidget(self.nav_frame)
        self.splitter.addWidget(self.tabs)
        self.splitter.setSizes([240, 960])
        self.main_layout.addWidget(self.splitter)

    def _setup_tabs(self) -> None:
        self.pane_chat = ChatPanel()
        self.pane_stream = AgentStreamPanel()
        self.pane_terminal = TerminalPanel()
        self.pane_files = FileExplorerPanel(str(Path(__file__).resolve().parent.parent))
        self.pane_models = ModelManagerPanel(DOWNLOAD_TARGETS)
        self.pane_api = APIManagerPanel()
        self.pane_skills = SkillManagerPanel()
        self.pane_logs = LogsPanel()
        self.pane_dashboard = DashboardPanel()

        self.pane_chat.send_prompt.connect(self.handle_inference_request)
        self.pane_models.download_model.connect(self.handle_download_request)
        self.pane_models.load_model.connect(self.handle_load_request)
        self.pane_api.api_keys_saved.connect(self.handle_api_key_save)
        self.pane_api.api_approval_changed.connect(self.handle_api_approval_changed)
        self.pane_api.provider_config_saved.connect(self.handle_provider_config_save)
        self.pane_api.permission_blocks_reset.connect(self.handle_permission_blocks_reset)

        for label, widget in [
            ("Chat", self.pane_chat),
            ("AgentStream", self.pane_stream),
            ("Terminal", self.pane_terminal),
            ("Files", self.pane_files),
            ("Models", self.pane_models),
            ("API", self.pane_api),
            ("Skills", self.pane_skills),
            ("Logs", self.pane_logs),
            ("Dashboard", self.pane_dashboard),
        ]:
            self.tabs.addTab(widget, label)

    def _populate_navigation_tree(self) -> None:
        self.nav_model.clear()
        workspace = QStandardItem("Workspace")
        workspace.setEditable(False)
        skills = QStandardItem("Skills")
        skills.setEditable(False)
        skills.setData(6, Qt.ItemDataRole.UserRole)

        for index, label in enumerate(
            [
                "Chat",
                "AgentStream",
                "Terminal",
                "Files",
                "Models",
                "API",
                "Skills",
                "Logs",
                "Dashboard",
            ]
        ):
            item = QStandardItem(label)
            item.setEditable(False)
            item.setData(index, Qt.ItemDataRole.UserRole)
            workspace.appendRow(item)
            self._tree_items_by_tab[index] = item

        for skill_name in self._load_skill_names():
            item = QStandardItem(skill_name)
            item.setEditable(False)
            item.setData(6, Qt.ItemDataRole.UserRole)
            skills.appendRow(item)

        self.nav_model.appendRow(workspace)
        self.nav_model.appendRow(skills)

    def _load_skill_names(self) -> list[str]:
        try:
            from core.skill_loader import skill_loader

            skill_loader.load()
            return [skill.name for skill in skill_loader._skills[:30]]
        except Exception as exc:
            logger.debug("Could not populate skill navigation: %s", exc)
            return []

    def _handle_nav_selected(self, current, _previous) -> None:
        item = self.nav_model.itemFromIndex(current)
        if item is None:
            return
        target = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(target, int):
            self.switch_panel(target)

    def _setup_status_bar(self) -> None:
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("System Operational")

    def _setup_logging_bridge(self) -> None:
        self.log_handler = LogSignalHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self.log_handler.new_log.connect(self.pane_logs.append_log)
        logging.getLogger().addHandler(self.log_handler)

    def _setup_stats_timer(self) -> None:
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_dashboard_stats)
        self.stats_timer.start(2000)

    def _update_dashboard_stats(self) -> None:
        self.active_threads = [thread for thread in self.active_threads if thread.isRunning()]
        process = psutil.Process(os.getpid())
        ram_str = f"{process.memory_info().rss / (1024 * 1024):.0f} MB"

        model_name = "None"
        if self.loader and self.loader.is_loaded():
            tier = self.loader.active_tier_info
            model_name = f"{tier['name']} ({tier.get('quantization', 'Q4')})" if tier else "Generic Loaded"

        status = "ONLINE"
        if not self.loader or not self.loader.is_loaded():
            status = "SAFE MODE"
        elif self.orchestrator and hasattr(self.orchestrator.router, "inference"):
            inference = self.orchestrator.router.inference
            if getattr(inference, "_active_model_path", None) is not None and not inference.verify_health():
                status = "BACKEND ERROR"

        routing = "PROCESSING" if any(thread.isRunning() for thread in self.active_threads) else "IDLE"
        self.pane_dashboard.update_stats(ram_str, model_name, status, routing)

    @pyqtSlot(int)
    def switch_panel(self, index: int) -> None:
        if not hasattr(self, "tabs"):
            return
        if 0 <= index < self.tabs.count() and self.tabs.currentIndex() != index:
            self.tabs.setCurrentIndex(index)
        item = self._tree_items_by_tab.get(index)
        if item is not None:
            self.nav_tree.setCurrentIndex(item.index())
        if index == 4:
            self._refresh_model_status()

    def _refresh_model_status(self) -> None:
        if self.downloader:
            try:
                status_map = self.downloader.check_available()
                for tier_id, exists in status_map.items():
                    label = "Downloaded" if exists else "Missing"
                    if self.loader and self.loader.is_loaded() and self.loader.active_tier_info:
                        if self.loader.active_tier_info.get("tier") == tier_id:
                            label = "ACTIVE"
                    self.pane_models.update_tier_status(tier_id, label)
            except Exception as exc:
                logger.error("Failed to refresh model status: %s", exc)

    def handle_inference_request(self, prompt: str) -> None:
        self.status.showMessage("Assistant is thinking...")
        self.pane_chat.append_message("User", prompt)

        thread = InferenceThread(self.orchestrator, prompt)
        thread.finished.connect(self.on_inference_finished)
        thread.error.connect(lambda error: self.pane_chat.append_message("System", f"Error: {error}"))
        try:
            from core.event_stream import agent_event_stream

            agent_event_stream.subscribe(self.pane_stream._on_event)
        except Exception:
            pass
        thread.start()
        self.active_threads.append(thread)

    def on_inference_finished(self, result: dict) -> None:
        self.pane_chat.append_message("Assistant", result["response"])
        self.status.showMessage("Inference complete.")
        gc.collect()

    @pyqtSlot(str, str)
    def _show_permission_dialog(self, action_type: str, details: str) -> None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("MAYDAY Safety Gateway: Action Requested")
        msg.setText(f"<b>Action Type:</b> {action_type}")
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

    def handle_download_request(self, tier: int) -> None:
        self.status.showMessage(f"Starting download for Tier {tier}...")
        thread = DownloadThread(self.downloader, tier)
        thread.progress.connect(self.pane_models.on_download_progress)
        thread.finished.connect(self._on_download_finished)
        thread.start()
        self.active_threads.append(thread)

    def _on_download_finished(self, tier: int, ok: bool, message: str) -> None:
        self._refresh_model_status()
        self.status.showMessage(
            f"Tier {tier} download complete." if ok else f"Tier {tier} download failed: {message}"
        )

    def handle_load_request(self, tier: int) -> None:
        self.status.showMessage(f"Loading Model Tier {tier}...")
        if not self.loader:
            self.status.showMessage("No loader available.")
            return

        success = self.loader.load_tier(tier)
        if success:
            self.status.showMessage(f"Verifying Tier {tier}...")
            if self.orchestrator and hasattr(self.orchestrator.router, "inference"):
                path = self.loader.model_dir / self.loader.active_tier_info["gguf_file"]
                worker_ok = self.orchestrator.router.inference.load_model(path)
                if worker_ok:
                    test_ok, test_res = self.orchestrator.router.inference.run_inference_test()
                    if test_ok:
                        self.status.showMessage(f"Model Tier {tier} Loaded and Verified.")
                        self._refresh_model_status()
                        self.pane_models.update_tier_status(tier, "ACTIVE")
                        return
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

    def handle_api_key_save(self, keys: dict) -> None:
        if self.api_manager is None:
            self.pane_api.update_status("Runtime not ready; keys were not saved")
            self.status.showMessage("API runtime not ready.")
            return

        saved = []
        try:
            for provider, key in keys.items():
                self.api_manager.save_key(provider, key)
                saved.append(provider)
        except Exception as exc:
            self.pane_api.update_status(f"Key save failed: {exc}")
            self.status.showMessage("API key save failed.")
            return

        self.pane_api.update_status(f"Encrypted key saved for: {', '.join(saved)}")
        self.status.showMessage("API key saved to encrypted backend store.")

    def handle_api_approval_changed(self, allowed: bool) -> None:
        if self.api_manager is None:
            self.pane_api.update_status("Runtime not ready; approval was not changed")
            self.status.showMessage("API runtime not ready.")
            return

        self.api_manager.set_user_approved(allowed)
        self.pane_api.update_status(
            "API fallback approved for this session" if allowed else "API fallback disabled"
        )
        self.status.showMessage(
            "API fallback approved for this session." if allowed else "API fallback disabled."
        )

    def handle_provider_config_save(self, config: dict) -> None:
        try:
            if self.api_manager is not None:
                self.api_manager.save_provider_config(config)
            else:
                provider_config.save(config)
            self.pane_api.update_status("Runtime provider configuration saved")
            self.status.showMessage("Runtime provider configuration saved.")
        except Exception as exc:
            self.pane_api.update_status(f"Provider config save failed: {exc}")
            self.status.showMessage("Provider config save failed.")

    def handle_permission_blocks_reset(self) -> None:
        self.gateway_bridge.reset_denials()
        permission_gate.reset()
        if self.orchestrator and hasattr(self.orchestrator, "engine"):
            gateway = getattr(self.orchestrator.engine, "gateway", None)
            reset = getattr(gateway, "reset_denials", None)
            if callable(reset):
                reset()
        self.pane_api.update_status("Permission blocks reset; future actions will ask again")
        self.status.showMessage("Permission blocks reset.")

    def update_model_status(self, text: str) -> None:
        self.status.showMessage(text)
