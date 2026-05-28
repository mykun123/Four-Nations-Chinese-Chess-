# ai_4p.py — 四国象棋AI（支持4人博弈的 Paranoid Search + 静态搜索 + 局面评估）
from game_4p import (
    RED, BLACK, GREEN, BLUE, NEUTRAL,
    TURN_ORDER, PIECE_VALUES, PLAYER_PROPS, in_blank,
)
import random
import time

# ─── 盟友/敌人判断（自由模式 vs 组队模式）──────────────────

def _is_ally_of(game, color, other):
    """other 是 color 的盟友？自由模式：仅自己；组队模式：同队"""
    if other == color:
        return True
    if game.mode == "team" and game.teams:
        return game.is_same_team(color, other)
    return False

def _is_enemy_of(game, color, other):
    """other 是 color 的敌人？"""
    if other == color:
        return False
    if game.mode == "team" and game.teams:
        return not game.is_same_team(color, other)
    return True

# ─── 规范坐标转换 ─────────────────────────────────────────
# 所有位置价值表以红方为基准（红方视角 = 正立朝下棋盘）
# 红方: (r, c)       黑方: (18-r, c)    绿方: (18-c, r)    蓝方: (c, r)

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

# ─── 位置价值表（红方基准）─────────────────────────────────
# 对每个棋子类型生成 19×19 价值表，空白角落记为 0

def _make_king_table():
    t = [[-1000]*19 for _ in range(19)]  # 出九宫：重罚
    for r in range(16, 19):
        for c in range(8, 11):
            if in_blank(r, c): continue
            t[r][c] = 0
    t[18][9] = 300
    t[18][8] = t[18][10] = 200
    t[17][9] = 200
    t[17][8] = t[17][10] = 100
    t[16][9] = 50
    t[16][8] = t[16][10] = 0
    return t

def _make_advisor_table():
    t = [[0]*19 for _ in range(19)]
    t[17][8] = t[17][10] = 20
    t[18][9] = 15
    t[16][9] = 10
    t[17][9] = 5
    t[16][8] = t[16][10] = 5
    t[18][8] = t[18][10] = 0
    return t

# 中象/象：己方半场×奇数格（田字），原位最高，乱走重罚
def _make_bishop_table():
    t = [[-60]*19 for _ in range(19)]  # 非原位皆重罚
    for r in range(14, 19):
        for c in range(5, 14):
            if in_blank(r, c): continue
            if (r + c) % 2 == 0: continue  # 象走奇数格
            t[r][c] = 0  # 合法象位基础分
    # 起始位置：最高分（双象连环）
    t[18][7] = t[18][11] = 50
    # 前线防守位（连环象可到达）
    t[16][5] = t[16][13] = 30
    t[16][9] = 35  # 中路象（连环核心）
    # 更前位置（过河前，可接受）
    t[14][7] = t[14][11] = 10
    return t

# 马：跳出原位奖励，但前期避免在边路(-3)
def _make_knight_table():
    t = [[-5]*19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c): continue
            if c < 5 or c > 13: continue
            base = 5  # 马在任何可走位置都有基础奖励
            forward = max(0, 14 - r)
            central = max(0, 7 - abs(c - 9))
            penalty = -8 if r <= 2 or r >= 16 else 0
            t[r][c] = base + forward + central + penalty
    return t

# 车：离开底线大奖励，过河后更高
def _make_rook_table():
    t = [[0]*19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c): continue
            if c < 5 or c > 13: continue
            if r <= 4:
                t[r][c] = [16,18,20,22,25,22,20,18,16][c-5]
            elif r <= 8:
                t[r][c] = [12,14,16,18,20,18,16,14,12][c-5]
            elif r <= 13:
                t[r][c] = [6,8,10,12,14,12,10,8,6][c-5]
            else:
                # 底线（r>=14）：鼓励出车，原位0，离开底线得正分
                t[r][c] = [0,0,0,2,4,2,0,0,0][c-5]
    # 车原位(列5和列13) = 0，鼓励出动
    t[18][5] = t[18][13] = 0
    return t

