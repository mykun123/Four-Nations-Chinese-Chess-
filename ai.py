# ai.py - Minimax AI with alpha-beta pruning for Chinese Chess
from game_logic import Game, RED, BLACK

PIECE_VALUES = {
    "K": 10000,
    "R": 900,
    "C": 450,
    "N": 400,
    "B": 200,
    "A": 200,
    "P": 100,
}

# Position bonus tables (indexed by row 0-9, col 0-8)
# Black perspective: higher rows = deeper into enemy territory

HORSE_BONUS = [
    [0,  0,  0,  0,  3,  0,  0,  0,  0],
    [0,  1,  2,  4,  5,  4,  2,  1,  0],
    [0, -2,  3,  6,  7,  6,  3, -2,  0],
    [-1, 2,  5,  8,  9,  8,  5,  2, -1],
    [0,  4,  4,  7,  8,  7,  4,  4,  0],
    [-3, 2,  3,  6,  6,  6,  3,  2, -3],
    [0,  1,  2,  3,  5,  3,  2,  1,  0],
    [-4,-2, -1,  0,  0,  0, -1, -2, -4],
    [0, -6, -3, -1,  0, -1, -3, -6,  0],
    [0,  0, -5, -3, -7, -3, -5,  0,  0],
]

ELEPHANT_BONUS = [
    [-2,-4, -8,-12,-16,-12,-8, -4, -2],
    [-4, 0, -2, -4, -8, -4, -2,  0, -4],
    [-8,-2,  3,  5,  7,  5,  3, -2, -8],
    [-12,-4, 5,  9, 12,  9,  5, -4, -12],
    [-16,-8, 7, 12, 16, 12,  7, -8, -16],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
]

ROOK_BONUS = [
    [2, 3, 4, 5, 6, 5, 4, 3, 2],
    [-1,-1, 0, 0, 0, 0, 0, -1, -1],
    [-1,-1, 0, 0, 0, 0, 0, -1, -1],
    [0,  0, 0, 3, 4, 3, 0,  0,  0],
    [0,  0, 0, 2, 5, 2, 0,  0,  0],
    [-1,-1, 0, 0, 0, 0, 0, -1, -1],
    [-1,-1, 0, 0, 0, 0, 0, -1, -1],
    [2, 3, 4, 5, 6, 5, 4, 3, 2],
    [2, 3, 4, 5, 6, 5, 4, 3, 2],
    [4, 5, 6, 7, 8, 7, 6, 5, 4],
]

PAWN_BONUS = [
    [-8,-7,-6,-5,-4,-5,-6,-7,-8],
    [-9,-8,-7,-6,-5,-6,-7,-8,-9],
    [-10,-9,-8,-7,-6,-7,-8,-9,-10],
    [ 3, 2, 1, 0, 0, 0, 1, 2,  3],
    [ 5, 4, 3, 2, 1, 2, 3, 4,  5],
    [ 0,  0, 0, 0, 0, 0, 0,  0,  0],
    [ 0,  0, 0, 0, 0, 0, 0,  0,  0],
    [-5,-4,-3,-2,-1,-2,-3,-4,-5],
    [-3,-2,-1, 0, 0, 0, -1,-2,-3],
    [10, 9, 8, 7, 6, 7, 8, 9, 10],
]

CANNON_BONUS = [
    [0, 0, 2, 4, 6, 4, 2, 0, 0],
    [2, 2, 4, 6, 8, 6, 4, 2, 2],
    [4, 4, 6, 8, 10, 8, 6, 4, 4],
    [2, 4, 6, 8, 10, 8, 6, 4, 2],
    [0, 2, 4, 6, 8, 6, 4, 2, 0],
    [0, 0, 0, 2, 4, 2, 0, 0, 0],
    [-2,-2, 0, 0, 0, 0, 0,-2,-2],
    [-4,-4,-2, 0, 0, 0,-2,-4,-4],
    [-4,-4,-2,-2, 0,-2,-2,-4,-4],
    [-4,-4,-4,-2,-2,-2,-4,-4,-4],
]

ADVISOR_BONUS = [
    [0, 0, 0, 0, 2, 0, 0, 0, 0],
    [0, 0, 0, 2, 4, 2, 0, 0, 0],
    [0, 0, 0, 0, 6, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 6, 0, 0, 0, 0],
    [0, 0, 0, 2, 4, 2, 0, 0, 0],
    [0, 0, 0, 0, 2, 0, 0, 0, 0],
]

POSITION_TABLES = {
    "R": ROOK_BONUS,
    "N": HORSE_BONUS,
    "B": ELEPHANT_BONUS,
    "P": PAWN_BONUS,
    "C": CANNON_BONUS,
    "A": ADVISOR_BONUS,
}


