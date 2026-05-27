# board_ui.py - PyQt5 chess board widget with painting and interaction
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import Qt, QRect, QTimer, pyqtSignal, QThread, QObject
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

import sys
sys.path.insert(0, ".")
from game_logic import Game, RED, BLACK, PIECE_NAMES


CELL = 64
MARGIN_X = 52
MARGIN_Y = 52
BOARD_W = CELL * 8
BOARD_H = CELL * 9

PIECE_R = 28


class AIWorker(QThread):
    """Run AI search in a separate thread so UI stays responsive."""
    move_found = pyqtSignal(int, int, int, int)
    error = pyqtSignal(str)

    def __init__(self, game, depth=3):
        super().__init__()
        self.game = game
        self.depth = depth
        self._move = None

    def run(self):
        try:
            from ai import best_move as ai_best_move
            self._move = ai_best_move(self.game, depth=self.depth)
            if self._move:
                fr, fc, tr, tc = self._move
                self.move_found.emit(fr, fc, tr, tc)
            else:
                self.error.emit("AI 找不到合法走法")
        except Exception as e:
            self.error.emit(str(e))


class BoardWidget(QWidget):
    game_over_signal = pyqtSignal(str)   # winner text
    status_signal = pyqtSignal(str)      # status message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = Game()
        self.mode = "pvp"  # "pvp" or "pve"
        self.player_color = RED  # player is red in PvE (moves first)
        self._sel = None          # selected piece (row, col)
        self._legal_moves = []    # current legal move highlights
        self._thinking = False
        self._ai_worker = None
        self._last_move = None    # (fr, fc, tr, tc) for highlighting last move

        w = BOARD_W + MARGIN_X * 2
        h = BOARD_H + MARGIN_Y * 2
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)

    def set_mode(self, mode):
        if self._ai_worker and self._ai_worker.isRunning():
            self._ai_worker.wait(500)
        self.mode = mode
        self.game = Game()
        self._sel = None
        self._legal_moves = []
        self._thinking = False
        self._last_move = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            self._draw_board(painter)
            self._draw_pieces(painter)
            self._draw_highlights(painter)
        except Exception as e:
            print(f"Paint error: {e}")

    # ---- board drawing ----

    def _to_pixel(self, row, col):
        x = MARGIN_X + col * CELL
        y = MARGIN_Y + row * CELL
        return x, y

    def _draw_board(self, p):
        g = QColor("#C49A6C")
        pen_grid = QPen(g, 1.5)
        p.setPen(pen_grid)

        # vertical lines (top half and bottom half, gap at river)
        for i in range(9):
            x = MARGIN_X + i * CELL
            if i == 0 or i == 8:
                p.drawLine(x, MARGIN_Y, x, MARGIN_Y + BOARD_H)
            else:
                p.drawLine(x, MARGIN_Y, x, MARGIN_Y + CELL * 4)
                p.drawLine(x, MARGIN_Y + CELL * 5, x, MARGIN_Y + BOARD_H)

        # horizontal lines (small center gap at river rows 4 & 5 for text)
        cx = MARGIN_X + 4 * CELL  # board center x
        gap = 20
        for i in range(10):
            y = MARGIN_Y + i * CELL
            if i == 4 or i == 5:
                p.drawLine(MARGIN_X, y, cx - gap, y)
                p.drawLine(cx + gap, y, MARGIN_X + BOARD_W, y)
            else:
                p.drawLine(MARGIN_X, y, MARGIN_X + BOARD_W, y)

        # palace diagonals (top - black)
        p.drawLine(MARGIN_X + 3 * CELL, MARGIN_Y, MARGIN_X + 5 * CELL, MARGIN_Y + 2 * CELL)
        p.drawLine(MARGIN_X + 5 * CELL, MARGIN_Y, MARGIN_X + 3 * CELL, MARGIN_Y + 2 * CELL)
        # palace diagonals (bottom - red)
        p.drawLine(MARGIN_X + 3 * CELL, MARGIN_Y + 7 * CELL, MARGIN_X + 5 * CELL, MARGIN_Y + 9 * CELL)
        p.drawLine(MARGIN_X + 5 * CELL, MARGIN_Y + 7 * CELL, MARGIN_X + 3 * CELL, MARGIN_Y + 9 * CELL)

        # river text (vertically centered between rows 4 and 5)
        font = QFont("SimSun", 20, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor("#8B6914"))
        text_y = MARGIN_Y + 4 * CELL + (CELL - 20) // 2
        half_w = BOARD_W // 2
        p.drawText(QRect(MARGIN_X + 5, text_y, half_w - 10, CELL), Qt.AlignCenter, "楚  河")
        p.drawText(QRect(MARGIN_X + half_w + 5, text_y, half_w - 10, CELL), Qt.AlignCenter, "汉  界")

    def _draw_pieces(self, p):
        for r in range(10):
            for c in range(9):
                piece = self.game.board[r][c]
                if not piece:
                    continue
                x, y = self._to_pixel(r, c)
                color_name = "red" if piece["color"] == RED else "black"
                char = PIECE_NAMES[piece["type"]][color_name]

               # shadow
                p.setPen(QColor("#333333"))
                p.setBrush(QColor("#DDDDDD"))
                p.drawEllipse(x - PIECE_R + 2, y - PIECE_R + 2, PIECE_R * 2, PIECE_R * 2)

                # piece body
                pen_color = QColor("#CC3333") if color_name == "red" else QColor("#1A1A1A")
                p.setPen(pen_color)
                p.setBrush(QColor("#F5F5DC"))
                p.drawEllipse(x - PIECE_R, y - PIECE_R, PIECE_R * 2, PIECE_R * 2)

                # ring around piece
                p.setPen(QPen(pen_color, 1.5))
                p.drawEllipse(x - PIECE_R + 3, y - PIECE_R + 3, (PIECE_R - 3) * 2, (PIECE_R - 3) * 2)

                # character
                font = QFont("SimSun", 18, QFont.Bold)
                p.setFont(font)
                p.setPen(pen_color)
                rect = QRect(x - PIECE_R + 5, y - PIECE_R + 4, (PIECE_R - 5) * 2, (PIECE_R - 4) * 2)
                p.drawText(rect, Qt.AlignCenter, char)

    def _draw_highlights(self, p):
        # last move highlight
        if self._last_move:
            fr, fc, tr, tc = self._last_move
            for (r, c) in [(fr, fc), (tr, tc)]:
                x, y = self._to_pixel(r, c)
                hl = QColor("#FFD700")
                p.setPen(QPen(hl, 2.5))
                hl.setAlpha(80)
                p.setBrush(hl)
                p.drawEllipse(x - PIECE_R, y - PIECE_R, PIECE_R * 2, PIECE_R * 2)

        # selected piece highlight
        if self._sel:
            sr, sc = self._sel
            x, y = self._to_pixel(sr, sc)
            sel_pen = QColor("#4CAF50")
            sel_brush = QColor("#4CAF50")
            sel_brush.setAlpha(80)
            p.setPen(sel_pen)
            p.setBrush(sel_brush)
            p.drawEllipse(x - PIECE_R, y - PIECE_R, PIECE_R * 2, PIECE_R * 2)

        # legal move targets
        for tr, tc in self._legal_moves:
            x, y = self._to_pixel(tr, tc)
            target = self.game.board[tr][tc]
            if target:
                cap_pen = QColor("#FF5722")
                cap_brush = QColor("#FF5722")
                cap_brush.setAlpha(60)
                p.setPen(cap_pen)
                p.setBrush(cap_brush)
                p.drawEllipse(x - PIECE_R, y - PIECE_R, PIECE_R * 2, PIECE_R * 2)
            else:
                # small dot for empty target
                p.setPen(Qt.NoPen)
                dot = QColor("#4CAF50")
                dot.setAlpha(180)
                p.setBrush(dot)
                p.drawEllipse(x - 6, y - 6, 12, 12)

    def mousePressEvent(self, event):
        if self._thinking:
            return
        # in PvE mode, block input while AI is thinking
        if self.mode == "pve" and self.game.turn != self.player_color:
            return

        x = event.pos().x()
        y = event.pos().y()
        col = round((x - MARGIN_X) / CELL)
        row = round((y - MARGIN_Y) / CELL)

        if not (0 <= row < 10 and 0 <= col < 9):
            return

        # check distance to grid point
        px, py = self._to_pixel(row, col)
        dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        if dist > CELL * 0.6:
            return

        clicked_piece = self.game.board[row][col]

        # case 1: selecting own piece
        if clicked_piece and clicked_piece["color"] == self.game.turn:
            self._sel = (row, col)
            all_moves = self.game.get_legal_moves()
            self._legal_moves = [
                (m[2], m[3]) for m in all_moves
                if m[0] == row and m[1] == col
            ]
            self.update()
            return

        # case 2: moving to target
        if self._sel:
            fr, fc = self._sel
            all_moves = self.game.get_legal_moves(self.game.turn)
            move_ok = any(m[2] == row and m[3] == col for m in all_moves
                          if m[0] == fr and m[1] == fc)
            if move_ok:
                try:
                    self._execute_move(fr, fc, row, col)
                except Exception as e:
                    print(f"Move error: {e}")

    def _execute_move(self, fr, fc, tr, tc):
        # Save info BEFORE making the move (board state changes after make_move)
        captured = self.game.board[tr][tc] is not None
        piece_info = dict(self.game.board[fr][fc])  # copy before it moves
        color_name = "红方" if self.game.turn == RED else "黑方"
        ptype_display = PIECE_NAMES[piece_info["type"]]["red" if piece_info["color"] == RED else "black"]

        self.game.make_move(fr, fc, tr, tc)
        self._last_move = (fr, fc, tr, tc)
        self._sel = None
        self._legal_moves = []
        self.update()

        status_msg = f"{color_name} {ptype_display}" + (" 吃子" if captured else "")

        # check game over
        next_color = self.game.turn
        if not self.game.has_legal_moves(next_color):
            winner = "黑方胜！" if next_color == RED else "红方胜！"
            if self.game.in_check(next_color):
                status_msg += f" — 将杀！{winner}"
            else:
                status_msg += f" — 困毙！{winner}"
            self.status_signal.emit(status_msg)
            self.game_over_signal.emit(winner)
            return

        if self.game.in_check(next_color):
            nc_name = "红方" if next_color == RED else "黑方"
            status_msg += f" — {nc_name}被将军！"

        self.status_signal.emit(status_msg)

        # trigger AI move in PvE mode
        if (self.mode == "pve" and self.game.turn != self.player_color
                and not self._thinking):
            self._start_ai()

    def _start_ai(self):
        self._thinking = True
        self.status_signal.emit("AI 思考中...")
        # Use thread to keep UI responsive during AI computation
        self._ai_worker = AIWorker(self.game, depth=3)
        self._ai_worker.move_found.connect(self._on_ai_move)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_move(self, fr, fc, tr, tc):
        self._thinking = False
        try:
            self._execute_move(fr, fc, tr, tc)
        except Exception as e:
            print(f"AI move error: {e}")
            QMessageBox.critical(self, "错误", f"AI 移动出错: {e}")

    def _on_ai_error(self, msg):
        self._thinking = False
        print(f"AI error: {msg}")
        QMessageBox.critical(self, "AI 错误", f"{msg}")

