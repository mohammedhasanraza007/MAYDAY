import sys
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QApplication, QWidget


class FootballGame(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAYDAY PyQt6 Football")
        self.setFixedSize(820, 520)
        self.player = QRectF(100, 230, 34, 34)
        self.ball = QRectF(390, 245, 24, 24)
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.score = 0
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def keyPressEvent(self, event):
        self.keys.add(event.key())
        if event.key() == Qt.Key.Key_Space:
            dx = self.ball.center().x() - self.player.center().x()
            dy = self.ball.center().y() - self.player.center().y()
            if abs(dx) < 52 and abs(dy) < 52:
                self.ball_vx = 7.5 if dx >= 0 else -7.5
                self.ball_vy = dy / 8

    def keyReleaseEvent(self, event):
        self.keys.discard(event.key())

    def tick(self):
        speed = 5
        if Qt.Key.Key_Left in self.keys or Qt.Key.Key_A in self.keys:
            self.player.translate(-speed, 0)
        if Qt.Key.Key_Right in self.keys or Qt.Key.Key_D in self.keys:
            self.player.translate(speed, 0)
        if Qt.Key.Key_Up in self.keys or Qt.Key.Key_W in self.keys:
            self.player.translate(0, -speed)
        if Qt.Key.Key_Down in self.keys or Qt.Key.Key_S in self.keys:
            self.player.translate(0, speed)
        self.player.moveTo(max(20, min(self.player.x(), 760)), max(65, min(self.player.y(), 420)))

        self.ball.translate(self.ball_vx, self.ball_vy)
        self.ball_vx *= 0.985
        self.ball_vy *= 0.985
        if self.ball.top() < 62 or self.ball.bottom() > 458:
            self.ball_vy *= -0.8
        if self.ball.left() < 22:
            self.ball_vx *= -0.8
        if self.ball.right() > 798 and 190 < self.ball.center().y() < 330:
            self.score += 1
            self.ball.moveTo(390, 245)
            self.ball_vx = self.ball_vy = 0
        elif self.ball.right() > 798:
            self.ball_vx *= -0.8
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2f8f46"))
        painter.setPen(QColor("white"))
        painter.drawRect(20, 60, 780, 400)
        painter.drawLine(410, 60, 410, 460)
        painter.drawEllipse(350, 200, 120, 120)
        painter.drawRect(760, 190, 40, 140)
        painter.setBrush(QColor("#f5f1e8"))
        painter.drawEllipse(self.ball)
        painter.setBrush(QColor("#1b4fd8"))
        painter.drawRoundedRect(self.player, 8, 8)
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.drawText(30, 36, f"Goals: {self.score}   Move: WASD/Arrows   Kick: Space")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FootballGame()
    window.show()
    sys.exit(app.exec())