def evaluate(game):
    """Enhanced evaluation with material, position, checks, king safety, and cannon defense."""
    score = 0
    for r in range(10):
        for c in range(9):
            p = game.board[r][c]
            if not p:
                continue
            val = PIECE_VALUES.get(p["type"], 0)
            bonus_table = POSITION_TABLES.get(p["type"])
            pos_bonus = 0
            if bonus_table:
                if p["color"] == BLACK:
                    pos_bonus = bonus_table[r][c]
                else:
                    pos_bonus = bonus_table[9 - r][8 - c]
            total = val + pos_bonus
            score += total if p["color"] == BLACK else -total

    # King positions
    black_king = game.find_king(BLACK)
    red_king = game.find_king(RED)

    # Check bonus
    if black_king and game.is_attacked_by(black_king[0], black_king[1], RED):
        score -= 80  # Black king in check - penalty
    if red_king and game.is_attacked_by(red_king[0], red_king[1], BLACK):
        score += 80  # Red king in check - bonus

    # Cannon threat detection
    if black_king:
        score -= _cannon_threat_penalty(game, BLACK)
    if red_king:
        score += _cannon_threat_penalty(game, RED)

    # King defender bonus
    if black_king:
        score += _king_defenders(game, BLACK) * 15
    if red_king:
        score -= _king_defenders(game, RED) * 15

    # Flying general bonus
    if red_king and black_king:
        if red_king[1] == black_king[1]:
            count = game._pieces_between(
                min(red_king[0], black_king[0]), red_king[1],
                max(red_king[0], black_king[0]), red_king[1]
            )
            if count == 0:
                score += 30
    return score


def _cannon_threat_penalty(game, color):
    """检测敌方炮是否威胁到己方将/帅（隔一子瞄准）"""
    king_pos = game.find_king(color)
    if not king_pos:
        return 0
    kr, kc = king_pos
    opponent = -color
    penalty = 0

    for r in range(10):
        for c in range(9):
            p = game.board[r][c]
            if not p or p["color"] != opponent or p["type"] != "C":
                continue
            # Check if cannon threatens king along row or column
            if r == kr:
                between = game._pieces_between(r, min(c, kc), r, max(c, kc))
                if between == 1:
                    penalty += 100  # cannon aiming at king, severe penalty
            elif c == kc:
                between = game._pieces_between(min(r, kr), c, max(r, kr), c)
                if between == 1:
                    penalty += 100
    return penalty


def _king_defenders(game, color):
    """统计将/帅周围2格内的己方棋子数"""
    king_pos = game.find_king(color)
    if not king_pos:
        return 0
    kr, kc = king_pos
    count = 0
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            if dr == 0 and dc == 0:
                continue
            nr, nc = kr + dr, kc + dc
            if 0 <= nr < 10 and 0 <= nc < 9:
                p = game.board[nr][nc]
                if p and p["color"] == color:
                    count += 1
    return count


def best_move(game, depth=4):
    """Return (fr, fc, tr, tc) or None. Deeper search + check extension."""
    moves = game.get_legal_moves(BLACK)
    if not moves:
        return None

    # Sort by capture value + check bonus for better pruning
    def move_score(m):
        fr, fc, tr, tc = m
        target = game.board[tr][tc]
        base = PIECE_VALUES.get(target["type"], 0) if target else 0
        # bonus for giving check
        piece = game.board[fr][fc]
        captured = game.board[tr][tc]
        game.board[fr][fc] = None
        game.board[tr][tc] = piece
        if game.in_check(RED):
            base += 8
        game.board[tr][tc] = captured
        game.board[fr][fc] = piece
        return base

    moves.sort(key=move_score, reverse=True)

    best_val = float("-inf")
    best_list = []
    alpha = float("-inf")
    beta = float("inf")

    for fr, fc, tr, tc in moves:
        info = game.apply_move(fr, fc, tr, tc)
        # Check extension: search deeper after a check
        ext = 1 if game.in_check(RED) else 0
        val = _minimax(game, depth - 1 + ext, False, alpha, beta)
        game.unapply_move(fr, fc, tr, tc, info)
        if val > best_val:
            best_val = val
            best_list = [(fr, fc, tr, tc)]
        elif val == best_val:
            best_list.append((fr, fc, tr, tc))
        alpha = max(alpha, val)

    import random
    return random.choice(best_list) if best_list else None


def _minimax(game, depth, is_maximizing, alpha, beta):
    if depth <= 0:
        return evaluate(game)

    moves = game.get_legal_moves(BLACK if is_maximizing else RED)
    if not moves:
        if game.in_check(game.turn):
            return -99999 if game.turn == BLACK else 99999
        return 0  # stalemate

    # Move ordering: captures first
    def sort_key(m):
        fr, fc, tr, tc = m
        target = game.board[tr][tc]
        return PIECE_VALUES.get(target["type"], 0) if target else 0

    moves.sort(key=sort_key, reverse=True)

    if is_maximizing:
        best = float("-inf")
        for fr, fc, tr, tc in moves:
            info = game.apply_move(fr, fc, tr, tc)
            val = _minimax(game, depth - 1, False, alpha, beta)
            game.unapply_move(fr, fc, tr, tc, info)
            best = max(best, val)
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return best
    else:
        best = float("inf")
        for fr, fc, tr, tc in moves:
            info = game.apply_move(fr, fc, tr, tc)
            val = _minimax(game, depth - 1, True, alpha, beta)
            game.unapply_move(fr, fc, tr, tc, info)
            best = min(best, val)
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best
