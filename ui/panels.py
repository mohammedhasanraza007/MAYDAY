"""
M.A.Y.D.A.Y UI Panels — v5.0 Integrated Components
====================================================
Functional panels for Chat, Model Management, LoRA (folder-based), and System Logs.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QLineEdit, QPushButton, QLabel, QScrollArea,
                             QProgressBar, QFrame, QGridLayout, QFileDialog,
                             QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from ui.theme import THEME, FONTS, INPUT_STYLE, BUTTON_STYLE, PRIMARY_BUTTON_STYLE
import re
import html

class MarkdownRenderer:
    @staticmethod
    def to_html(text: str) -> str:
        # Escape existing HTML to prevent injection
        text = html.escape(text)
        
        # Bold: **text** -> <b>text</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Code blocks: ```lang\ncode\n``` -> <div style='background: #1e1e1e; border: 1px solid #333; padding: 10px; margin: 10px 0;'><pre>code</pre></div>
        def replace_code(match):
            lang = match.group(1) or ""
            code = match.group(2).strip()
            return f"<div style='background: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; border-radius: 5px; padding: 10px; margin: 10px 0; font-family: {FONTS['mono']};'><pre style='margin:0;'>{code}</pre></div>"
        
        text = re.sub(r'```(\w*)\n?(.*?)\n?```', replace_code, text, flags=re.DOTALL)
        
        # Inline code: `text` -> <code style='background: #333; padding: 2px 4px; border-radius: 3px;'>text</code>
        text = re.sub(r'`(.*?)`', f"<code style='background: {THEME.BORDER}; padding: 2px 4px; border-radius: 3px;'>\\1</code>", text)
        
        # Line breaks
        text = text.replace('\n', '<br>')
        
        return text

class ChatPanel(QWidget):
    send_prompt = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 1. Chat History
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setStyleSheet(f"background-color: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 15px;")
        self.history.setFont(QFont(FONTS['primary']))
        layout.addWidget(self.history)

        # 2. Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your instruction here...")
        self.input_field.setStyleSheet(INPUT_STYLE)
        self.input_field.returnPressed.connect(self._handle_send)

        self.btn_send = QPushButton("Send")
        self.btn_send.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_send.clicked.connect(self._handle_send)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.btn_send)
        layout.addLayout(input_layout)

    def _handle_send(self):
        text = self.input_field.text().strip()
        if text:
            self.append_message("User", text)
            self.send_prompt.emit(text)
            self.input_field.clear()

    def append_message(self, sender, text):
        color = THEME.ACCENT_GREEN if sender == "Assistant" else THEME.ACCENT_BLUE
        
        if sender == "Assistant":
            rendered_text = MarkdownRenderer.to_html(text)
        else:
            rendered_text = html.escape(text).replace('\n', '<br>')
            
        self.history.append(f"<b style='color: {color}'>{sender}:</b> {rendered_text}<br>")
        # Auto-scroll
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

class ModelManagerPanel(QWidget):
    load_model = pyqtSignal(int)
    download_model = pyqtSignal(int)

    def __init__(self, tiers):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Model Asset Management")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {THEME.TEXT}; margin-bottom: 20px;")
        layout.addWidget(title)

        info = QLabel("CPU Quantized GGUF Models Only • Coding Specialist")
        info.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(info)

        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        layout.addLayout(self.grid)

        self.tier_widgets = {}
        for i, tier in enumerate(tiers):
            self._add_tier_card(tier, i)

        layout.addStretch()

    def _add_tier_card(self, tier, row):
        card = QFrame()
        card.setStyleSheet(f"background-color: {THEME.PANEL_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 15px;")
        card_layout = QVBoxLayout(card)

        name = QLabel(tier['name'])
        name.setStyleSheet("font-weight: bold; font-size: 16px;")

        size_gb = tier.get('size_bytes', 0) / 1e9
        quant = tier.get('quantization', 'Q4_K_M')
        info = QLabel(f"Tier {tier['tier']} | {quant} | ~{size_gb:.1f} GB")
        info.setStyleSheet(f"color: {THEME.DIM};")

        spec = QLabel(f"Specialization: {tier.get('specialization', 'coding')}")
        spec.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 11px;")

        status_label = QLabel("Status: Unknown")
        progress = QProgressBar()
        progress.hide()

        btn_layout = QHBoxLayout()
        btn_load = QPushButton("Load")
        btn_load.setStyleSheet(BUTTON_STYLE)
        btn_load.clicked.connect(lambda: self.load_model.emit(tier['tier']))

        btn_download = QPushButton("Download")
        btn_download.setStyleSheet(BUTTON_STYLE)
        btn_download.clicked.connect(lambda: self.download_model.emit(tier['tier']))

        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_download)

        card_layout.addWidget(name)
        card_layout.addWidget(info)
        card_layout.addWidget(spec)
        card_layout.addWidget(status_label)
        card_layout.addWidget(progress)
        card_layout.addLayout(btn_layout)

        self.grid.addWidget(card, row // 2, row % 2)
        self.tier_widgets[tier['tier']] = {
            'status': status_label,
            'progress': progress,
            'btn_load': btn_load,
            'btn_download': btn_download
        }

    def on_download_progress(self, tier: int, pct: int, msg: str) -> None:
        if tier not in self.tier_widgets:
            return
        w = self.tier_widgets[tier]
        w["status"].setText(f"Status: {msg}")
        w["progress"].show()
        w["progress"].setValue(max(0, min(100, int(pct))))

    def update_tier_status(self, tier, status, progress=None):
        if tier in self.tier_widgets:
            w = self.tier_widgets[tier]
            w['status'].setText(f"Status: {status}")
            if progress is not None:
                w['progress'].show()
                w['progress'].setValue(progress)
            else:
                w['progress'].hide()

class LogsPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Physical System Logs")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {THEME.TEXT}; margin-bottom: 20px;")
        layout.addWidget(title)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet(f"background-color: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 15px;")
        self.log_output.setFont(QFont(FONTS['mono']))
        layout.addWidget(self.log_output)

    def append_log(self, message):
        self.log_output.append(message)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())


class LoRAManagerPanel(QWidget):
    """
    v5.0 LoRA Manager — Folder-based dataset ingestion.
    NOT a text input. Accepts folders, parses code/docs, produces JSONL.
    """
    ingest_folder = pyqtSignal(str)      # folder path
    prepare_dataset = pyqtSignal(str)    # output path
    load_adapter = pyqtSignal(str)       # adapter .gguf path

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel("LoRA Adapter Manager")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {THEME.TEXT}; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel("Folder-based dataset ingestion • GGUF adapter loading")
        subtitle.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # ── Folder Ingest Section ─────────────────────────────────────────
        ingest_frame = QFrame()
        ingest_frame.setStyleSheet(f"background-color: {THEME.PANEL_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 15px;")
        ingest_layout = QVBoxLayout(ingest_frame)

        ingest_title = QLabel("Dataset Ingestion")
        ingest_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {THEME.TEXT};")
        ingest_layout.addWidget(ingest_title)

        ingest_desc = QLabel("Select a folder containing code, docs, or structured data.\nSupports: .py .js .ts .md .json .txt .yaml and 15+ more extensions.\nskill.md files are treated as dataset manifests.")
        ingest_desc.setStyleSheet(f"color: {THEME.DIM}; font-size: 11px;")
        ingest_desc.setWordWrap(True)
        ingest_layout.addWidget(ingest_desc)

        folder_row = QHBoxLayout()
        self.folder_path_label = QLabel("No folder selected")
        self.folder_path_label.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")
        self.btn_browse = QPushButton("Browse Folder")
        self.btn_browse.setStyleSheet(BUTTON_STYLE)
        self.btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_path_label, 1)
        folder_row.addWidget(self.btn_browse)
        ingest_layout.addLayout(folder_row)

        self.ingest_status = QLabel("")
        self.ingest_status.setStyleSheet(f"color: {THEME.ACCENT_YELLOW}; font-size: 11px;")
        self.ingest_status.setWordWrap(True)
        ingest_layout.addWidget(self.ingest_status)

        ingest_btn_row = QHBoxLayout()
        self.btn_ingest = QPushButton("Ingest & Parse")
        self.btn_ingest.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_ingest.setEnabled(False)
        self.btn_ingest.clicked.connect(self._start_ingest)

        self.btn_prepare = QPushButton("Prepare JSONL Dataset")
        self.btn_prepare.setStyleSheet(BUTTON_STYLE)
        self.btn_prepare.setEnabled(False)
        self.btn_prepare.clicked.connect(self._prepare_dataset)

        ingest_btn_row.addWidget(self.btn_ingest)
        ingest_btn_row.addWidget(self.btn_prepare)
        ingest_layout.addLayout(ingest_btn_row)

        layout.addWidget(ingest_frame)

        # ── Adapter Loading Section ───────────────────────────────────────
        adapter_frame = QFrame()
        adapter_frame.setStyleSheet(f"background-color: {THEME.PANEL_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 15px;")
        adapter_layout = QVBoxLayout(adapter_frame)

        adapter_title = QLabel("Load Pre-Built Adapter")
        adapter_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {THEME.TEXT};")
        adapter_layout.addWidget(adapter_title)

        adapter_desc = QLabel("Load a pre-trained .gguf LoRA adapter file.\nAdapter will be applied to the currently loaded base model.")
        adapter_desc.setStyleSheet(f"color: {THEME.DIM}; font-size: 11px;")
        adapter_desc.setWordWrap(True)
        adapter_layout.addWidget(adapter_desc)

        self.adapter_status = QLabel("No adapter loaded")
        self.adapter_status.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")
        adapter_layout.addWidget(self.adapter_status)

        adapter_btn_row = QHBoxLayout()
        self.btn_load_adapter = QPushButton("Load Adapter (.gguf)")
        self.btn_load_adapter.setStyleSheet(BUTTON_STYLE)
        self.btn_load_adapter.clicked.connect(self._browse_adapter)
        adapter_btn_row.addWidget(self.btn_load_adapter)
        adapter_layout.addLayout(adapter_btn_row)

        layout.addWidget(adapter_frame)

        # ── Activity Log ──────────────────────────────────────────────────
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumHeight(120)
        self.activity_log.setPlaceholderText("Activity log...")
        self.activity_log.setStyleSheet(f"background-color: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 10px; font-size: 11px;")
        layout.addWidget(self.activity_log)

        layout.addStretch()

        # Internal state
        self._selected_folder: str | None = None

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Training Data Folder", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self._selected_folder = folder
            self.folder_path_label.setText(folder)
            self.btn_ingest.setEnabled(True)
            self._log(f"Selected folder: {folder}")

    def _start_ingest(self):
        if self._selected_folder:
            self.ingest_status.setText("Ingesting...")
            self.ingest_folder.emit(self._selected_folder)

    def _prepare_dataset(self):
        output_path = QFileDialog.getSaveFileName(
            self, "Save JSONL Dataset", "lora_training_data/dataset.jsonl",
            "JSONL Files (*.jsonl)"
        )[0]
        if output_path:
            self.prepare_dataset.emit(output_path)

    def _browse_adapter(self):
        adapter_file = QFileDialog.getOpenFileName(
            self, "Select LoRA Adapter", "lora_adapters/",
            "GGUF Files (*.gguf)"
        )[0]
        if adapter_file:
            self.load_adapter.emit(adapter_file)

    def update_ingest_status(self, stats: dict):
        """Update UI after ingestion completes."""
        self.ingest_status.setText(
            f"Ingested: {stats.get('files_ingested', 0)} files | "
            f"Errors: {stats.get('errors', 0)} | "
            f"Total: {stats.get('total_chars', 0):,} chars | "
            f"Manifest: {'Yes' if stats.get('has_manifest') else 'No'}"
        )
        self.ingest_status.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 11px;")
        self.btn_prepare.setEnabled(stats.get('files_ingested', 0) > 0)
        self._log(f"Ingestion complete: {stats.get('files_ingested', 0)} files processed")

    def update_adapter_status(self, path: str | None):
        if path:
            self.adapter_status.setText(f"Active adapter: {path}")
            self.adapter_status.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 12px;")
        else:
            self.adapter_status.setText("No adapter loaded")
            self.adapter_status.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")

    def _log(self, msg: str):
        self.activity_log.append(msg)


class APIManagerPanel(QWidget):
    api_keys_saved = pyqtSignal(dict)
    api_approval_changed = pyqtSignal(bool)
    provider_config_saved = pyqtSignal(dict)
    permission_blocks_reset = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel("Cloud API Configuration")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {THEME.TEXT}; margin-bottom: 10px;")
        layout.addWidget(title)

        self.provider_inputs = {}
        self.config_inputs = {}

        # Provider Inputs
        self._add_api_row(layout, "openai_compatible", "OpenAI-Compatible / OpenRouter", "sk-or-...")
        self._add_api_row(layout, "openai", "OpenAI", "sk-...")
        self._add_api_row(layout, "claude", "Anthropic (Claude)", "sk-ant-...")
        self._add_api_row(layout, "gemini", "Google (Gemini)", "AIza...")

        config_title = QLabel("Runtime Provider Settings")
        config_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {THEME.TEXT}; margin-top: 14px;")
        layout.addWidget(config_title)

        self._add_config_row(layout, "openai_compatible_base_url", "OpenAI-Compatible Base URL", "https://openrouter.ai/api/v1")
        self._add_config_row(layout, "openai_compatible_model", "Model Name", "qwen/qwen3-coder:free")
        self._add_config_row(layout, "browser_executable_path", "Browser Executable Path", r"C:\Path\To\brave.exe")
        self._add_config_row(layout, "ocr_provider", "OCR Provider", "none")

        self.browser_headless_checkbox = QCheckBox("Run browser executor headless")
        self.browser_headless_checkbox.setStyleSheet(f"color: {THEME.TEXT}; font-size: 12px;")
        layout.addWidget(self.browser_headless_checkbox)

        self.btn_save_config = QPushButton("Save Runtime Provider Config")
        self.btn_save_config.setStyleSheet(BUTTON_STYLE)
        self.btn_save_config.clicked.connect(self._save_provider_config)
        layout.addWidget(self.btn_save_config)

        self.btn_save = QPushButton("Save Encrypted Keys")
        self.btn_save.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_save.clicked.connect(self._save_keys)
        layout.addWidget(self.btn_save)

        self.approval_checkbox = QCheckBox("Allow API fallback for this session")
        self.approval_checkbox.setStyleSheet(f"color: {THEME.TEXT}; font-size: 12px;")
        self.approval_checkbox.stateChanged.connect(self._approval_changed)
        layout.addWidget(self.approval_checkbox)

        self.api_status = QLabel("No encrypted keys saved in this session")
        self.api_status.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")
        layout.addWidget(self.api_status)

        self.btn_reset_permissions = QPushButton("Reset Permission Blocks")
        self.btn_reset_permissions.setStyleSheet(BUTTON_STYLE)
        self.btn_reset_permissions.clicked.connect(self.permission_blocks_reset.emit)
        layout.addWidget(self.btn_reset_permissions)

        layout.addStretch()

    def _add_api_row(self, layout, provider, label, placeholder):
        row = QVBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setStyleSheet(INPUT_STYLE)
        row.addWidget(lbl)
        row.addWidget(edit)
        layout.addLayout(row)
        self.provider_inputs[provider] = edit

    def _add_config_row(self, layout, key, label, placeholder):
        row = QVBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px;")
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(INPUT_STYLE)
        row.addWidget(lbl)
        row.addWidget(edit)
        layout.addLayout(row)
        self.config_inputs[key] = edit

    def _save_keys(self):
        keys = {}
        for provider, edit in self.provider_inputs.items():
            value = edit.text().strip()
            if value:
                keys[provider] = value
                edit.clear()

        if not keys:
            self.update_status("No keys entered")
            return

        self.api_keys_saved.emit(keys)

    def _approval_changed(self):
        self.api_approval_changed.emit(self.approval_checkbox.isChecked())

    def update_status(self, text):
        self.api_status.setText(text)

    def _save_provider_config(self):
        values = {key: edit.text().strip() for key, edit in self.config_inputs.items()}
        config = {
            "model_api": {},
            "browser": {"headless": self.browser_headless_checkbox.isChecked()},
            "desktop": {},
        }
        if values.get("openai_compatible_base_url"):
            config["model_api"]["openai_compatible_base_url"] = values["openai_compatible_base_url"]
        if values.get("openai_compatible_model"):
            config["model_api"]["openai_compatible_model"] = values["openai_compatible_model"]
        if values.get("browser_executable_path"):
            config["browser"]["executable_path"] = values["browser_executable_path"]
        if values.get("ocr_provider"):
            config["desktop"]["ocr_provider"] = values["ocr_provider"]

        self.provider_config_saved.emit(config)

class DashboardPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Factory Floor Dashboard")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {THEME.TEXT};")
        layout.addWidget(title)

        version_label = QLabel("v5.0 — CPU Quantized GGUF • Coding Specialist")
        version_label.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(version_label)

        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(15)
        layout.addLayout(self.stats_grid)

        self.ram_label = self._add_stat_card("Process RAM", "0.0 MB", 0, 0)
        self.model_label = self._add_stat_card("Active Model", "None", 0, 1)
        self.status_label = self._add_stat_card("Runtime Status", "INITIALIZING", 1, 0)
        self.routing_label = self._add_stat_card("Routing State", "IDLE", 1, 1)

        layout.addStretch()

    def _add_stat_card(self, title, value, row, col):
        card = QFrame()
        card.setStyleSheet(f"background-color: {THEME.PANEL_BG}; border: 1px solid {THEME.BORDER}; border-radius: 10px; padding: 20px;")
        c_layout = QVBoxLayout(card)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: {THEME.DIM}; font-size: 12px; font-weight: bold; text-transform: uppercase;")

        v_lbl = QLabel(value)
        v_lbl.setStyleSheet(f"color: {THEME.ACCENT_GREEN}; font-size: 22px; font-weight: bold;")

        c_layout.addWidget(t_lbl)
        c_layout.addWidget(v_lbl)
        self.stats_grid.addWidget(card, row, col)
        return v_lbl

    def update_stats(self, ram, model, status, routing):
        self.ram_label.setText(ram)
        self.model_label.setText(model)
        self.status_label.setText(status)
        self.routing_label.setText(routing)
