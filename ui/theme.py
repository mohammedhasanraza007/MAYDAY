"""
M.A.Y.D.A.Y UI Theme — Single Source of Truth for All Colours & Styles
======================================================================
ALL colour values are defined HERE and ONLY here.
No other file may hardcode hex colour values.
PyQt6 stylesheet fragments are pre-built for reuse.

v4.1 audit compliance: This is generation order file #2.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeConstants:
    """Immutable colour and style constants for the entire application."""

    # ── Core Colours ──────────────────────────────────────────────────────
    BG:            str = '#000000'   # Every window, panel, dialog background
    TEXT:          str = '#FFFFFF'   # All primary text
    PANEL_BG:      str = '#0A0A0A'   # Slightly lighter panels inside main window
    ACCENT_GREEN:  str = '#00FF9C'   # RUNNING, PASS, OK, live indicators
    ACCENT_RED:    str = '#FF4444'   # ERROR, FAIL, DENIED, permission alerts
    ACCENT_YELLOW: str = '#FFD700'   # WARNING, LOADING, PENDING states
    ACCENT_BLUE:   str = '#4A9EFF'   # Links, info highlights, API provider active
    DIM:           str = '#555555'   # Timestamps, metadata, secondary labels
    BORDER:        str = '#1E1E1E'   # Panel borders, separators
    CODE_BG:       str = '#050505'   # Terminal output, code blocks
    BUTTON_BG:     str = '#1A1A2E'   # Standard button background
    BUTTON_HOVER:  str = '#2A2A4E'   # Button hover state

    # ── Extended Palette ──────────────────────────────────────────────────
    ACCENT_ORANGE: str = '#FF8C00'   # Tier 3 model warning
    SURFACE:       str = '#111111'   # Elevated surface cards
    INPUT_BG:      str = '#0D0D0D'   # Text input fields
    SCROLLBAR:     str = '#2A2A2A'   # Scrollbar thumb
    SELECTION:     str = '#1A3A5C'   # Text selection highlight
    TAB_BG:         str = '#0D1117'   # Tab bar background
    TAB_ACTIVE:     str = '#161B22'   # Active tab background
    ACTION_BLUE:    str = '#58A6FF'   # Agent action events
    OBS_GREEN:      str = '#3FB950'   # Successful observations
    OBS_RED:        str = '#F85149'   # Failed observations


# ── Singleton instance ────────────────────────────────────────────────────
THEME = ThemeConstants()

FONTS = {
    'primary': 'Segoe UI',
    'mono': 'Consolas'
}


# ── Pre-Built Stylesheet Fragments ───────────────────────────────────────

GLOBAL_STYLESHEET = f"""
QMainWindow, QWidget, QDialog {{
    background-color: {THEME.BG};
    color: {THEME.TEXT};
    font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
    font-size: 13px;
}}
QLabel {{
    color: {THEME.TEXT};
    background: transparent;
}}
"""

SIDEBAR_BTN_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {THEME.TEXT};
    border: none;
    text-align: left;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 6px;
    margin: 2px 8px;
}}
QPushButton:hover {{
    background-color: {THEME.BUTTON_HOVER};
}}
QPushButton:checked, QPushButton[active="true"] {{
    background-color: {THEME.BUTTON_BG};
    color: {THEME.ACCENT_GREEN};
    border-left: 3px solid {THEME.ACCENT_GREEN};
}}
"""

SIDEBAR_STYLE = f"""
QWidget {{
    background-color: {THEME.PANEL_BG};
    border-right: 1px solid {THEME.BORDER};
}}
"""

INPUT_STYLE = f"""
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {THEME.INPUT_BG};
    color: {THEME.TEXT};
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-family: 'Consolas', 'Cascadia Code', monospace;
    font-size: 13px;
    selection-background-color: {THEME.SELECTION};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {THEME.ACCENT_BLUE};
}}
"""

BUTTON_STYLE = f"""
QPushButton {{
    background-color: {THEME.BUTTON_BG};
    color: {THEME.TEXT};
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: {THEME.BUTTON_HOVER};
    border: 1px solid {THEME.ACCENT_BLUE};
}}
QPushButton:pressed {{
    background-color: {THEME.BG};
}}
QPushButton:disabled {{
    color: {THEME.DIM};
    border-color: {THEME.BORDER};
}}
"""

PRIMARY_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {THEME.ACCENT_GREEN};
    color: {THEME.BG};
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: 700;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: #33FFB5;
}}
QPushButton:pressed {{
    background-color: #00CC7D;
}}
QPushButton:disabled {{
    background-color: {THEME.DIM};
    color: {THEME.BORDER};
}}
"""

DANGER_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {THEME.ACCENT_RED};
    color: {THEME.TEXT};
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: 700;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: #FF6666;
}}
"""

