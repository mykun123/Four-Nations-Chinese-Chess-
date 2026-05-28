"""super_ai/evaluate.py — 局势评估（优化版，可被 pickle 序列化）"""

from game_4p import (
    RED, BLACK, GREEN, BLUE, NEUTRAL,
    TURN_ORDER, PIECE_VALUES, PLAYER_PROPS, in_blank,
)
from move_order import order_moves

# ====== 位置价值表（复用 ai_4p 相同逻辑） ======

def _canonical_pos(color, r, c):
    if color == RED:
        return r, c
    elif color == BLACK:
        return 18 - r, c
    elif color == GREEN:
        return 18 - c, r
    elif color == BLUE:
        return c, r
    return r, c


def _make_king_table():
    t = [[-1000] * 19 for _ in range(19)]
    for r in range(16, 19):
        for c in range(8, 11):
            if in_blank(r, c):
                continue
            t[r][c] = 0
    t[18][9] = 300
    t[18][8] = t[18][10] = 200
    t[17][9] = 200
    t[17][8] = t[17][10] = 100
    t[16][9] = 50
    t[16][8] = t[16][10] = 0
    return t


def _make_advisor_table():
    t = [[0] * 19 for _ in range(19)]
    t[17][8] = t[17][10] = 20
    t[18][9] = 15
    t[16][9] = 10
    t[17][9] = 5
    t[16][8] = t[16][10] = 5
    t[18][8] = t[18][10] = 0
    return t


def _make_bishop_table():
    t = [[-60] * 19 for _ in range(19)]
    for r in range(14, 19):
        for c in range(5, 14):
            if in_blank(r, c):
                continue
            if (r + c) % 2 == 0:
                continue
            t[r][c] = 0
    t[18][7] = t[18][11] = 50
    t[16][5] = t[16][13] = 30
    t[16][9] = 35
    t[14][7] = t[14][11] = 10
    return t


def _make_knight_table():
    t = [[-5] * 19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c):
                continue
            if c < 5 or c > 13:
                continue
            base = 5
            forward = max(0, 14 - r)
            central = max(0, 7 - abs(c - 9))
            penalty = -8 if r <= 2 or r >= 16 else 0
            t[r][c] = base + forward + central + penalty
    return t


def _make_rook_table():
    t = [[0] * 19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c):
                continue
            if c < 5 or c > 13:
                continue
            if r <= 4:
                t[r][c] = [16, 18, 20, 22, 25, 22, 20, 18, 16][c - 5]
            elif r <= 8:
                t[r][c] = [12, 14, 16, 18, 20, 18, 16, 14, 12][c - 5]
            elif r <= 13:
                t[r][c] = [6, 8, 10, 12, 14, 12, 10, 8, 6][c - 5]
            else:
                t[r][c] = [0, 0, 0, 2, 4, 2, 0, 0, 0][c - 5]
    t[18][5] = t[18][13] = 0
    return t


def _make_cannon_table():
    t = [[0] * 19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c):
                continue
            if c < 5 or c > 13:
                continue
            if r <= 4:
                t[r][c] = 20 + max(0, 5 - abs(c - 9))
            elif r <= 8:
                t[r][c] = 25 + max(0, 5 - abs(c - 9))
            elif r <= 13:
                t[r][c] = 15 + max(0, 5 - abs(c - 9))
            else:
                t[r][c] = max(0, 5 - abs(c - 9))
    t[16][6] = t[16][12] = 0
    return t


def _make_pawn_table():
    t = [[0] * 19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c):
                continue
            if r >= 14:
                if 5 <= c <= 13 and c % 2 == 1:
                    t[r][c] = 1
                continue
            if c < 5 or c > 13:
                continue
            advance = max(0, 13 - r)
            center = max(0, 4 - abs(c - 9) // 2)
            t[r][c] = min(18, 5 + advance * 2 + center)
    return t


PIECE_TABLES = {
    "K": _make_king_table(),
    "A": _make_advisor_table(),
    "B": _make_bishop_table(),
    "N": _make_knight_table(),
    "R": _make_rook_table(),
    "C": _make_cannon_table(),
    "P": _make_pawn_table(),
}


def piece_square_bonus(ptype, color, r, c):
    cr, cc = _canonical_pos(color, r, c)
    tbl = PIECE_TABLES.get(ptype)
    return tbl[cr][cc] if tbl else 0


# ====== 高速局面评估 ======

def _is_ally_of(game, color, other):
    if other == color:
        return True
    if game.mode in ("team", "team_stratagem") and game.teams:
        return game.is_same_team(color, other)
    return False


def _is_enemy_of(game, color, other):
    if other == color:
        return False
    if game.mode in ("team", "team_stratagem") and game.teams:
        return not game.is_same_team(color, other)
    return True


def fast_evaluate(game, color):
    """快速评估函数（不评估开局出动、象连环等精细项）"""
    score = 0

    for r in range(19):
        for c in range(19):
            pc = game.board[r][c]
            if not pc or pc["color"] == NEUTRAL:
                continue
            val = PIECE_VALUES.get(pc["type"], 0) + piece_square_bonus(pc["type"], pc["color"], r, c)
            if pc["color"] == color:
                score += val
            elif _is_ally_of(game, color, pc["color"]):
                score += int(val * 0.85)
            else:
                score -= int(val * 1.0)

    # 王的安全：简单惩罚
    king_pos = game._find_king(color)
    if king_pos:
        kr, kc = king_pos
        props = PLAYER_PROPS[color]
        r1, r2, c1, c2 = props["palace"]
        if not (r1 <= kr <= r2 and c1 <= kc <= c2):
            score -= 600  # 出九宫

        # 炮威胁检测（简化）：对手炮与己方帅同线且中间恰有一子
        for opp in TURN_ORDER:
            if not _is_enemy_of(game, color, opp):
                continue
            for rr in range(19):
                for cc in range(19):
                    pc = game.board[rr][cc]
                    if pc and pc["color"] == opp and pc["type"] == "C":
                        if rr == kr:
                            between = sum(1 for ccc in range(min(cc, kc) + 1, max(cc, kc)) if game.board[kr][ccc] is not None)
                            if between == 1:
                                score -= 8000
                        elif cc == kc:
                            between = sum(1 for rrr in range(min(rr, kr) + 1, max(rr, kr)) if game.board[rrr][kc] is not None)
                            if between == 1:
                                score -= 8000

    return score