# 炮：离开原位奖励，到中场最高
def _make_cannon_table():
    t = [[0]*19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c): continue
            if c < 5 or c > 13: continue
            if r <= 4:
                t[r][c] = 20 + max(0, 5 - abs(c - 9))
            elif r <= 8:
                t[r][c] = 25 + max(0, 5 - abs(c - 9))
            elif r <= 13:
                t[r][c] = 15 + max(0, 5 - abs(c - 9))
            else:
                t[r][c] = max(0, 5 - abs(c - 9))
    # 炮原位(16,6)和(16,12)：不加分，鼓励移动
    t[16][6] = t[16][12] = 0
    return t

# 兵：未过河低分，过河后加分
def _make_pawn_table():
    t = [[0]*19 for _ in range(19)]
    for r in range(19):
        for c in range(19):
            if in_blank(r, c): continue
            if r >= 14:
                # 己方半场：原位得分极低
                if 5 <= c <= 13 and c % 2 == 1:
                    t[r][c] = 1
                continue
            if c < 5 or c > 13: continue
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

def _piece_square_bonus(ptype, color, r, c):
    cr, cc = _canonical_pos(color, r, c)
    tbl = PIECE_TABLES.get(ptype)
    return tbl[cr][cc] if tbl else 0

# ─── 攻击检测 ─────────────────────────────────────────────

def _color_attacks_square(game, r, c, attacker_color):
    """判断 attacker_color 是否有棋子攻击 (r,c)（与 _is_square_attacked 同逻辑但按颜色过滤）"""
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r + dr, c + dc
        found_screen = False
        while game.in_bounds(nr, nc):
            piece = game.board[nr][nc]
            if piece is None:
                nr += dr; nc += dc; continue
            if piece["color"] == NEUTRAL:
                break
            if not found_screen:
                # 第一个遇到的棋子：
                # 如果是 attacker_color 的子，可能直接攻击（K/P/R 或炮架）
                # 如果是别家的子，仍可以作为炮架
                if piece["color"] == attacker_color:
                    dist = abs(nr - r) + abs(nc - c)
                    if dist == 1 and piece["type"] == "K":
                        return True
                    if dist == 1 and piece["type"] == "P":
                        if (r, c) in game._pawn_moves(nr, nc, attacker_color):
                            return True
                    if piece["type"] == "R":
                        return True
                # 任意颜色的子都可以当炮架（第二个子如果是 attacker_color 的炮则攻击成立）
                found_screen = True
            else:
                # 第二个棋子：如果是 attacker_color 的炮则攻击成立
                if piece["color"] == attacker_color and piece["type"] == "C":
                    return True
                break
            nr += dr; nc += dc

    for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        nr, nc = r + dr, c + dc
        if game.in_bounds(nr, nc):
            p = game.board[nr][nc]
            if p and p["color"] == attacker_color and p["type"] == "A":
                return True
        nr2, nc2 = r + dr*2, c + dc*2
        if game.in_bounds(nr2, nc2):
            if game.board[r+dr][c+dc] is None:
                p = game.board[nr2][nc2]
                if p and p["color"] == attacker_color and p["type"] == "B":
                    return True

    for dr, dc, br, bc in [
        (-2, -1, -1, 0), (-2, 1, -1, 0),
        (2, -1, 1, 0),   (2, 1, 1, 0),
        (-1, -2, 0, -1), (-1, 2, 0, 1),
        (1, -2, 0, -1),  (1, 2, 0, 1),
    ]:
        kr, kc = r - dr, c - dc
        if not game.in_bounds(kr, kc): continue
        p = game.board[kr][kc]
        if p and p["color"] == attacker_color and p["type"] == "N":
            if game.in_bounds(kr+br, kc+bc) and game.board[kr+br][kc+bc] is None:
                return True
    return False

# ─── 局面评估 ─────────────────────────────────────────────

