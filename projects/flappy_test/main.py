import sys, random
from PyQt6.QtCore import QTimer, Qt, QRectF
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QColor, QFont

class FlappyBird(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flappy Bird")
        self.setFixedSize(400, 600)
        self.bird_y = 300.0
        self.bird_vy = 0.0
        self.pipes = []
        self.score = 0
        self.game_over = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_game)
        self.timer.start(16)
        self.spawn_timer = 0

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            if self.game_over:
                self.__init__()
            else:
                self.bird_vy = -8.0

    def update_game(self):
        if self.game_over: return
        self.bird_vy += 0.4
        self.bird_y += self.bird_vy
        self.spawn_timer += 1
        if self.spawn_timer >= 100:
            h = random.randint(100, 400)
            self.pipes.append([400, h])
            self.spawn_timer = 0
        for p in self.pipes:
            p[0] -= 3
        if self.pipes and self.pipes[0][0] < -80:
            self.pipes.pop(0)
            self.score += 1
        if self.bird_y < 0 or self.bird_y > 580:
            self.game_over = True
        bird_rect = QRectF(50, self.bird_y, 30, 30)
        for p in self.pipes:
            top = QRectF(p[0], 0, 80, p[1])
            bot = QRectF(p[0], p[1] + 150, 80, 600 - p[1] - 150)
            if top.intersects(bird_rect) or bot.intersects(bird_rect):
                self.game_over = True
        self.update()

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.fillRect(self.rect(), QColor(135, 206, 235))
        qp.setBrush(QColor(255, 223, 0))
        qp.drawEllipse(50, int(self.bird_y), 30, 30)
        qp.setBrush(QColor(34, 139, 34))
        for p in self.pipes:
            qp.drawRect(p[0], 0, 80, p[1])
            qp.drawRect(p[0], p[1] + 150, 80, 600 - p[1] - 150)
        qp.setPen(Qt.GlobalColor.white)
        qp.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        if self.game_over:
            qp.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Game Over\nScore: " + str(self.score) + "\nPress Space to Restart")
        else:
            qp.drawText(20, 40, "Score: " + str(self.score))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    game = FlappyBird()
    game.show()
    sys.exit(app.exec())
