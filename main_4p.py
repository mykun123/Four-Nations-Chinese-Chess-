# main_4p.py - 四国象棋入口（模式选择+游戏）
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QDialog, QButtonGroup,
    QRadioButton, QGroupBox, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QFontDatabase

from game_4p import (
    RED, BLACK, GREEN, BLUE, TURN_ORDER, NEXT_PLAYER, PREV_PLAYER,
    OPPOSITE, COLOR_SHORT, COLOR_NAMES, COLOR_RGB,
)
from board_4p_ui import Board4PWidget


class StartDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("四国象棋 - 开局设置")
        self.setFixedSize(420, 480)
        self.mode = "ffa"
        self.color = RED
        self.teammate = GREEN  # 相邻队友

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("四国象棋")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ---- 模式选择 ----
        mode_box = QGroupBox("游戏模式")
        mode_layout = QVBoxLayout(mode_box)
        self.mode_ffa = QRadioButton("自由对战 — 各自为战，最后一人获胜")
        self.mode_team = QRadioButton("组队对战 — 2v2，相邻两国为队友")
        self.mode_pvp = QRadioButton("人人对战 — 全部人类，轮流操作")
        self.mode_ffa.setChecked(True)
        self.mode_ffa.toggled.connect(self._on_mode_changed)
        self.mode_team.toggled.connect(self._on_mode_changed)
        self.mode_pvp.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_ffa)
        mode_layout.addWidget(self.mode_team)
        mode_layout.addWidget(self.mode_pvp)
        layout.addWidget(mode_box)

        # ---- 颜色选择（PvP不需要） ----
        self.color_box = QGroupBox("选择你的颜色（其他为电脑）")
        color_layout = QVBoxLayout(self.color_box)
        self.color_group = QButtonGroup(self)
        self.color_btns = {}
        for c in TURN_ORDER:
            btn = QRadioButton(f"  {COLOR_NAMES[c]}")
            btn.setStyleSheet(f"color: {COLOR_RGB[c]}; font-weight: bold; font-size: 13px;")
            self.color_group.addButton(btn, c)
            color_layout.addWidget(btn)
            self.color_btns[c] = btn
        self.color_btns[RED].setChecked(True)
        self.color_group.buttonClicked[int].connect(self._on_color_changed)
        layout.addWidget(self.color_box)

        # ---- 队友选择（仅组队对战） ----
        self.team_box = QGroupBox("选择你的队友（相邻两国）")
        team_layout = QVBoxLayout(self.team_box)
        self.team_combo = QComboBox()
        self.team_combo.setFont(QFont("Microsoft YaHei", 11))
        team_layout.addWidget(self.team_combo)
        layout.addWidget(self.team_box)
        self._update_team_options()

        # ---- 开始按钮 ----
        btn_start = QPushButton("开始游戏")
        btn_start.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        btn_start.setFixedHeight(40)
        btn_start.clicked.connect(self._on_start)
        layout.addWidget(btn_start)
        layout.addStretch()

        self._on_mode_changed()

    def _on_mode_changed(self):
        is_ffa = self.mode_ffa.isChecked()
        is_team = self.mode_team.isChecked()
        is_pvp = self.mode_pvp.isChecked()

        self.color_box.setVisible(not is_pvp)
        self.team_box.setVisible(is_team)

    def _on_color_changed(self, color_id):
        self._update_team_options()

    def _update_team_options(self):
        self.team_combo.clear()
        color = self.color_group.checkedId()
        adj = [NEXT_PLAYER[color], PREV_PLAYER[color]]
        for c in adj:
            self.team_combo.addItem(f"  {COLOR_NAMES[c]}", c)
        self.team_combo.setCurrentIndex(0)

    def _get_teams(self):
        """返回 {color: team_id}"""
        my_color = self.color_group.checkedId()
        mate_color = self.team_combo.currentData()
        team_id_1 = f"team_{min(my_color, mate_color)}"
        # my_color 和 mate_color 一队，剩下两人另一队
        other = [c for c in TURN_ORDER if c not in (my_color, mate_color)]
        teams = {}
        teams[my_color] = team_id_1
        teams[mate_color] = team_id_1
        teams[other[0]] = "team_other"
        teams[other[1]] = "team_other"
        return teams

    def _on_start(self):
        if self.mode_ffa.isChecked():
            self.mode = "ffa"
        elif self.mode_team.isChecked():
            self.mode = "team"
        else:
            self.mode = "pvp"

        if self.mode != "pvp":
            self.color = self.color_group.checkedId()
            if self.mode == "team":
                mate = self.team_combo.currentData()
                other = [c for c in TURN_ORDER if c not in (self.color, mate)]
                msg = (f"你: {COLOR_NAMES[self.color]}  "
                       f"队友: {COLOR_NAMES[mate]}\n"
                       f"对手: {COLOR_NAMES[other[0]]} & {COLOR_NAMES[other[1]]}")
                QMessageBox.information(self, "组队信息", msg)
        else:
            self.color = RED  # PvP模式，默认红方先走

        self.accept()


class MainWindow4P(QMainWindow):
    def __init__(self, mode, human_color, teams=None):
        super().__init__()
        self.setWindowTitle("四国象棋")
        self.mode = mode
        self.human_color = human_color
        self.teams = teams

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 标题栏
        top = QHBoxLayout()
        title = QLabel("四国象棋")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        top.addWidget(title)
        top.addStretch()

        mode_names = {"ffa": "自由对战", "team": "组队对战", "pvp": "人人对战"}
        info_parts = [mode_names[mode]]
        if mode != "pvp":
            info_parts.append(f"你: {COLOR_NAMES[human_color]}")
        mode_label = QLabel(" | ".join(info_parts))
        mode_label.setFont(QFont("Microsoft YaHei", 10))
        top.addWidget(mode_label)
        layout.addLayout(top)

        # 棋盘
        self.board = Board4PWidget(mode=mode, human_color=human_color)
        if teams:
            self.board.game.teams = teams
        layout.addWidget(self.board, alignment=Qt.AlignCenter)

        # 状态栏
        turn_name = COLOR_NAMES[self.board.game.turn]
        self.status_label = QLabel(f"游戏开始 — 轮到 {turn_name}")
        self.status_label.setFont(QFont("Microsoft YaHei", 12))
        self.status_label.setFixedHeight(28)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # 信号连接
        self.board.game_over_signal.connect(self._on_game_over)
        self.board.status_signal.connect(self._on_status)

        # AI先手或PvP自动走子
        QTimer.singleShot(200, self._check_ai_start)

    def _check_ai_start(self):
        if self.mode != "pvp" and self.board.game.turn != self.human_color:
            self.board._start_next_ai()

    def _on_status(self, msg):
        self.status_label.setText(msg)

    def _on_game_over(self, msg):
        self.status_label.setText(msg)
        QMessageBox.information(self, "游戏结束", msg)


def main():
    app = QApplication(sys.argv)
    try:
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    except Exception:
        pass

    dlg = StartDialog()
    if dlg.exec_() != QDialog.Accepted:
        return

    teams = dlg._get_teams() if dlg.mode == "team" else None

    window = MainWindow4P(mode=dlg.mode, human_color=dlg.color, teams=teams)
    w = 48 * 2 + 18 * 38 + 60
    h = 48 * 2 + 18 * 38 + 120
    window.resize(int(w), int(h))
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