def evaluate(game, color):
    """从 color 视角评估局面。正值 = 对 color 有利。"""
    score = 0

    # 1. 子力 + 位置
    for r in range(19):
        for c in range(19):
            pc = game.board[r][c]
            if not pc or pc["color"] == NEUTRAL:
                continue
            val = PIECE_VALUES.get(pc["type"], 0) + _piece_square_bonus(pc["type"], pc["color"], r, c)
            if pc["color"] == color:
                score += val
            elif _is_ally_of(game, color, pc["color"]):
                score += int(val * 0.85)  # 队友的子（略折价，不可完全控制）
            else:
                score -= int(val * 0.9)

    # 2. 将军奖励
    for opp in TURN_ORDER:
        if not _is_enemy_of(game, color, opp):
            continue
        kr = game._find_king(opp)
        if kr and _color_attacks_square(game, kr[0], kr[1], color):
            score += 200
    # 组队模式：队友将军也有奖励
    if game.mode == "team" and game.teams:
        for mate in TURN_ORDER:
            if not _is_ally_of(game, color, mate) or mate == color:
                continue
            for opp in TURN_ORDER:
                if not _is_enemy_of(game, color, opp):
                    continue
                kr = game._find_king(opp)
                if kr and _color_attacks_square(game, kr[0], kr[1], mate):
                    score += 120

    # 3. 受威胁子惩罚 + 有根子保护
    for r in range(19):
        for c in range(19):
            pc = game.board[r][c]
            if not pc or pc["color"] != color or pc["type"] == "K":
                continue
            val = PIECE_VALUES.get(pc["type"], 0)
            if val < 30:
                continue
            if game._is_square_attacked(r, c, own_color=color):
                # 检查是否有同色子保护（有根子）
                defended = _color_attacks_square(game, r, c, color)
                if not defended and game.mode == "team" and game.teams:
                    for mate in TURN_ORDER:
                        if not _is_ally_of(game, color, mate) or mate == color:
                            continue
                        if _color_attacks_square(game, r, c, mate):
                            defended = True
                            break
                if defended:
                    score -= int(val * 0.10)
                else:
                    score -= int(val * 0.40)

    # 4. 王的安全
    king_pos = game._find_king(color)
    if king_pos:
        kr, kc = king_pos
        props = PLAYER_PROPS[color]
        r1, r2, c1, c2 = props["palace"]
        if r1 <= kr <= r2 and c1 <= kc <= c2:
            score += 50
        else:
            score -= 500  # 出九宫重罚
        defenders = 0
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0: continue
                nr, nc = kr+dr, kc+dc
                if 0 <= nr < 19 and 0 <= nc < 19:
                    p = game.board[nr][nc]
                    if p and p["color"] == color:
                        defenders += 1
        score += defenders * 15
        if any(
            _is_enemy_of(game, color, opp) and game.alive.get(opp, True)
            and _color_attacks_square(game, kr, kc, opp)
            for opp in TURN_ORDER
        ):
            score -= 400  # 被将军重罚
        # 组队模式：检查队友的王是否被将军
        if game.mode == "team" and game.teams:
            for mate in TURN_ORDER:
                if not _is_ally_of(game, color, mate) or mate == color:
                    continue
                mk = game._find_king(mate)
                if mk:
                    if any(
                        _is_enemy_of(game, color, opp) and game.alive.get(opp, True)
                        and _color_attacks_square(game, mk[0], mk[1], opp)
                        for opp in TURN_ORDER
                    ):
                        score -= 300  # 队友王被将军
        # 炮威胁将/帅检测：对手炮同线且中间恰有一子 → 重罚
        for opp in TURN_ORDER:
            if not _is_enemy_of(game, color, opp):
                continue
            kr_pos = game._find_king(color)
            if not kr_pos:
                break
            kr, kc = kr_pos
            for rr in range(19):
                for cc in range(19):
                    pc = game.board[rr][cc]
                    if pc and pc["color"] == opp and pc["type"] == "C":
                        if rr == kr:
                            between = sum(1 for ccc in range(min(cc, kc)+1, max(cc, kc)) if game.board[kr][ccc] is not None)
                            if between == 1:
                                score -= 8000
                        elif cc == kc:
                            between = sum(1 for rrr in range(min(rr, kr)+1, max(rr, kr)) if game.board[rrr][kc] is not None)
                            if between == 1:
                                score -= 8000
        # 组队模式：队友的王受炮威胁也罚分
        if game.mode == "team" and game.teams:
            for mate in TURN_ORDER:
                if not _is_ally_of(game, color, mate) or mate == color:
                    continue
                mk = game._find_king(mate)
                if not mk:
                    continue
                for opp in TURN_ORDER:
                    if not _is_enemy_of(game, color, opp):
                        continue
                    for rr in range(19):
                        for cc in range(19):
                            pc = game.board[rr][cc]
                            if pc and pc["color"] == opp and pc["type"] == "C":
                                if rr == mk[0]:
                                    between = sum(1 for ccc in range(min(cc, mk[1])+1, max(cc, mk[1])) if game.board[mk[0]][ccc] is not None)
                                    if between == 1:
                                        score -= 4000
                                elif cc == mk[1]:
                                    between = sum(1 for rrr in range(min(rr, mk[0])+1, max(rr, mk[0])) if game.board[rrr][mk[1]] is not None)
                                    if between == 1:
                                        score -= 4000
        if 6 <= kr <= 12 and 6 <= kc <= 12:
            score -= 200  # 暴露在中立区

    # 5. 开局出动奖励 + 布局惩罚
    total_moves = len(game.move_history)
    if total_moves < 40:  # 开局阶段
        own_pieces = []
        for r in range(19):
            for c in range(19):
                pc = game.board[r][c]
                if pc and pc["color"] == color:
                    own_pieces.append((pc, r, c))
        dev_bonus = 0
        for pc, r, c in own_pieces:
            cr, cc = _canonical_pos(color, r, c)
            pt = pc["type"]
            if pt == "R":
                if cr < 16 or cc not in (5, 13):
                    dev_bonus += 30
                if cr <= 8:
                    dev_bonus += 20
            elif pt == "C":
                if not (cr == 16 and cc in (6, 12)):
                    dev_bonus += 20
                if cr <= 8:
                    dev_bonus += 10
            elif pt == "N":
                if not (cr == 18 and cc in (6, 12)):
                    dev_bonus += 15
                if cr <= 8:
                    dev_bonus += 10
            elif pt == "P":
                if cr <= 8:
                    dev_bonus += 8
            elif pt == "B":
                if not (cr == 18 and cc in (7, 11)):
                    dev_bonus -= 25
        score += dev_bonus

        # 象连环检测
        bpos = [(r, c) for pc, r, c in own_pieces if pc["type"] == "B"]
        if len(bpos) == 2:
            r1, c1 = _canonical_pos(color, bpos[0][0], bpos[0][1])
            r2, c2 = _canonical_pos(color, bpos[1][0], bpos[1][1])
            if abs(r1 - r2) > 2 or abs(c1 - c2) > 4:
                score -= 30
        elif len(bpos) == 1:
            score -= 20

        # 士移位惩罚
        for pc, r, c in own_pieces:
            cr, cc = _canonical_pos(color, r, c)
            if pc["type"] == "A":
                if not (cr == 18 and cc in (8, 10)):
                    score -= 15

    return score

