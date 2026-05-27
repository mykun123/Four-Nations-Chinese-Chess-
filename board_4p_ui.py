# board_4p_ui.py - 四国象棋棋盘（含棋子绘制和交互）
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QThread
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

from game_4p import (
    Game4P, RED, BLACK, GREEN, BLUE,
    TURN_ORDER, OPPOSITE, COLOR_NAMES, COLOR_SHORT,
    COLOR_RGB, PIECE_CHARS, PLAYER_PROPS, in_blank,
)

CELL = 38
MX = 48
MY = 48


class AIWorker4P(QThread):
    move_found = pyqtSignal(int, int, int, int)
    error = pyqtSignal(str)

    def __init__(self, game, color, depth=2):
        super().__init__()
        self.game = game
        self.color = color
        self.depth = depth

    def run(self):
        try:
            from ai_4p import best_move
            result = best_move(self.game, self.color, depth=self.depth)
            if result:
                fr, fc, tr, tc = result
                self.move_found.emit(fr, fc, tr, tc)
            else:
                self.error.emit(f"AI({COLOR_SHORT[self.color]}) 找不到走法")
        except Exception as e:
            self.error.emit(str(e))


class Board4PWidget(QWidget):
    game_over_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, mode="ffa", human_color=RED, parent=None):
        super().__init__(parent)
        self.game = Game4P(mode=mode)
        self.mode = mode
        self.human_color = human_color
        self._sel = None
        self._legal_moves = []
        self._thinking = False
        self._ai_workers = []
        self._last_move = None

        w = MX * 2 + 18 * CELL
        h = MY * 2 + 18 * CELL
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)

    def _px(self, r, c):
        return MX + c * CELL, MY + r * CELL

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            self._draw_board(painter)
            self._draw_pieces(painter)
            self._draw_highlights(painter)
        except Exception as e:
            print(f"Paint error: {e}")

    # ======== 棋盘绘制 ========
    def _draw_board(self, p):
        pen = QPen(QColor("#C49A6C"), 1.5)
        p.setPen(pen)

        # 水平线段（四角空白跳过，河界缺口跳过）
        for r in range(19):
            for c in range(18):
                if in_blank(r, c) or in_blank(r, c + 1):
                    continue
                if 6 <= r <= 12 and c == 4:
                    continue
                if 6 <= r <= 12 and c == 13:
                    continue
                x1, y = self._px(r, c)
                x2, _ = self._px(r, c + 1)
                p.drawLine(x1, y, x2, y)

        # 垂直线段
        for r in range(18):
            for c in range(19):
                if in_blank(r, c) or in_blank(r + 1, c):
                    continue
                if 6 <= c <= 12 and r == 4:
                    continue
                if 6 <= c <= 12 and r == 13:
                    continue
                x, y1 = self._px(r, c)
                _, y2 = self._px(r + 1, c)
                p.drawLine(x, y1, x, y2)

        # 九宫斜线
        p.setPen(QPen(QColor("#C49A6C"), 1.5))
        palaces = {
            "black": (0, 2, 8, 10), "red": (16, 18, 8, 10),
            "green": (8, 10, 0, 2), "blue": (8, 10, 16, 18),
        }
        for (r1, r2, c1, c2) in palaces.values():
            x1, y1 = self._px(r1, c1); x2, y2 = self._px(r2, c2)
            p.drawLine(x1, y1, x2, y2)
            x3, y3 = self._px(r1, c2); x4, y4 = self._px(r2, c1)
            p.drawLine(x3, y3, x4, y4)

        # 楚河汉界
        p.setPen(QColor("#8B6914"))
        f = QFont("SimSun", 13, QFont.Bold)
        p.setFont(f)
        p.drawText(QRect(MX + 5 * CELL, MY + 4 * CELL + 4, 8 * CELL, CELL - 8),
                   Qt.AlignCenter, "楚  河")
        p.drawText(QRect(MX + 5 * CELL, MY + 13 * CELL + 4, 8 * CELL, CELL - 8),
                   Qt.AlignCenter, "汉  界")

        fv = QFont("SimSun", 11, QFont.Bold)
        p.setFont(fv)
        p.drawText(QRect(MX + 4 * CELL + 3, MY + 5 * CELL + 2, CELL - 6, 8 * CELL - 4),
                   Qt.AlignCenter, "楚\n河")
        p.drawText(QRect(MX + 13 * CELL + 3, MY + 5 * CELL + 2, CELL - 6, 8 * CELL - 4),
                   Qt.AlignCenter, "汉\n界")

        # 国家标记
        fl = QFont("SimSun", 15, QFont.Bold)
        p.setFont(fl)
        _, y0 = self._px(0, 9)
        p.setPen(QColor(COLOR_RGB[BLACK]))
        p.drawText(QRect(MX + 8 * CELL, y0 - 40, CELL, 30), Qt.AlignCenter, "黑")

        _, y18 = self._px(18, 9)
        p.setPen(QColor(COLOR_RGB[RED]))
        p.drawText(QRect(MX + 8 * CELL, y18 + 14, CELL, 30), Qt.AlignCenter, "红")

        x0, _ = self._px(9, 0)
        p.setPen(QColor(COLOR_RGB[GREEN]))
        p.drawText(QRect(x0 - 42, MY + 8 * CELL, 30, CELL), Qt.AlignCenter, "绿")

        x18, _ = self._px(9, 18)
        p.setPen(QColor(COLOR_RGB[BLUE]))
        p.drawText(QRect(x18 + 14, MY + 8 * CELL, 30, CELL), Qt.AlignCenter, "蓝")

        # 当前轮到谁（小三角标记）
        turn_player = self.game.turn
        tcolors = {RED: (MX + 8 * CELL, MY + 18 * CELL + 4),
                   BLACK: (MX + 8 * CELL, MY - 20),
                   GREEN: (MX - 20, MY + 8 * CELL),
                   BLUE: (MX + 19 * CELL + 4, MY + 8 * CELL)}
        if turn_player in tcolors:
            tx, ty = tcolors[turn_player]
            p.setPen(QPen(QColor(COLOR_RGB[turn_player]), 2))
            p.setBrush(QColor(COLOR_RGB[turn_player]))
            pts = [(tx, ty - 6), (tx - 5, ty + 4), (tx + 5, ty + 4)] if turn_player in (RED, BLACK) else \
                  [(tx, ty - 5), (tx + 4, ty + 5), (tx - 4, ty + 5)]
            # 用一个小圆点代替
            p.drawEllipse(tx - 4, ty - 4, 8, 8)

    # ======== 棋子绘制 ========
    def _draw_pieces(self, p):
        R = 15  # 棋子半径
        for r in range(19):
            for c in range(19):
                piece = self.game.board[r][c]
                if not piece:
                    continue
                x, y = self._px(r, c)
                col = piece["color"]
                ptype = piece["type"]
                char = PIECE_CHARS[col][ptype]
                rgb = COLOR_RGB[col]

                # 投影
                p.setPen(QColor("#333333"))
                p.setBrush(QColor("#DDDDDD"))
                p.drawEllipse(x - R + 1, y - R + 1, R * 2, R * 2)

                # 棋子本体
                p.setPen(QColor(rgb))
                p.setBrush(QColor("#F5F5DC"))
                p.drawEllipse(x - R, y - R, R * 2, R * 2)

                # 内圈
                p.setPen(QPen(QColor(rgb), 1.2))
                p.drawEllipse(x - R + 2, y - R + 2, (R - 2) * 2, (R - 2) * 2)

                # 文字
                pf = QFont("SimSun", 11, QFont.Bold)
                p.setFont(pf)
                p.setPen(QColor(rgb))
                rect = QRect(x - R + 2, y - R + 1, (R - 2) * 2, (R - 1) * 2)
                p.drawText(rect, Qt.AlignCenter, char)

    # ======== 高亮 ========
    def _draw_highlights(self, p):
        # 上一步走法
        if self._last_move:
            fr, fc, tr, tc = self._last_move
            for rr, cc in [(fr, fc), (tr, tc)]:
                x, y = self._px(rr, cc)
                hl = QColor("#FFD700")
                hl.setAlpha(80)
                p.setPen(QPen(hl, 2))
                p.setBrush(hl)
                p.drawEllipse(x - 15, y - 15, 30, 30)

        # 选中棋子
        if self._sel:
            sr, sc = self._sel
            x, y = self._px(sr, sc)
            sel = QColor("#4CAF50")
            sel.setAlpha(80)
            p.setPen(sel)
            p.setBrush(sel)
            p.drawEllipse(x - 15, y - 15, 30, 30)

        # 合法走法
        for tr, tc in self._legal_moves:
            x, y = self._px(tr, tc)
            target = self.game.board[tr][tc]
            if target:
                cap = QColor("#FF5722")
                cap.setAlpha(60)
                p.setPen(cap)
                p.setBrush(cap)
                p.drawEllipse(x - 15, y - 15, 30, 30)
            else:
                dot = QColor("#4CAF50")
                dot.setAlpha(160)
                p.setPen(Qt.NoPen)
                p.setBrush(dot)
                p.drawEllipse(x - 4, y - 4, 8, 8)

    # ======== 鼠标交互 ========
    def mousePressEvent(self, event):
        if self._thinking:
            return
        is_pvp = (self.game.mode == "pvp")
        if not is_pvp and self.game.turn != self.human_color:
            return  # AI回合不接受操作

        cur_color = self.game.turn

        x, y = event.pos().x(), event.pos().y()
        col = round((x - MX) / CELL)
        row = round((y - MY) / CELL)

        if not (0 <= row < 19 and 0 <= col < 19):
            return
        if in_blank(row, col):
            return

        px, py = self._px(row, col)
        dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        if dist > CELL * 0.6:
            return

        clicked = self.game.board[row][col]

        # 选当前回合方的棋子
        if clicked and clicked["color"] == cur_color:
            self._sel = (row, col)
            moves = self.game.get_legal_moves(cur_color)
            self._legal_moves = [(m[2], m[3]) for m in moves if m[0] == row and m[1] == col]
            self.update()
            return

        # 走子
        if self._sel:
            fr, fc = self._sel
            moves = self.game.get_legal_moves(cur_color)
            for m in moves:
                if m[0] == fr and m[1] == fc and m[2] == row and m[3] == col:
                    self._execute_move(fr, fc, row, col)
                    break

    def _execute_move(self, fr, fc, tr, tc):
        self.game.make_move(fr, fc, tr, tc)
        self._last_move = (fr, fc, tr, tc)
        self._sel = None
        self._legal_moves = []
        self.update()
        if self._check_game_over():
            return

        # PvP模式：不触发AI
        if self.game.mode == "pvp":
            self.status_signal.emit(f"轮到 {COLOR_NAMES[self.game.turn]}")
            return

        # 触发AI走子
        if not self._thinking and self.game.turn != self.human_color:
            self._start_next_ai()

    def _check_game_over(self):
        winners = self.game.check_winner()
        if winners:
            if self.mode == "ffa":
                msg = f"{COLOR_NAMES[winners[0]]} 获胜！"
            else:
                msg = " & ".join(COLOR_NAMES[c] for c in winners) + " 获胜！"
            self.status_signal.emit(msg)
            self.game_over_signal.emit(msg)
            return True
        # 轮到哪个玩家
        self.status_signal.emit(f"轮到 {COLOR_NAMES[self.game.turn]}")
        return False

    # ======== AI 走子 ========
    def _start_next_ai(self):
        if self._thinking:
            return
        color = self.game.turn
        if color == self.human_color:
            return
        if not self.game.alive[color]:
            self.game.next_turn()
            self._check_game_over()
            return

        self._thinking = True
        self.status_signal.emit(f"{COLOR_NAMES[color]} 思考中...")
        worker = AIWorker4P(self.game, color)
        worker.move_found.connect(self._on_ai_move)
        worker.error.connect(self._on_ai_error)
        worker.start()
        self._ai_workers.append(worker)

    def _on_ai_move(self, fr, fc, tr, tc):
        self._thinking = False
        self._execute_move(fr, fc, tr, tc)

    def _on_ai_error(self, msg):
        self._thinking = False
        print(f"AI error: {msg}")
        color = self.game.turn
        if self.game.alive[color]:
            # AI无法走子，认输
            self.game.alive[color] = False
            self.game.next_turn()
            self._check_game_over()
