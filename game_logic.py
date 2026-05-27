# game_logic.py - Chinese Chess (Xiangqi) core rules and state management

RED = 1
BLACK = -1
EMPTY = None

PIECE_NAMES = {
    "K": {"red": "帅", "black": "将"},
    "A": {"red": "仕", "black": "士"},
    "B": {"red": "相", "black": "象"},
    "N": {"red": "马", "black": "馬"},
    "R": {"red": "车", "black": "車"},
    "C": {"red": "炮", "black": "砲"},
    "P": {"red": "兵", "black": "卒"},
}


class Game:
    def __init__(self):
        self.board = [[None] * 9 for _ in range(10)]
        self.turn = RED  # red moves first
        self.history = []
        self._setup()

    def _setup(self):
        back_row = ["R", "N", "B", "A", "K", "A", "B", "N", "R"]
        for col, ptype in enumerate(back_row):
            self.board[0][col] = {"color": BLACK, "type": ptype}
            self.board[9][col] = {"color": RED, "type": ptype}
        cannon_row = [1, 7]
        for col in cannon_row:
            self.board[2][col] = {"color": BLACK, "type": "C"}
            self.board[7][col] = {"color": RED, "type": "C"}
        pawn_row = [0, 2, 4, 6, 8]
        for col in pawn_row:
            self.board[3][col] = {"color": BLACK, "type": "P"}
            self.board[6][col] = {"color": RED, "type": "P"}

    # ---- basic getters/setters ----

    def get(self, r, c):
        if 0 <= r < 10 and 0 <= c < 9:
            return self.board[r][c]
        return None

    def set(self, r, c, piece):
        self.board[r][c] = piece

    def in_bounds(self, r, c):
        return 0 <= r < 10 and 0 <= c < 9

    # ---- move application (for search) ----

    def apply_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        captured = self.board[tr][tc]
        self.board[fr][fc] = None
        self.board[tr][tc] = piece
        return {"piece": piece, "captured": captured}

    def unapply_move(self, fr, fc, tr, tc, info):
        self.board[tr][tc] = info["captured"]
        self.board[fr][fc] = info["piece"]

    # ---- path helpers (count pieces on line segment) ----

    def _pieces_between(self, r1, c1, r2, c2):
        count = 0
        if r1 == r2:
            step = 1 if c2 > c1 else -1
            for c in range(c1 + step, c2, step):
                if self.board[r1][c] is not None:
                    count += 1
        elif c1 == c2:
            step = 1 if r2 > r1 else -1
            for r in range(r1 + step, r2, step):
                if self.board[r][c1] is not None:
                    count += 1
        return count

    # ---- raw pseudo-legal moves per piece type (ignoring check) ----

    def _pseudo_moves(self, r, c):
        piece = self.board[r][c]
        if piece is None:
            return []
        color = piece["color"]
        ptype = piece["type"]
        moves = []

        if ptype == "K":
            moves = self._king_moves(r, c)
        elif ptype == "A":
            moves = self._advisor_moves(r, c, color)
        elif ptype == "B":
            moves = self._bishop_moves(r, c, color)
        elif ptype == "N":
            moves = self._knight_moves(r, c)
        elif ptype == "R":
            moves = self._rook_moves(r, c)
        elif ptype == "C":
            moves = self._cannon_moves(r, c)
        elif ptype == "P":
            moves = self._pawn_moves(r, c, color)

        return [m for m in moves if self.board[m[0]][m[1]] is None or self.board[m[0]][m[1]]["color"] != color]

    def _king_moves(self, r, c):
        moves = []
        color = self.board[r][c]["color"]
        if color == RED:
            rmin, rmax, cmin, cmax = 7, 9, 3, 5
        else:
            rmin, rmax, cmin, cmax = 0, 2, 3, 5
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if rmin <= nr <= rmax and cmin <= nc <= cmax:
                moves.append((nr, nc))
        return moves

    def _advisor_moves(self, r, c, color):
        moves = []
        if color == RED:
            rmin, rmax = 7, 9
        else:
            rmin, rmax = 0, 2
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = r + dr, c + dc
            if rmin <= nr <= rmax and 3 <= nc <= 5:
                moves.append((nr, nc))
        return moves

    def _bishop_moves(self, r, c, color):
        moves = []
        # elephant cannot cross river
        if color == RED:
            half = range(5, 10)
        else:
            half = range(0, 5)
        for dr, dc, br, bc in [(-2, -2, -1, -1), (-2, 2, -1, 1), (2, -2, 1, -1), (2, 2, 1, 1)]:
            nr, nc = r + dr, c + dc
            if nr in half and 0 <= nc < 9 and self.board[r + br][c + bc] is None:
                moves.append((nr, nc))
        return moves

    def _knight_moves(self, r, c):
        moves = []
        table = [
            (-2, -1, -1, 0), (-2, 1, -1, 0),
            (2, -1, 1, 0),   (2, 1, 1, 0),
            (-1, -2, 0, -1), (-1, 2, 0, 1),
            (1, -2, 0, -1),  (1, 2, 0, 1),
        ]
        for dr, dc, br, bc in table:
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc) and self.board[r + br][c + bc] is None:
                moves.append((nr, nc))
        return moves

    def _rook_moves(self, r, c):
        moves = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            while self.in_bounds(nr, nc):
                moves.append((nr, nc))
                if self.board[nr][nc] is not None:
                    break
                nr += dr
                nc += dc
        return moves

    def _cannon_moves(self, r, c):
        color = self.board[r][c]["color"]
        moves = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            screen_found = False
            while self.in_bounds(nr, nc):
                cell = self.board[nr][nc]
                if not screen_found:
                    # before finding a screen piece, can move to empty squares only
                    if cell is None:
                        moves.append((nr, nc))
                    else:
                        screen_found = True  # this is the screen, skip it
                else:
                    # after screen, scan for first non-empty (capture target)
                    if cell is not None:
                        if cell["color"] != color:
                            moves.append((nr, nc))  # capture enemy
                        break  # stop at first piece regardless of color
                nr += dr
                nc += dc
        return moves

    def _pawn_moves(self, r, c, color):
        moves = []
        if color == RED:
            forward = -1
            river_line = 4
        else:
            forward = 1
            river_line = 5
        # forward always allowed
        nr = r + forward
        if self.in_bounds(nr, c):
            moves.append((nr, c))
        # after crossing river, can move sideways
        if (color == RED and r <= river_line) or (color == BLACK and r >= river_line):
            for dc in [-1, 1]:
                nc = c + dc
                if self.in_bounds(r, nc):
                    moves.append((r, nc))
        return moves

    # ---- check / attack detection ----

    def find_king(self, color):
        king_type = "K"
        for r in range(10):
            for c in range(9):
                p = self.board[r][c]
                if p and p["color"] == color and p["type"] == king_type:
                    return r, c
        return None

    def is_attacked_by(self, r, c, by_color):
        # check all piece types of opponent
        for tr in range(10):
            for tc in range(9):
                p = self.board[tr][tc]
                if not p or p["color"] != by_color:
                    continue
                pt = p["type"]
                if pt == "R" and _rook_attacks(self, tr, tc, r, c):
                    return True
                if pt == "C" and _cannon_attacks(self, tr, tc, r, c):
                    return True
                if pt == "N" and _knight_attacks(self, tr, tc, r, c):
                    return True
                if pt == "P" and _pawn_attacks(self, tr, tc, r, c, by_color):
                    return True
                if pt == "K" and _king_attacks(self, tr, tc, r, c):
                    return True
        return False

    def in_check(self, color):
        pos = self.find_king(color)
        if not pos:
            return True  # king captured (shouldn't happen)
        kr, kc = pos
        opponent = -color
        return self.is_attacked_by(kr, kc, opponent)

    def has_legal_moves(self, color):
        for fr in range(10):
            for fc in range(9):
                p = self.board[fr][fc]
                if not p or p["color"] != color:
                    continue
                moves = self._pseudo_moves(fr, fc)
                for tr, tc in moves:
                    captured = self.board[tr][tc]
                    piece = self.board[fr][fc]
                    self.board[fr][fc] = None
                    self.board[tr][tc] = piece
                    if not self.in_check(color):
                        self.board[tr][tc] = captured
                        self.board[fr][fc] = piece
                        return True
                    self.board[tr][tc] = captured
                    self.board[fr][fc] = piece
        return False

    # ---- legal moves for current turn ----

    def get_legal_moves(self, color=None):
        if color is None:
            color = self.turn
        moves = []
        for fr in range(10):
            for fc in range(9):
                p = self.board[fr][fc]
                if not p or p["color"] != color:
                    continue
                for tr, tc in self._pseudo_moves(fr, fc):
                    captured = self.board[tr][tc]
                    piece = self.board[fr][fc]
                    self.board[fr][fc] = None
                    self.board[tr][tc] = piece
                    if not self.in_check(color):
                        moves.append((fr, fc, tr, tc))
                    self.board[tr][tc] = captured
                    self.board[fr][fc] = piece
        return moves

    # ---- make move (for real play) ----

    def make_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        captured = self.board[tr][tc]
        self.history.append({
            "from": (fr, fc),
            "to": (tr, tc),
            "piece": piece,
            "captured": captured,
        })
        self.board[fr][fc] = None
        self.board[tr][tc] = piece
        self.turn = -self.turn

    def undo_move(self):
        if not self.history:
            return False
        h = self.history.pop()
        fr, fc = h["from"]
        tr, tc = h["to"]
        self.board[fr][fc] = h["piece"]
        self.board[tr][tc] = h["captured"]
        self.turn = -self.turn
        return True

    def is_checkmate(self):
        color = self.turn
        if not self.has_legal_moves(color):
            return True
        return False