# ─── 搜索工具函数 ─────────────────────────────────────────

def _apply_move(game, move):
    """在棋盘上执行一步走子（不保存历史，不推进 turn_idx）。
    返回 (captured, killed_list) 用于悔棋。"""
    fr, fc, tr, tc = move
    captured = game.board[tr][tc]
    killed = []
    game.board[tr][tc] = game.board[fr][fc]
    game.board[fr][fc] = None
    if captured and captured["type"] == "K":
        dead = captured["color"]
        game.alive[dead] = False
        for rr in range(19):
            for cc in range(19):
                p = game.board[rr][cc]
                if p and p["color"] == dead:
                    killed.append((rr, cc, p))
                    game.board[rr][cc] = None
    return captured, killed

def _undo_move(game, move, captured, killed):
    """撤销 _apply_move 的修改。"""
    fr, fc, tr, tc = move
    for rr, cc, p in killed:
        game.board[rr][cc] = p
    if killed:
        game.alive[killed[0][2]["color"]] = True
    game.board[fr][fc] = game.board[tr][tc]
    game.board[tr][tc] = captured

def _next_player_after(game, color):
    """返回轮到 color 之后的存活玩家。"""
    try:
        idx = game.turn_order.index(color)
    except ValueError:
        return game.turn_order[0]
    for i in range(1, 5):
        nxt = game.turn_order[(idx + i) % 4]
        if game.alive.get(nxt, True):
            return nxt
    return color

