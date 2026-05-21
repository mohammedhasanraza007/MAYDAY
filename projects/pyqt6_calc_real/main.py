"""MAYDAY Phase 6B — PyQt6 Dark-Themed Calculator"""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


DARK_STYLE = """
QMainWindow { background-color: #1e1e2e; }
QLineEdit {
    background-color: #181825; color: #cdd6f4; border: none;
    font-size: 32px; padding: 16px; border-radius: 8px;
}
QPushButton {
    background-color: #313244; color: #cdd6f4; border: none;
    font-size: 20px; padding: 18px; border-radius: 8px;
    min-width: 64px; min-height: 48px;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QPushButton[cssClass="operator"] { background-color: #f38ba8; color: #1e1e2e; }
QPushButton[cssClass="operator"]:hover { background-color: #f5a8be; }
QPushButton[cssClass="clear"] { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton[cssClass="clear"]:hover { background-color: #b8ebb4; }
QPushButton[cssClass="equals"] { background-color: #89b4fa; color: #1e1e2e; }
QPushButton[cssClass="equals"]:hover { background-color: #a0c4fb; }
"""


class Calculator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAYDAY PyQt6 Calculator")
        self.setMinimumSize(340, 480)
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        self.display = QLineEdit("0")
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setReadOnly(True)
        self.display.setFont(QFont("Segoe UI", 28))
        layout.addWidget(self.display)

        grid = QGridLayout()
        grid.setSpacing(6)
        layout.addLayout(grid)

        buttons = [
            ("C", 0, 0, "clear"), ("±", 0, 1, ""), ("%", 0, 2, ""), ("/", 0, 3, "operator"),
            ("7", 1, 0, ""), ("8", 1, 1, ""), ("9", 1, 2, ""), ("*", 1, 3, "operator"),
            ("4", 2, 0, ""), ("5", 2, 1, ""), ("6", 2, 2, ""), ("-", 2, 3, "operator"),
            ("1", 3, 0, ""), ("2", 3, 1, ""), ("3", 3, 2, ""), ("+", 3, 3, "operator"),
            ("0", 4, 0, ""), (".", 4, 2, ""), ("=", 4, 3, "equals"),
        ]

        for label, row, col, css_class in buttons:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if css_class:
                btn.setProperty("cssClass", css_class)
            btn.clicked.connect(lambda checked, v=label: self.on_press(v))
            colspan = 2 if label == "0" else 1
            grid.addWidget(btn, row, col, 1, colspan)

        self._expression = ""
        self._new_input = True

    def on_press(self, value):
        if value == "C":
            self._expression = ""
            self.display.setText("0")
            self._new_input = True
            return
        if value == "=":
            try:
                safe = set("0123456789.+-*/() %")
                if not set(self._expression) <= safe:
                    raise ValueError("bad input")
                result = eval(self._expression, {"__builtins__": {}}, {})
                result_str = str(result)
                if "." in result_str:
                    result_str = result_str.rstrip("0").rstrip(".")
                self.display.setText(result_str)
                self._expression = result_str
                self._new_input = True
            except Exception:
                self.display.setText("Error")
                self._expression = ""
                self._new_input = True
            return
        if value == "±":
            if self._expression.startswith("-"):
                self._expression = self._expression[1:]
            elif self._expression:
                self._expression = "-" + self._expression
            self.display.setText(self._expression or "0")
            return
        if value == "%":
            try:
                self._expression = str(float(self._expression) / 100)
                self.display.setText(self._expression)
            except Exception:
                pass
            return

        if self._new_input and value not in "+-*/":
            self._expression = ""
            self._new_input = False

        self._expression += value
        self.display.setText(self._expression)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Calculator()
    window.show()
    sys.exit(app.exec())