PROGRESS_STYLE = f"""
QProgressBar {{
    background-color: {THEME.PANEL_BG};
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    text-align: center;
    color: {THEME.TEXT};
    font-size: 11px;
    min-height: 22px;
}}
QProgressBar::chunk {{
    background-color: {THEME.ACCENT_GREEN};
    border-radius: 5px;
}}
"""

TABLE_STYLE = f"""
QTableWidget {{
    background-color: {THEME.BG};
    color: {THEME.TEXT};
    gridline-color: {THEME.BORDER};
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {THEME.BORDER};
}}
QTableWidget::item:selected {{
    background-color: {THEME.SELECTION};
}}
QHeaderView::section {{
    background-color: {THEME.PANEL_BG};
    color: {THEME.DIM};
    border: none;
    border-bottom: 1px solid {THEME.BORDER};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}}
"""

COMBOBOX_STYLE = f"""
QComboBox {{
    background-color: {THEME.INPUT_BG};
    color: {THEME.TEXT};
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 28px;
}}
QComboBox:hover {{
    border: 1px solid {THEME.ACCENT_BLUE};
}}
QComboBox QAbstractItemView {{
    background-color: {THEME.PANEL_BG};
    color: {THEME.TEXT};
    selection-background-color: {THEME.SELECTION};
    border: 1px solid {THEME.BORDER};
}}
"""

SCROLLBAR_STYLE = f"""
QScrollBar:vertical {{
    background: {THEME.BG};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {THEME.SCROLLBAR};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {THEME.DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {THEME.BG};
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {THEME.SCROLLBAR};
    border-radius: 4px;
    min-width: 30px;
}}
"""

TOOLTIP_STYLE = f"""
QToolTip {{
    background-color: {THEME.PANEL_BG};
    color: {THEME.TEXT};
    border: 1px solid {THEME.BORDER};
    padding: 6px 10px;
    font-size: 12px;
    border-radius: 4px;
}}
"""

CODE_BLOCK_STYLE = f"""
QTextEdit {{
    background-color: {THEME.CODE_BG};
    color: {THEME.ACCENT_GREEN};
    font-family: 'Consolas', 'Cascadia Code', 'Fira Code', monospace;
    font-size: 13px;
    border: 1px solid {THEME.BORDER};
    border-radius: 6px;
    padding: 8px;
}}
"""

# ── Status Indicator Colours ─────────────────────────────────────────────

STATUS_COLOURS = {
    'running':   THEME.ACCENT_GREEN,
    'pass':      THEME.ACCENT_GREEN,
    'ok':        THEME.ACCENT_GREEN,
    'active':    THEME.ACCENT_GREEN,
    'error':     THEME.ACCENT_RED,
    'fail':      THEME.ACCENT_RED,
    'denied':    THEME.ACCENT_RED,
    'crashed':   THEME.ACCENT_RED,
    'warning':   THEME.ACCENT_YELLOW,
    'loading':   THEME.ACCENT_YELLOW,
    'pending':   THEME.ACCENT_YELLOW,
    'info':      THEME.ACCENT_BLUE,
    'api':       THEME.ACCENT_BLUE,
    'inactive':  THEME.DIM,
    'disabled':  THEME.DIM,
}


def status_dot_style(status: str) -> str:
    """Return a QLabel stylesheet for a coloured status dot indicator."""
    colour = STATUS_COLOURS.get(status.lower(), THEME.DIM)
    return f"""
    QLabel {{
        background-color: {colour};
        border-radius: 5px;
        min-width: 10px;
        max-width: 10px;
        min-height: 10px;
        max-height: 10px;
    }}
    """


def panel_card_style() -> str:
    """Return a stylesheet for a raised card/panel within the main content area."""
    return f"""
    QWidget {{
        background-color: {THEME.SURFACE};
        border: 1px solid {THEME.BORDER};
        border-radius: 8px;
    }}
    """


__all__ = [
    'THEME',
    'ThemeConstants',
    'GLOBAL_STYLESHEET',
    'SIDEBAR_BTN_STYLE',
    'SIDEBAR_STYLE',
    'INPUT_STYLE',
    'BUTTON_STYLE',
    'PRIMARY_BUTTON_STYLE',
    'DANGER_BUTTON_STYLE',
    'PROGRESS_STYLE',
    'TABLE_STYLE',
    'COMBOBOX_STYLE',
    'SCROLLBAR_STYLE',
    'TOOLTIP_STYLE',
    'CODE_BLOCK_STYLE',
    'STATUS_COLOURS',
    'status_dot_style',
    'panel_card_style',
    'FONTS'
]