def _order_moves(moves, game, current_color):
    """MVV-LVA 排序：
    - 吃子：被吃价值×10 - 攻击子价值
    - 亏损交换：用高价值子吃低价值子到被对手保护的格 → 重罚
    - 受威胁子逃跑/防守 → 高优
    """
    _threat_cache = {}
    _defended_cache = {}
    for fr, fc, tr, tc in moves:
        if (fr, fc) not in _threat_cache:
            _threat_cache[(fr, fc)] = game._is_square_attacked(fr, fc, own_color=current_color)
        tgt = game.board[tr][tc]
        if tgt and tgt["color"] != current_color and (tr, tc) not in _defended_cache:
            _defended_cache[(tr, tc)] = game._is_square_attacked(tr, tc, own_color=current_color)

    def key(m):
        fr, fc, tr, tc = m
        tgt = game.board[tr][tc]
        atk = game.board[fr][fc]
        atk_type = atk["type"] if atk else ""
        score = 0
        if tgt and tgt["color"] != current_color:
            # 组队模式：不吃队友
            if _is_ally_of(game, current_color, tgt["color"]):
                return -100000
            tv = PIECE_VALUES.get(tgt["type"], 0)
            av = PIECE_VALUES.get(atk_type, 0)
            score = tv * 10 - av
            if _threat_cache.get((fr, fc), False):
                score = 10000 + tv * 10 - av
            elif av > tv and _defended_cache.get((tr, tc), False):
                score -= 5000
        elif _threat_cache.get((fr, fc), False):
            score = 5000
            if atk_type == "K":
                score = 30000  # 王被将军逃命最高优先级
        return score

    moves.sort(key=key, reverse=True)
    return moves

# ─── 静态搜索（Quiescence Search）─────────────────────────

_MAX_QUIESCE_MOVES = 3
_Q_SCORE_LIMIT = 150  # delta pruning: 低于此阈值的吃子不考虑

def _quiescence(game, ai_color, current_color, alpha, beta, qdepth):
    """静态搜索：在叶节点继续搜索吃子走法，解决水平线效应。"""
    stand_pat = evaluate(game, ai_color)

    # Stand-pat 剪枝
    is_ally = current_color == ai_color or _is_ally_of(game, ai_color, current_color)
    if is_ally:
        if stand_pat >= beta:
            return beta
        if alpha < stand_pat:
            alpha = stand_pat
    else:
        if stand_pat <= alpha:
            return alpha
        if beta > stand_pat:
            beta = stand_pat

    if qdepth <= 0:
        return stand_pat

    # 胜负判定（含组队）
    _team_alive = True
    if game.mode == "team" and game.teams:
        _team_alive = any(
            game.alive.get(c, True) and _is_ally_of(game, ai_color, c)
            for c in TURN_ORDER
        )
    if not game.alive.get(ai_color, True) or not _team_alive:
        return -99999 + (4 - qdepth)
    winners = game.check_winner()
    if ai_color in winners:
        return 99999 - (4 - qdepth)
    if game.mode == "team" and game.teams and winners:
        for w in winners:
            if _is_ally_of(game, ai_color, w):
                return 99999 - (4 - qdepth)
    if winners:
        return -99999

    if not game.alive.get(current_color, True):
        nxt = _next_player_after(game, current_color)
        return _quiescence(game, ai_color, nxt, alpha, beta, qdepth)

    moves = game.get_legal_moves(current_color)
    captures = []
    for m in moves:
        fr, fc, tr, tc = m
        tgt = game.board[tr][tc]
        if tgt and tgt["color"] != current_color:
            if _is_ally_of(game, ai_color, tgt["color"]):
                continue  # 组队不吃队友
            captures.append(m)

    if not captures:
        return stand_pat

    def cap_key(m):
        fr, fc, tr, tc = m
        tgt = game.board[tr][tc]
        atk = game.board[fr][fc]
        return PIECE_VALUES.get(tgt["type"], 0) * 10 - PIECE_VALUES.get(atk["type"], 0)
    captures.sort(key=cap_key, reverse=True)
    max_gain = PIECE_VALUES.get(game.board[captures[0][2]][captures[0][3]]["type"], 0)

    captures = captures[:_MAX_QUIESCE_MOVES]
    nxt = _next_player_after(game, current_color)

    if is_ally:
        best = alpha
        for move in captures:
            cap, killed = _apply_move(game, move)
            val = _quiescence(game, ai_color, nxt, alpha, beta, qdepth - 1)
            _undo_move(game, move, cap, killed)
            if val > best:
                best = val
            alpha = max(alpha, val)
            if alpha >= beta:
                break
        return best
    else:
        best = beta
        for move in captures:
            cap, killed = _apply_move(game, move)
            val = _quiescence(game, ai_color, nxt, alpha, beta, qdepth - 1)
            _undo_move(game, move, cap, killed)
            if val < best:
                best = val
            beta = min(beta, val)
            if alpha >= beta:
                break
        return best

# ─── 核心搜索 ─────────────────────────────────────────────