# ---- attack helpers (standalone for performance) ----

def _rook_attacks(game, fr, fc, tr, tc):
    if fr == tr:
        return game._pieces_between(fr, min(fc, tc), fr, max(fc, tc)) == 0
    if fc == tc:
        return game._pieces_between(min(fr, tr), fc, max(fr, tr), fc) == 0
    return False

def _cannon_attacks(game, fr, fc, tr, tc):
    if fr == tr:
        return game._pieces_between(fr, min(fc, tc), fr, max(fc, tc)) == 1
    if fc == tc:
        return game._pieces_between(min(fr, tr), fc, max(fr, tr), fc) == 1
    return False

def _knight_attacks(game, fr, fc, tr, tc):
    dr = abs(tr - fr)
    dc = abs(tc - fc)
    if (dr, dc) not in ((2, 1), (1, 2)):
        return False
    # check blocking leg/eye
    if dr == 2:
        br = fr + (tr - fr) // 2
        bc = fc
    else:
        br = fr
        bc = fc + (tc - fc) // 2
    return game.board[br][bc] is None

def _pawn_attacks(game, fr, fc, tr, tc, color):
    if color == RED:
        forward = -1
        river_line = 4
    else:
        forward = 1
        river_line = 5
    # pawn can only move forward or sideways (after river)
    if fr + forward == tr and fc == tc:
        return True
    crossed = (color == RED and fr <= river_line) or (color == BLACK and fr >= river_line)
    if crossed and fr == tr and abs(tc - fc) == 1:
        return True
    return False

def _king_attacks(game, fr, fc, tr, tc):
    # flying general: same file, no pieces between
    if fc != tc:
        return False
    count = game._pieces_between(min(fr, tr), fc, max(fr, tr), fc)
    return count == 0
