# main.py - Chinese Chess (Xiangqi) game entry point
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QMessageBox, QFrame, QDialog)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QFontDatabase

from board_ui import BoardWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("中国象棋")
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # title bar with buttons
        top_row = QHBoxLayout()
        title_label = QLabel("中国象棋")
        title_font = QFont("Microsoft YaHei", 16, QFont.Bold)
        title_label.setFont(title_font)
        top_row.addWidget(title_label)
        top_row.addStretch(1)

        btn_pvp = QPushButton("人人对战")
        btn_pve = QPushButton("人机对战")
        btn_restart = QPushButton("重新开始")
        for btn in (btn_pvp, btn_pve, btn_restart):
            btn.setFixedSize(QSize(90, 32))
            btn.setFont(QFont("Microsoft YaHei", 10))

        top_row.addWidget(btn_pvp)
        top_row.addWidget(btn_pve)
        top_row.addWidget(btn_restart)
        layout.addLayout(top_row)

        # board widget
        self.board = BoardWidget()
        layout.addWidget(self.board, alignment=Qt.AlignCenter)

        # status bar label
        self.status_label = QLabel("请选择对战模式")
        self.status_label.setFont(QFont("Microsoft YaHei", 12))
        self.status_label.setFixedHeight(30)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # connect signals
        btn_pvp.clicked.connect(lambda: self._start_game("pvp"))
        btn_pve.clicked.connect(lambda: self._start_game("pve"))
        btn_restart.clicked.connect(self._restart)
        self.board.game_over_signal.connect(self._on_game_over)
        self.board.status_signal.connect(self._on_status)

    def _start_game(self, mode):
        self.board.set_mode(mode)
        if mode == "pvp":
            self.status_label.setText("人人对战 — 红方先行")
        else:
            self.status_label.setText("人机对战 — 你执红先行")

    def _restart(self):
        current = self.board.mode if hasattr(self.board, 'mode') else "pvp"
        self._start_game(current)

    def _on_status(self, msg):
        self.status_label.setText(msg)

    def _on_game_over(self, winner_text):
        msg = QMessageBox(self)
        msg.setWindowTitle("游戏结束")
        msg.setText(f"{winner_text}\n\n")
        btn_rematch = msg.addButton("再来一局", QMessageBox.AcceptRole)
        btn_quit = msg.addButton("退出", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_rematch)
        msg.exec_()
        if msg.clickedButton() == btn_rematch:
            self._restart()
        # else: just close the dialog


def main():
    app = QApplication(sys.argv)
    try:
        QFontDatabase.addApplicationFont("/C/Windows/Fonts/msyh.ttc")
    except Exception:
        pass  # system font is fine fallback
    window = MainWindow()
    window.resize(640, 720)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