_MAX_AI_MOVES = 8
_MAX_OPP_MOVES = 3
_MAX_Q_DEPTH = 2

def _minimax_4p(game, ai_color, current_color, depth, alpha, beta):
    """4人搜索（支持自由/组队）：
    - 己方/队友回合 → 最大化（depth-1）
    - 对手回合 → 最小化（depth-1）"""
    if depth <= 0:
        return _quiescence(game, ai_color, current_color, alpha, beta, _MAX_Q_DEPTH)

    # 胜负判定（含组队）
    _team_alive = True
    if game.mode == "team" and game.teams:
        _team_alive = any(
            game.alive.get(c, True) and _is_ally_of(game, ai_color, c)
            for c in TURN_ORDER
        )
    if not game.alive.get(ai_color, True) or not _team_alive:
        return -99999 + (4 - depth)
    winners = game.check_winner()
    if ai_color in winners:
        return 99999 - (4 - depth)
    if game.mode == "team" and game.teams and winners:
        for w in winners:
            if _is_ally_of(game, ai_color, w):
                return 99999 - (4 - depth)
    if winners:
        return -99999

    if not game.alive.get(current_color, True):
        nxt = _next_player_after(game, current_color)
        return _minimax_4p(game, ai_color, nxt, depth, alpha, beta)

    moves = game.get_legal_moves(current_color)
    if not moves:
        nxt = _next_player_after(game, current_color)
        return _minimax_4p(game, ai_color, nxt, depth, alpha, beta)

    _order_moves(moves, game, current_color)
    is_ally = current_color == ai_color or _is_ally_of(game, ai_color, current_color)
    top_n = _MAX_AI_MOVES if is_ally else _MAX_OPP_MOVES
    if depth <= 2:
        top_n = min(top_n, 6)
    moves = moves[:top_n]
    nxt = _next_player_after(game, current_color)

    if is_ally:
        best = float("-inf")
        for move in moves:
            cap, killed = _apply_move(game, move)
            val = _minimax_4p(game, ai_color, nxt, depth - 1, alpha, beta)
            _undo_move(game, move, cap, killed)
            if val > best:
                best = val
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return best
    else:
        best = float("inf")
        for move in moves:
            cap, killed = _apply_move(game, move)
            val = _minimax_4p(game, ai_color, nxt, depth - 1, alpha, beta)
            _undo_move(game, move, cap, killed)
            if val < best:
                best = val
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best

# ─── 对外接口 ─────────────────────────────────────────────

def best_move(game, color, depth=5, debug_out=None):
    """入口：为 color 选出最佳走法。返回 (fr,fc,tr,tc) 或 None。"""
    moves = game.get_legal_moves(color)
    if not moves:
        return None

    _order_moves(moves, game, color)
    top_moves = moves[:_MAX_AI_MOVES]

    # 胜负判定（含组队）
    if not game.alive.get(color, True):
        return None
    if game.mode == "team" and game.teams:
        team_alive = any(
            game.alive.get(c, True) and _is_ally_of(game, color, c)
            for c in TURN_ORDER
        )
        if not team_alive:
            return None

    nxt = _next_player_after(game, color)
    move_scores = []

    for move in top_moves:
        cap, killed = _apply_move(game, move)
        val = _minimax_4p(game, color, nxt, depth - 1, float("-inf"), float("inf"))
        _undo_move(game, move, cap, killed)

        if cap and cap["type"] == "K":
            val += 50000

        move_scores.append((move, val))

    # 绝境求生：必输局面下优先换掉对方高价值子
    raw_best = max(s for _, s in move_scores) if move_scores else float("-inf")
    if raw_best < -2000:
        for i, (move, val) in enumerate(move_scores):
            fr, fc, tr, tc = move
            tgt = game.board[tr][tc]
            if tgt and _is_enemy_of(game, color, tgt["color"]):
                tv = PIECE_VALUES.get(tgt["type"], 0)
                val += tv * 0.8  # 换子奖励：吃高价值子优先
            move_scores[i] = (move, val)

    best_val = max(s for _, s in move_scores) if move_scores else float("-inf")
    best_list = [m for m, s in move_scores if abs(s - best_val) < 5]
    chosen = random.choice(best_list) if best_list else top_moves[0]

    if debug_out is not None:
        debug_out["scores"] = move_scores
        debug_out["chosen"] = chosen

    return chosen
