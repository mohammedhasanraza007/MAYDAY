"""
M.A.Y.D.A.Y UI Panels — v5.0 Integrated Components
====================================================
Functional panels for Chat, Model Management, and System Logs.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QLineEdit, QPushButton, QLabel, QScrollArea,
                             QProgressBar, QFrame, QGridLayout, QFileDialog,
                             QCheckBox, QTreeView)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QFileSystemModel
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


class AgentStreamPanel(QWidget):
    """Live scrolling view of agent action/observation events."""

    event_received = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        header = QLabel("Agent Event Stream")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {THEME.ACCENT_GREEN};")
        layout.addWidget(header)

        self.stream_view = QTextEdit()
        self.stream_view.setReadOnly(True)
        self.stream_view.setStyleSheet(
            f"background-color: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; "
            f"border-radius: 6px; padding: 10px; font-family: Consolas; font-size: 12px;"
        )
        layout.addWidget(self.stream_view)

        clear_btn = QPushButton("Clear Stream")
        clear_btn.setStyleSheet(BUTTON_STYLE)
        clear_btn.clicked.connect(self.stream_view.clear)
        layout.addWidget(clear_btn)

        self.event_received.connect(self.append_event)
        try:
            from core.event_stream import agent_event_stream

            agent_event_stream.subscribe(self._on_event)
        except Exception:
            pass

    def _on_event(self, event) -> None:
        self.event_received.emit(event)

    def append_event(self, event) -> None:
        try:
            from core.event_stream import AgentAction, AgentObservation
            import time

            ts = time.strftime("%H:%M:%S", time.localtime(getattr(event, "timestamp", 0)))
            if isinstance(event, AgentAction):
                colour = THEME.ACTION_BLUE
                label = f"[{ts}] ACTION: {event.tool or event.type}"
                params_text = str(event.parameters)
                params = params_text[:120] + ("..." if len(params_text) > 120 else "")
                self.stream_view.append(
                    f"<span style='color:{colour}'><b>{html.escape(label)}</b></span>"
                    f"<br><span style='color:{THEME.DIM}; font-size:11px;'>{html.escape(params)}</span><br>"
                )
            elif isinstance(event, AgentObservation):
                ok = event.status == "success"
                colour = THEME.OBS_GREEN if ok else THEME.OBS_RED
                label = f"[{ts}] {'OK' if ok else 'ERR'} RESULT: {event.status.upper()}"
                result_preview = str(event.result)[:100]
                self.stream_view.append(
                    f"<span style='color:{colour}'><b>{html.escape(label)}</b></span>"
                    f"<br><span style='color:{THEME.DIM}; font-size:11px;'>{html.escape(result_preview)}</span><br>"
                )
            self.stream_view.verticalScrollBar().setValue(
                self.stream_view.verticalScrollBar().maximum()
            )
        except Exception:
            pass


class TerminalPanel(QWidget):
    """Embedded terminal-style output panel."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        header = QLabel("Terminal Output")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {THEME.ACCENT_GREEN};")
        layout.addWidget(header)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet(
            f"background-color: {THEME.CODE_BG}; color: {THEME.ACCENT_GREEN}; "
            f"border: 1px solid {THEME.BORDER}; border-radius: 6px; padding: 10px; "
            f"font-family: Consolas; font-size: 12px;"
        )
        layout.addWidget(self.terminal)

        input_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Enter shell command (goes through permission gate)...")
        self.cmd_input.setStyleSheet(INPUT_STYLE)
        self.cmd_input.returnPressed.connect(self._run_command)

        run_btn = QPushButton("Run")
        run_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        run_btn.clicked.connect(self._run_command)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(BUTTON_STYLE)
        clear_btn.clicked.connect(self.terminal.clear)

        input_row.addWidget(self.cmd_input)
        input_row.addWidget(run_btn)
        input_row.addWidget(clear_btn)
        layout.addLayout(input_row)

    def _run_command(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        self.append_output(f"$ {cmd}")
        self.cmd_input.clear()
        self.append_output("[Routed to orchestrator via permission gate]\n")

    def append_output(self, text: str, colour: str = "") -> None:
        output_colour = colour or THEME.ACCENT_GREEN
        self.terminal.append(
            f"<span style='color:{output_colour}; font-family:Consolas;'>{html.escape(text)}</span>"
        )
        self.terminal.verticalScrollBar().setValue(
            self.terminal.verticalScrollBar().maximum()
        )


class FileExplorerPanel(QWidget):
    """Workspace file browser rooted at the MAYDAY project."""

    def __init__(self, root_path: str = "."):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        header = QLabel("Workspace Files")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {THEME.ACCENT_GREEN};")
        layout.addWidget(header)

        self.model = QFileSystemModel(self)
        self.model.setRootPath(root_path)
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(root_path))
        self.tree.setSortingEnabled(True)
        self.tree.setAlternatingRowColors(False)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.setStyleSheet(
            f"QTreeView {{ background-color: {THEME.CODE_BG}; color: {THEME.TEXT}; "
            f"border: 1px solid {THEME.BORDER}; border-radius: 6px; padding: 6px; }}"
            f"QTreeView::item:selected {{ background-color: {THEME.SELECTION}; }}"
        )
        layout.addWidget(self.tree)


class SkillManagerPanel(QWidget):
    """Shows loaded skills and trigger keywords."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        header = QLabel("Skill Manager (OpenHands Microagents)")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {THEME.ACCENT_GREEN};")
        layout.addWidget(header)

        self.skills_view = QTextEdit()
        self.skills_view.setReadOnly(True)
        self.skills_view.setStyleSheet(
            f"background-color: {THEME.CODE_BG}; border: 1px solid {THEME.BORDER}; "
            f"border-radius: 6px; padding: 10px; font-size: 12px;"
        )
        layout.addWidget(self.skills_view)

        reload_btn = QPushButton("Reload Skills from Disk")
        reload_btn.setStyleSheet(BUTTON_STYLE)
        reload_btn.clicked.connect(self._reload)
        layout.addWidget(reload_btn)

        self._reload()

    def _reload(self):
        try:
            from core.skill_loader import skill_loader

            count = skill_loader.load()
            lines = [f"<b style='color:{THEME.ACCENT_GREEN}'>{count} skills loaded</b><br><br>"]
            for skill in skill_loader._skills:
                triggers = ", ".join(skill.triggers[:6])
                lines.append(
                    f"<b style='color:{THEME.ACCENT_BLUE}'>{skill.name}</b> "
                    f"<span style='color:{THEME.DIM}'>- triggers: {html.escape(triggers)}</span><br>"
                )
            self.skills_view.setHtml("".join(lines))
        except Exception as exc:
            self.skills_view.setText(f"Error loading skills: {exc}")
