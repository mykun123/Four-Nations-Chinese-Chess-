# game_4p.py — 四国象棋核心逻辑
import random
from copy import deepcopy

# 玩家颜色
RED, BLACK, GREEN, BLUE = 0, 1, 2, 3
NEUTRAL = 4  # 中立单位（AI控制）

COLOR_NAMES = {RED: "红方", BLACK: "黑方", GREEN: "绿方", BLUE: "蓝方"}
COLOR_SHORT = {RED: "红", BLACK: "黑", GREEN: "绿", BLUE: "蓝"}

# 配色（UI用）
COLOR_RGB = {
    RED:   "#CC3333",
    BLACK: "#B8860B",
    GREEN: "#2E7D32",
    BLUE:  "#1565C0",
}

PIECE_NAMES = {
    "K": {"red": "帅", "black": "将", "green": "𩂰", "blue": "𩂱"},
    "A": {"red": "仕", "black": "士", "green": "𠦜", "blue": "𠦝"},
    "B": {"red": "相", "black": "象", "green": "𤣩", "blue": "𤣪"},
    "N": {"red": "马", "black": "馬", "green": "𮪤", "blue": "𮪥"},
    "R": {"red": "车", "black": "車", "green": "𨊇", "blue": "𨊈"},
    "C": {"red": "炮", "black": "砲", "green": "𥕛", "blue": "𥕜"},
    "P": {"red": "兵", "black": "卒", "green": "𠂉", "blue": "𠂊"},
}

# 用可打印字符替代生僻字
PIECE_CHARS = {
    RED:   {"K": "帅", "A": "仕", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵"},
    BLACK: {"K": "将", "A": "士", "B": "象", "N": "馬", "R": "車", "C": "砲", "P": "卒"},
    GREEN: {"K": "将", "A": "士", "B": "象", "N": "马", "R": "车", "C": "炮", "P": "卒"},
    BLUE:  {"K": "帅", "A": "仕", "B": "相", "N": "馬", "R": "車", "C": "砲", "P": "兵"},
    NEUTRAL: {"K": "帅", "A": "士", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵"},
}

PIECE_VALUES = {
    "K": 10000, "R": 900, "C": 550, "N": 400,
    "B": 200, "A": 200, "P": 100,
}

# 每个玩家的属性
# forward: 前进方向 (row变化 或 col变化)
# home: 己方半幅边界（某行或某列）
# palace: 九宫范围 (r1,r2,c1,c2)
PLAYER_PROPS = {
    RED: {
        "forward": (-1, 0),      # 前进=r-1
        "home_limit": 14,         # 不能低于row 14...不对, 是己半幅
        "river_boundary": 13,     # 河界（红方河在row 13-14之间，过河后row<=13）
        "river_check": lambda r: r <= 13,
        "palace": (16, 18, 8, 10),
        "rows": (14, 18),
        "cols": (5, 13),
    },
    BLACK: {
        "forward": (1, 0),       # 前进=r+1
        "river_boundary": 5,      # 河在row 4-5之间，过河后row>=5
        "river_check": lambda r: r >= 5,
        "palace": (0, 2, 8, 10),
        "rows": (0, 4),
        "cols": (5, 13),
    },
    GREEN: {
        "forward": (0, 1),       # 前进=c+1（朝右）
        "river_boundary": 5,      # 河在col 4-5之间，过河后col>=5
        "river_check": lambda c: c >= 5,
        "palace": (8, 10, 0, 2),
        "rows": (5, 13),
        "cols": (0, 4),
    },
    BLUE: {
        "forward": (0, -1),      # 前进=c-1（朝左）
        "river_boundary": 13,     # 河在col 13-14之间，过河后col<=13
        "river_check": lambda c: c <= 13,
        "palace": (8, 10, 16, 18),
        "rows": (5, 13),
        "cols": (14, 18),
    },
}

# 逆时针顺序
TURN_ORDER = [RED, GREEN, BLACK, BLUE]

# 中立区域（7×7 正方形）
NEUTRAL_ZONE = (6, 12)  # rows/cols 6-12 范围

# 中立单位初始布局 (row, col, type)
NEUTRAL_INIT = [
    (7, 7, "P"), (7, 11, "P"),
    (8, 8, "A"), (8, 10, "A"),
    (9, 9, "K"),
    (10, 8, "A"), (10, 10, "A"),
    (11, 7, "P"), (11, 11, "P"),
]

# 对面的玩家（组队时队友）
OPPOSITE = {RED: BLACK, BLACK: RED, GREEN: BLUE, BLUE: GREEN}

# 逆时针相邻
NEXT_PLAYER = {RED: GREEN, GREEN: BLACK, BLACK: BLUE, BLUE: RED}
PREV_PLAYER = {RED: BLUE, GREEN: RED, BLACK: GREEN, BLUE: BLACK}


def in_blank(r, c):
    """判断是否在空白四角"""
    BLANKS = [(0, 4, 0, 4), (0, 4, 14, 18), (14, 18, 0, 4), (14, 18, 14, 18)]
    for r1, r2, c1, c2 in BLANKS:
        if r1 <= r <= r2 and c1 <= c <= c2:
            return True
    return False


def compute_alternating_turn_order(teams):
    """
    根据队伍分配计算交替走子顺序（同队不连续走子）。
    teams: {color: team_id}
    返回: [color, color, ...] 交替顺序
    例: {RED:0, GREEN:0, BLACK:1, BLUE:1} -> [RED, BLACK, GREEN, BLUE]
    """
    base = [RED, GREEN, BLACK, BLUE]
    result = []
    used = set()

    if not teams or len(set(teams.values())) <= 1:
        return base

    current = 0
    current_team = teams[base[0]]

    while len(result) < 4:
        color = base[current]
        result.append(color)
        used.add(color)
        if len(result) >= 4:
            break
        for _ in range(4):
            current = (current + 1) % 4
            c = base[current]
            if c not in used and teams[c] != current_team:
                current_team = teams[c]
                break

    return result


class Game4P:
    def __init__(self, mode="ffa", teams=None, turn_order=None):
        """
        mode: "ffa"=自由对战, "team"=组队对战, "pvp"=人人对战
        teams: {color: team_id} ，如 {RED:0, GREEN:0, BLACK:1, BLUE:1}
        """
        self.mode = mode
        self.teams = teams or {}
        self.turn_order = turn_order or list(TURN_ORDER)
        self.board = [[None] * 19 for _ in range(19)]
        self.turn_idx = 0  # index in self.turn_order
        self.move_history = []
        self.last_neutral_moves = None  # [(fr,fc,tr,tc), ...] 悔棋时需撤销
        self.alive = {RED: True, BLACK: True, GREEN: True, BLUE: True}
        self.ai_debug_log = []  # [(turn, color, scores, chosen), ...]
        self.move_log = []  # [(turn, color, fr, fc, tr, tc, is_ai, piece_type, captured_type), ...]
        self._setup()
        self._setup_neutral()

    # ---- 当前玩家 ----
    @property
    def turn(self):
        return self.turn_order[self.turn_idx]

    def next_turn(self):
        """轮到下一个活着的玩家"""
        for _ in range(4):
            self.turn_idx = (self.turn_idx + 1) % 4
            if self.alive[self.turn_order[self.turn_idx]]:
                break

    # ---- 初始布阵 ----
    def _setup(self):
        b = self.board

        # 红方（下方）
        back = ["R", "N", "B", "A", "K", "A", "B", "N", "R"]
        for i, ptype in enumerate(back):
            b[18][5 + i] = {"color": RED, "type": ptype}
        b[16][6] = {"color": RED, "type": "C"}
        b[16][12] = {"color": RED, "type": "C"}
        for col in [5, 7, 9, 11, 13]:
            b[15][col] = {"color": RED, "type": "P"}

        # 黑方（上方）
        for i, ptype in enumerate(back):
            b[0][5 + i] = {"color": BLACK, "type": ptype}
        b[2][6] = {"color": BLACK, "type": "C"}
        b[2][12] = {"color": BLACK, "type": "C"}
        for col in [5, 7, 9, 11, 13]:
            b[3][col] = {"color": BLACK, "type": "P"}

        # 绿方（左方）
        for i, ptype in enumerate(back):
            b[5 + i][0] = {"color": GREEN, "type": ptype}
        b[6][2] = {"color": GREEN, "type": "C"}
        b[12][2] = {"color": GREEN, "type": "C"}
        for row in [5, 7, 9, 11, 13]:
            b[row][3] = {"color": GREEN, "type": "P"}

        # 蓝方（右方）
        for i, ptype in enumerate(back):
            b[5 + i][18] = {"color": BLUE, "type": ptype}
        b[6][16] = {"color": BLUE, "type": "C"}
        b[12][16] = {"color": BLUE, "type": "C"}
        for row in [5, 7, 9, 11, 13]:
            b[row][15] = {"color": BLUE, "type": "P"}

    def _setup_neutral(self):
        """在棋盘中央放置中立单位"""
        b = self.board
        for r, c, ptype in NEUTRAL_INIT:
            b[r][c] = {"color": NEUTRAL, "type": ptype}

    # ---- 通用棋盘操作 ----
    def get(self, r, c):
        if 0 <= r < 19 and 0 <= c < 19:
            return self.board[r][c]
        return None

    def in_bounds(self, r, c):
        if not (0 <= r < 19 and 0 <= c < 19):
            return False
        if in_blank(r, c):
            return False
        return True

    def _count_between(self, r1, c1, r2, c2):
        """统计两点之间直线上的棋子数"""
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

    # ---- 获取某方所有合法走法 ----
    def get_legal_moves(self, color):
        moves = []
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if not p or p["color"] != color:
                    continue
                for tr, tc in self._pseudo_moves(r, c, color):
                    # 模拟走子
                    captured = self.board[tr][tc]
                    piece = self.board[r][c]
                    self.board[r][c] = None
                    self.board[tr][tc] = piece

                    # 检查是否合理（不能吃自己的子、不能将杀自己的王、不能送将）
                    ok = True
                    if captured and captured["color"] == color:
                        ok = False
                    if captured and self.is_same_team(color, captured["color"]):
                        ok = False
                    if ok:
                        if piece["type"] == "K":
                            # 王移动 → 检查新位置
                            if self._is_square_attacked(tr, tc, own_color=color):
                                ok = False
                        else:
                            king = self._find_king(color)
                            if king is None:
                                ok = False
                            elif (r == king[0] or c == king[1] or
                                  abs(r - king[0]) == abs(c - king[1])):
                                # 该子与王处于同行/列/斜线，移动可能暴露王
                                if self._is_square_attacked(king[0], king[1], own_color=color):
                                    ok = False
                            # else: 该子不在王的方向上，移动不会影响王的安全

                    self.board[r][c] = piece
                    self.board[tr][tc] = captured

                    if ok:
                        moves.append((r, c, tr, tc))
        return moves

    # ---- 走子 ----
    def make_move(self, fr, fc, tr, tc, is_ai=False):
        # 走子前保存快照（用于悔棋）
        snapshot = deepcopy(self.board)
        alive_snap = dict(self.alive)
        turn_idx_snap = self.turn_idx

        info = {
            "from": (fr, fc), "to": (tr, tc),
            "piece": self.board[fr][fc],
            "captured": self.board[tr][tc],
            "board_snapshot": snapshot,
            "alive_snapshot": alive_snap,
            "turn_idx": turn_idx_snap,
        }
        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None
        self.move_history.append(info)

        # 记录全局走子日志
        piece = info["piece"]
        cap = info["captured"]
        piece_type = piece["type"] if piece else "?"
        cap_type = cap["type"] if cap else None
        turn_num = len(self.move_history)
        self.move_log.append((turn_num, piece["color"], fr, fc, tr, tc, is_ai, piece_type, cap_type))

        # 如果吃子
        if cap:
            dead = cap["color"]
            if cap["type"] == "K":
                self.alive[dead] = False
                for r in range(19):
                    for c in range(19):
                        p = self.board[r][c]
                        if p and p["color"] == dead:
                            self.board[r][c] = None
                # 奖励炮：仅自由混战灭人奖励炮（组队模式不奖励）
                if self.mode not in ("team", "team_stratagem"):
                    capturer = piece["color"]
                    if dead == NEUTRAL:
                        back_candidates = []
                    elif dead == RED:
                        back_candidates = [(18, c) for c in range(19) if not in_blank(18, c) and self.board[18][c] is None]
                    elif dead == BLACK:
                        back_candidates = [(0, c) for c in range(19) if not in_blank(0, c) and self.board[0][c] is None]
                    elif dead == GREEN:
                        back_candidates = [(r, 0) for r in range(19) if not in_blank(r, 0) and self.board[r][0] is None]
                    else:  # BLUE
                        back_candidates = [(r, 18) for r in range(19) if not in_blank(r, 18) and self.board[r][18] is None]
                    if back_candidates:
                        br, bc = random.choice(back_candidates)
                        self.board[br][bc] = {"color": capturer, "type": "C"}
            elif not self._has_any_piece(dead):
                self.alive[dead] = False

        self.next_turn()

    def undo_last(self):
        """悔棋：恢复到上一个走子前的状态"""
        if not self.move_history:
            return None
        info = self.move_history.pop()
        self.board = info["board_snapshot"]
        self.alive = info["alive_snapshot"]
        self.turn_idx = info["turn_idx"]
        return info["from"], info["to"], info["captured"]

    def _has_any_piece(self, color):
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if p and p["color"] == color:
                    return True
        return False

    def _find_king(self, color):
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if p and p["color"] == color and p["type"] == "K":
                    return r, c
        return None

    # ---- 中立单位 ----
    NEUTRAL_MIN = 6
    NEUTRAL_MAX = 12
    # 帅/士的九宫（中间田字）
    PALACE_MIN = 9
    PALACE_MAX = 11

    def _in_neutral_zone(self, r, c):
        return self.NEUTRAL_MIN <= r <= self.NEUTRAL_MAX and self.NEUTRAL_MIN <= c <= self.NEUTRAL_MAX

    def _in_palace(self, r, c):
        """是否在中间田字（帅/士的活动范围）"""
        return self.PALACE_MIN <= r <= self.PALACE_MAX and self.PALACE_MIN <= c <= self.PALACE_MAX

    def _neutral_pseudo_moves(self, r, c):
        """生成中立单位在一个走法范围内的所有落点（不含非法位置）"""
        piece = self.board[r][c]
        if not piece or piece["color"] != NEUTRAL:
            return []
        ptype = piece["type"]
        moves = []

        if ptype == "K":  # 帅：一步直走，限中间田字
            dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            bounds_check = self._in_palace
        elif ptype == "A":  # 士：一步斜走，限中间田字
            dirs = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            bounds_check = self._in_palace
        elif ptype == "P":  # 兵：一步直走，限整个中立区
            dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            bounds_check = self._in_neutral_zone
        else:
            return []

        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if not bounds_check(nr, nc):
                continue
            if not self.in_bounds(nr, nc):
                continue
            target = self.board[nr][nc]
            if target and target["color"] == NEUTRAL:
                continue  # 不能吃友军
            moves.append((nr, nc))
        return moves

    def _find_nearest_enemy(self, r, c):
        """返回距离 (r,c) 最近的敌方棋子位置（曼哈顿距离），没有则返回 None"""
        best = None
        best_dist = 999
        for rr in range(19):
            for cc in range(19):
                p = self.board[rr][cc]
                if p and p["color"] != NEUTRAL:
                    d = abs(rr - r) + abs(cc - c)
                    if d < best_dist:
                        best_dist = d
                        best = (rr, cc)
        return best

    def _find_cannon_threats(self):
        """检查是否有炮威胁到中立帅。
        返回 [(cannon_r, cannon_c, screen_r, screen_c), ...] 威胁列表
        若炮和帅在同一直线且中间恰好有1个棋子（炮架），则该炮可杀帅。"""
        mr, mc = self._find_king(NEUTRAL)
        if mr is None:
            return []

        threats = []
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if not p or p["type"] != "C" or p["color"] == NEUTRAL:
                    continue
                # 同行或同列
                if r == mr:
                    step = 1 if mc > c else -1
                    between = 0
                    screen_pos = None
                    for cc in range(c + step, mc, step):
                        if self.board[r][cc] is not None:
                            between += 1
                            screen_pos = (r, cc)
                    if between == 1:
                        threats.append((r, c, screen_pos[0], screen_pos[1]))
                elif c == mc:
                    step = 1 if mr > r else -1
                    between = 0
                    screen_pos = None
                    for rr in range(r + step, mr, step):
                        if self.board[rr][c] is not None:
                            between += 1
                            screen_pos = (rr, c)
                    if between == 1:
                        threats.append((r, c, screen_pos[0], screen_pos[1]))
        return threats

    def _find_cannon_alignments(self):
        """检测所有对准帅的炮（不论中间有几个子）
        返回 [(cannon_r, cannon_c, between_count), ...]"""
        mr, mc = self._find_king(NEUTRAL)
        if mr is None:
            return []
        result = []
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if not p or p["type"] != "C" or p["color"] == NEUTRAL:
                    continue
                if r == mr:
                    step = 1 if mc > c else -1
                    between = sum(1 for cc in range(c + step, mc, step) if self.board[r][cc] is not None)
                    result.append((r, c, between))
                elif c == mc:
                    step = 1 if mr > r else -1
                    between = sum(1 for rr in range(r + step, mr, step) if self.board[rr][c] is not None)
                    result.append((r, c, between))
        return result

    def _is_neutral_under_cannon_threat(self, r, c, ignore_pos=None):
        """检查 (r,c) 上的中立单位是否正被敌方炮瞄准（炮与目标同行/列，中间恰有1个棋子）。
        ignore_pos: 模拟走子时忽略的原始位置（相当于该位置已空）。"""
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            found_screen = False
            while self.in_bounds(nr, nc):
                if ignore_pos and (nr, nc) == ignore_pos:
                    nr += dr
                    nc += dc
                    continue
                piece = self.board[nr][nc]
                if piece is None:
                    nr += dr
                    nc += dc
                    continue
                if not found_screen:
                    found_screen = True  # 第一个子 = 炮架
                else:
                    if piece["type"] == "C" and piece["color"] != NEUTRAL:
                        return True
                    break  # 第二个子不是炮，此方向无威胁
                nr += dr
                nc += dc
        return False

    def _cannon_proximity_risk(self, r, c, max_dist=6, ignore_pos=None):
        """评估 (r,c) 是否靠近敌方炮线（同一直线，中间子数 ≤ 2，距离 ≤ max_dist）。
        返回风险值：0=安全, 1=一般风险, 2=较高风险
        ignore_pos: 模拟走子时忽略的原始位置（相当于该位置已空）。"""
        risk = 0
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            dist = 1
            between = 0
            while self.in_bounds(nr, nc) and dist <= max_dist:
                if ignore_pos and (nr, nc) == ignore_pos:
                    nr += dr
                    nc += dc
                    dist += 1
                    continue
                piece = self.board[nr][nc]
                if piece is not None:
                    if piece["type"] == "C" and piece["color"] != NEUTRAL:
                        if between <= 1:
                            risk = max(risk, 2)
                        elif between == 2:
                            risk = max(risk, 1)
                        break
                    else:
                        between += 1
                nr += dr
                nc += dc
                dist += 1
        return risk

    def _count_neutral_neighbors(self, r, c):
        """统计 (r,c) 周围8格内的友军数量"""
        count = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc):
                    p = self.board[nr][nc]
                    if p and p["color"] == NEUTRAL:
                        count += 1
        return count

    # ---- 帅的安全检测（全方位）----

    def _is_enemy_color(self, color1, color2):
        """判断 color2 是否是 color1 的敌方（组队模式考虑队友）"""
        if color1 == color2:
            return False
        if self.mode in ("team", "team_stratagem") and self.teams:
            return not self.is_same_team(color1, color2)
        return True

    def _is_square_attacked(self, r, c, own_color=None):
        """检查位置 (r,c) 是否被任何非中立棋子攻击。
        若 own_color 指定，只检查对手方（用于将军检测）。"""
        # 1. 正交方向：车(R)、炮(C)、将(K)、兵(P)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            found_screen = False
            while self.in_bounds(nr, nc):
                piece = self.board[nr][nc]
                if piece is None:
                    nr += dr; nc += dc; continue
                if piece["color"] == NEUTRAL:
                    break  # 中立单位挡住视线
                is_foe = own_color is None or self._is_enemy_color(own_color, piece["color"])
                dist = abs(nr - r) + abs(nc - c)
                if not found_screen:
                    if dist == 1:
                        if piece["type"] == "K" and is_foe:
                            return True  # 将/帅相邻
                        if piece["type"] == "P" and is_foe:
                            if (r, c) in self._pawn_moves(nr, nc, piece["color"]):
                                return True  # 兵能吃过来
                    if piece["type"] == "R" and is_foe:
                        return True  # 车直通
                    found_screen = True  # 成为炮架（己方子也可作炮架）
                else:
                    if piece["type"] == "C" and is_foe:
                        return True  # 炮隔一子
                    break  # 再多子就看不到了
                nr += dr; nc += dc

        # 2. 对角线方向：士(A)、象(B)
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc):
                piece = self.board[nr][nc]
                if piece and piece["color"] != NEUTRAL and piece["type"] == "A":
                    if own_color is None or self._is_enemy_color(own_color, piece["color"]):
                        return True  # 士一步斜吃
            nr2, nc2 = r + dr * 2, c + dc * 2
            if self.in_bounds(nr2, nc2):
                mid = self.board[r + dr][c + dc]
                if mid is None:  # 象眼没堵
                    piece = self.board[nr2][nc2]
                    if piece and piece["color"] != NEUTRAL and piece["type"] == "B":
                        if own_color is None or self._is_enemy_color(own_color, piece["color"]):
                            return True  # 象飞过来

        # 3. 马(N)脚：从目标反向查找
        knight_table = [
            (-2, -1, -1, 0), (-2, 1, -1, 0),
            (2, -1, 1, 0),   (2, 1, 1, 0),
            (-1, -2, 0, -1), (-1, 2, 0, 1),
            (1, -2, 0, -1),  (1, 2, 0, 1),
        ]
        for dr, dc, br, bc in knight_table:
            kr, kc = r - dr, c - dc  # 马的可能位置
            if not self.in_bounds(kr, kc): continue
            piece = self.board[kr][kc]
            if piece and piece["color"] != NEUTRAL and piece["type"] == "N":
                if own_color is None or self._is_enemy_color(own_color, piece["color"]):
                    lr, lc = kr + br, kc + bc  # 马脚位置
                    if self.in_bounds(lr, lc) and self.board[lr][lc] is None:
                        return True

        return False

    def _marshal_is_safe(self):
        """中立帅当前是否安全（不被任何棋子攻击）"""
        mr, mc = self._find_king(NEUTRAL)
        if mr is None:
            return True  # 帅已死，无所谓安全
        return not self._is_square_attacked(mr, mc)

    def _would_move_leave_marshal_in_check(self, fr, fc, tr, tc):
        """模拟走子后检查帅是否处于被攻击状态"""
        mr, mc = self._find_king(NEUTRAL)
        if mr is None:
            return False

        # 模拟
        old_from = self.board[fr][fc]
        old_to = self.board[tr][tc]
        self.board[tr][tc] = old_from
        self.board[fr][fc] = None

        # 如果移动的是帅，检查新位置；否则检查原位置
        if old_from and old_from["type"] == "K":
            in_check = self._is_square_attacked(tr, tc)
        else:
            in_check = self._is_square_attacked(mr, mc)

        # 恢复
        self.board[fr][fc] = old_from
        self.board[tr][tc] = old_to

        return in_check

    def _score_neutral_move(self, fr, fc, tr, tc):
        """对中立单位的走法进行评分，分值越高越好"""
        # ---- 0. 生死线：走子后帅不能处于危险中 ----
        marshal_in_danger_after = self._would_move_leave_marshal_in_check(fr, fc, tr, tc)
        if marshal_in_danger_after:
            return -10000  # 任何导致帅被将杀的走法都直接否决

        score = 0
        target = self.board[tr][tc]
        piece_type = self.board[fr][fc]["type"] if self.board[fr][fc] else None
        mr, mc = self._find_king(NEUTRAL) if self._find_king(NEUTRAL) else (None, None)
        marshal_under_attack = mr is not None and self._is_square_attacked(mr, mc)

        # ---- 1. 吃子 ----
        if target:
            score += 500
            if mr is not None:
                threat_dist = abs(tr - mr) + abs(tc - mc)
                score += max(0, 100 - threat_dist * 10)
            if target["type"] in ("R", "C"):
                score += 300  # 吃车/炮高价值
            elif target["type"] in ("N",):
                score += 150

        # ---- 2. 帅被攻击时：不惜代价救驾 ----
        if marshal_under_attack:
            # 2a. 吃子（任何吃子都可能解除威胁）
            if target:
                score += 2000
            # 2b. 将军：站在帅旁边挡路（针对车/炮直线攻击）
            if piece_type != "K" and not target:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (tr, tc) == (mr + dr, mc + dc):
                        score += 1500
                        break
            # 2c. 帅逃跑：走到不被攻击的位置
            if piece_type == "K" and not self._is_square_attacked(tr, tc):
                score += 1800
            # 2d. 士贴身护帅
            if piece_type == "A":
                if abs(tr - mr) + abs(tc - mc) <= 1:
                    score += 1000

        # ---- 3. 炮架威胁（已架好的炮） ----
        threats = self._find_cannon_threats() if mr is not None else []
        if threats and not marshal_under_attack:
            for cr, cc, sr, sc in threats:
                if target and target["type"] == "C" and tr == cr and tc == cc:
                    score += 1000
                if self._between(cr, cc, mr, mc, tr, tc) and self.board[tr][tc] is None:
                    if (tr, tc) != (sr, sc):
                        score += 800
                if piece_type == "K":
                    if tr != cr and tc != cc:
                        score += 600

        # ---- 3b. 炮位对准惩罚（炮已对齐但尚未构成直接威胁） ----
        if mr is not None and not marshal_under_attack:
            alignments = self._find_cannon_alignments()
            for cr, cc, between in alignments:
                was_between = self._between(cr, cc, mr, mc, fr, fc)
                now_between = self._between(cr, cc, mr, mc, tr, tc)

                if piece_type == "K":
                    # 帅避开炮线（移到不同行且不同列）
                    if tr != cr and tc != cc:
                        score += 200
                elif was_between and not now_between:
                    # 移走了炮和帅之间的棋子
                    # between是移走前的棋子数，包含当前棋子
                    if between <= 1:
                        score += 400  # 移走后中间0子，炮无法吃帅 -> 安全
                    elif between == 2:
                        score -= 200  # 移走后中间还有1子，炮仍可吃帅 -> 危险
                    else:
                        score += 80   # 移走后中间≥2子，炮无法吃 -> 安全
                elif not was_between and now_between and self.board[tr][tc] is None:
                    # 棋子进入炮和帅之间的直线
                    if between == 0:
                        score -= 500  # 进入后成为炮架，炮可直接吃帅 -> 危险
                    elif between == 1:
                        score += 400  # 进入后中间2子，炮无法吃帅 -> 安全
                    else:
                        score -= 100  # 进入后中间≥3子，需要更多棋子挡
                elif was_between and now_between and self.board[tr][tc] is None:
                    # 在屏障内平移，没有离开
                    score += 20

        # ---- 3c. 所有中立子免受炮击 ----
        if piece_type != "K":
            # 3c-i: 直接炮威胁（中间恰有1个炮架）
            is_self_threatened = self._is_neutral_under_cannon_threat(fr, fc)
            if is_self_threatened:
                if not self._is_neutral_under_cannon_threat(tr, tc, ignore_pos=(fr, fc)):
                    score += 700  # 逃离炮线
                else:
                    score -= 400  # 仍在炮线上
            else:
                if self._is_neutral_under_cannon_threat(tr, tc, ignore_pos=(fr, fc)):
                    score -= 500  # 主动走入炮线

            # 3c-ii: 炮线近距避让（炮在同一直线6格内，中间子数 ≤ 2，尚未构成直接威胁）
            near_risk = self._cannon_proximity_risk(fr, fc)
            target_risk = self._cannon_proximity_risk(tr, tc, ignore_pos=(fr, fc))
            if target_risk < near_risk:
                score += 150  # 远离炮线
            elif target_risk > near_risk:
                score -= 100  # 靠近炮线

        # ---- 4. 帅安全时：互相防御 + 反击 ----
        if not marshal_under_attack:
            # 计算敌人与帅的距离，用于缩放防守权重
            if mr is not None:
                nearest_enemy = self._find_nearest_enemy(mr, mc)
                enemy_dist = abs(nearest_enemy[0] - mr) + abs(nearest_enemy[1] - mc) if nearest_enemy else 99
            else:
                enemy_dist = 99
            # 防守紧迫度：敌人越近，防守权重越高 (1x-4x)
            def_scale = max(1, 4 - enemy_dist // 5) if enemy_dist < 99 else 1
            def_scale = min(def_scale, 4)

            # 4a. 互相防御：保持阵型（按敌情缩放）
            old_neighbors = self._count_neutral_neighbors(fr, fc)
            new_neighbors = self._count_neutral_neighbors(tr, tc)
            score += (new_neighbors - old_neighbors) * 20 * def_scale

            # 4b. 士贴身护帅（按敌情缩放）
            if piece_type == "A" and mr is not None:
                old_guard = abs(fr - mr) + abs(fc - mc)
                new_guard = abs(tr - mr) + abs(tc - mc)
                if new_guard <= 1:
                    score += 60 * def_scale
                elif new_guard < old_guard:
                    score += 30 * def_scale
                elif new_guard > old_guard and old_guard <= 1:
                    score -= 50 * def_scale  # 不要离开帅

            # 4c. 所有非帅棋子：靠近帅（防御姿态）
            if piece_type != "K" and mr is not None:
                old_kdist = abs(fr - mr) + abs(fc - mc)
                new_kdist = abs(tr - mr) + abs(tc - mc)
                if new_kdist < old_kdist:
                    score += 10 * def_scale  # 靠近帅
                elif new_kdist > old_kdist and old_kdist <= 3:
                    score -= 20 * def_scale  # 远离帅（尤其原本就在附近）

            # 4d. 兵主动出击（仅在敌人较近时）
            if piece_type == "P" and enemy_dist <= 10:
                enemy = self._find_nearest_enemy(tr, tc)
                if enemy:
                    old_ed = abs(fr - enemy[0]) + abs(fc - enemy[1])
                    new_ed = abs(tr - enemy[0]) + abs(tc - enemy[1])
                    if new_ed < old_ed:
                        score += 30
                    if target:
                        score += 200

            # 4e. 占据宫位/中立区中心（按敌情缩放）
            if piece_type in ("A", "P"):
                if self._in_palace(tr, tc):
                    score += 20 * def_scale
                elif self._in_neutral_zone(tr, tc):
                    score += 8 * def_scale
        else:
            # 帅受威胁但当前走法不是救驾走法 → 扣分
            if mr is not None:
                old_d = abs(fr - mr) + abs(fc - mc)
                new_d = abs(tr - mr) + abs(tc - mc)
                if new_d > old_d:
                    score -= 80  # 帅有难还远离 → 重罚
                elif new_d < old_d:
                    score += 30  # 靠近帅

        # ---- 5. 靠近最近敌人 ----
        enemy = self._find_nearest_enemy(tr, tc)
        if enemy:
            old_ed = abs(fr - enemy[0]) + abs(fc - enemy[1])
            new_ed = abs(tr - enemy[0]) + abs(tc - enemy[1])
            if new_ed < old_ed:
                score += 15

        return score

    def _between(self, r1, c1, r2, c2, pr, pc):
        """检查位置 (pr,pc) 是否在 (r1,c1) 和 (r2,c2) 的直线上且介于两者之间"""
        if r1 == r2 == pr:
            return min(c1, c2) < pc < max(c1, c2)
        if c1 == c2 == pc:
            return min(r1, r2) < pr < max(r1, r2)
        return False

    def get_neutral_ai_moves(self):
        """AI 决策：为每个中立单位选一个走法。返回 [(fr,fc,tr,tc), ...]"""
        if self._find_king(NEUTRAL) is None:
            return []  # 帅已死，中立单位全部消失

        # 收集所有候选走法及其评分
        all_candidates = []  # [(score, fr, fc, tr, tc)]
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if not p or p["color"] != NEUTRAL:
                    continue
                for tr, tc in self._neutral_pseudo_moves(r, c):
                    s = self._score_neutral_move(r, c, tr, tc)
                    all_candidates.append((s, r, c, tr, tc))

        # 按评分降序排列
        all_candidates.sort(key=lambda x: -x[0])

        # 贪心分配：高评分优先，每个棋子和目标位置只能使用一次
        selected = []
        used_pieces = set()   # 已经移动过的棋子
        used_targets = set()  # 已被占用的目标位置

        for s, fr, fc, tr, tc in all_candidates:
            if (fr, fc) in used_pieces:
                continue
            if (tr, tc) in used_targets:
                continue
            # 目标上有其它中立单位（当前轮次未移动的）
            target = self.board[tr][tc]
            if target and target["color"] == NEUTRAL:
                continue
            selected.append((fr, fc, tr, tc))
            used_pieces.add((fr, fc))
            used_targets.add((tr, tc))

        return selected

    def get_single_neutral_ai_move(self):
        """返回单个最佳中立走法 (fr,fc,tr,tc)，没有可行走法返回 None"""
        if self._find_king(NEUTRAL) is None:
            return None

        best = None
        best_score = -float("inf")  # 确保即使所有走法都送死也能选出一个
        for r in range(19):
            for c in range(19):
                p = self.board[r][c]
                if not p or p["color"] != NEUTRAL:
                    continue
                for tr, tc in self._neutral_pseudo_moves(r, c):
                    # 目标上有其它未移动的中立单位则跳过
                    target = self.board[tr][tc]
                    if target and target["color"] == NEUTRAL:
                        continue
                    s = self._score_neutral_move(r, c, tr, tc)
                    if s > best_score:
                        best_score = s
                        best = (r, c, tr, tc)
        return best

    def neutral_ai_needs_urgent_move(self):
        """检测是否需要紧急触发中立AI（帅被攻击或有炮对准）"""
        mr, mc = self._find_king(NEUTRAL)
        if mr is None:
            return False
        if self._is_square_attacked(mr, mc):
            return True
        if self._find_cannon_alignments():
            return True
        return False

    def remove_all_neutral(self):
        """清除棋盘上所有中立单位"""
        for r in range(19):
            for c in range(19):
                if self.board[r][c] and self.board[r][c]["color"] == NEUTRAL:
                    self.board[r][c] = None

    def apply_neutral_move(self, fr, fc, tr, tc):
        """执行单个中立单位的走子"""
        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None
        turn_num = len(self.move_history) + 1
        self.move_log.append((turn_num, NEUTRAL, fr, fc, tr, tc, False, "N", None))

    def undo_neutral_moves(self):
        """撤销上一回合的所有中立走子"""
        if self.last_neutral_moves:
            for nfr, nfc, ntr, ntc in reversed(self.last_neutral_moves):
                self.board[nfr][nfc] = self.board[ntr][ntc]
                self.board[ntr][ntc] = None
            self.last_neutral_moves = None

    # ---- AI 走子 ----
    def get_ai_move(self, color):
        """AI 走子决策：使用 ai_4p 模块的 Minimax 搜索"""
        from ai_4p import best_move as ai_best_move
        debug_info = {"scores": [], "chosen": None}
        move = ai_best_move(self, color, debug_out=debug_info)
        self.ai_debug_log.append((len(self.move_history), color, debug_info["scores"], debug_info["chosen"]))
        return move

    def write_ai_debug(self, filepath=None):
        """将完整走子记录 + AI 调试日志写入文件"""
        import datetime, os
        filepath = filepath or os.path.join(os.path.dirname(__file__), "ai_debug.log")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            # 输出全局走子记录
            f.write("\n-- 全局走子记录 --\n")
            for turn_num, color, fr, fc, tr, tc, is_ai, ptype, ctype in self.move_log:
                ai_tag = " (AI)" if is_ai else ""
                cap_tag = f" 吃{COLOR_NAMES.get(ctype, str(ctype))}[{ctype}]" if ctype else ""
                f.write(f"#{turn_num} {COLOR_NAMES.get(color, f'P{color}')}{ai_tag}: "
                        f"({fr},{fc})→({tr},{tc}) [{ptype}]{cap_tag}\n")
            # 输出 AI 思考细节
            if self.ai_debug_log:
                f.write("\n-- AI 思考细节 --\n")
                for turn, color, scores, chosen in self.ai_debug_log:
                    f.write(f"\n[Turn {turn}] {COLOR_NAMES.get(color, f'P{color}')} (AI)\n")
                    if scores:
                        for move, val in scores:
                            mark = " ◀ SELECTED" if move == chosen else ""
                            fr, fc, tr, tc = move
                            f.write(f"  ({fr},{fc})→({tr},{tc})  score={val:+.0f}{mark}\n")
                    f.write(f"  Chosen: ({chosen[0]},{chosen[1]})→({chosen[2]},{chosen[3]})\n" if chosen else "  Chosen: None\n")
            f.write(f"=== End ===\n")
        return filepath

    # ---- 走法生成（伪合法）----
    def _pseudo_moves(self, r, c, color):
        p = self.board[r][c]
        if not p:
            return []
        ptype = p["type"]
        props = PLAYER_PROPS[color]

        if ptype == "K":
            return self._king_moves(r, c, color)
        elif ptype == "A":
            return self._advisor_moves(r, c, color)
        elif ptype == "B":
            return self._bishop_moves(r, c, color)
        elif ptype == "N":
            return self._knight_moves(r, c)
        elif ptype == "R":
            return self._rook_moves(r, c)
        elif ptype == "C":
            return self._cannon_moves(r, c)
        elif ptype == "P":
            return self._pawn_moves(r, c, color)
        return []

    def _king_moves(self, r, c, color):
        moves = []
        props = PLAYER_PROPS[color]
        r1, r2, c1, c2 = props["palace"]
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if r1 <= nr <= r2 and c1 <= nc <= c2:
                moves.append((nr, nc))
        return moves

    def _advisor_moves(self, r, c, color):
        moves = []
        props = PLAYER_PROPS[color]
        r1, r2, c1, c2 = props["palace"]
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = r + dr, c + dc
            if r1 <= nr <= r2 and c1 <= nc <= c2:
                moves.append((nr, nc))
        return moves

    def _bishop_moves(self, r, c, color):
        moves = []
        props = PLAYER_PROPS[color]
        # 象不能过河
        for dr, dc, br, bc in [(-2, -2, -1, -1), (-2, 2, -1, 1),
                                (2, -2, 1, -1), (2, 2, 1, 1)]:
            nr, nc = r + dr, c + dc
            if not self.in_bounds(nr, nc):
                continue
            # 检查塞象眼
            if self.board[r + br][c + bc] is not None:
                continue
            # 检查过河
            if not self._same_half(nr, nc, color):
                continue
            moves.append((nr, nc))
        return moves

    def _same_half(self, r, c, color):
        """判断位置是否在己方半幅（象不能过河）"""
        props = PLAYER_PROPS[color]
        if color in (RED, BLACK):
            # 红方：row >= 14，黑方：row <= 4
            r1, r2, _, _ = props["palace"]
            # 简单规则：从己方九宫到河界
            if color == RED:
                return r >= 14  # Red's home half
            else:
                return r <= 4   # Black's home half
        else:
            if color == GREEN:
                return c <= 4   # Green's home half
            else:
                return c >= 14  # Blue's home half

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
            if not self.in_bounds(nr, nc):
                continue
            if self.board[r + br][c + bc] is not None:
                continue
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
        moves = []
        color = self.board[r][c]["color"]
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            screen = False
            while self.in_bounds(nr, nc):
                cell = self.board[nr][nc]
                if not screen:
                    if cell is None:
                        moves.append((nr, nc))
                    else:
                        screen = True
                else:
                    if cell is not None:
                        if cell["color"] != color:
                            moves.append((nr, nc))
                        break
                nr += dr
                nc += dc
        return moves

    def _pawn_moves(self, r, c, color):
        moves = []
        props = PLAYER_PROPS[color]
        dr, dc = props["forward"]
        nr, nc = r + dr, c + dc
        if self.in_bounds(nr, nc):
            moves.append((nr, nc))
        # 过河后可以横走
        crossed = props["river_check"](r if color in (RED, BLACK) else c)
        if crossed:
            # 横走两个方向
            if dr != 0:  # 垂直方向玩家，横走为col方向
                for dc2 in [-1, 1]:
                    nr2, nc2 = r, c + dc2
                    if self.in_bounds(nr2, nc2):
                        moves.append((nr2, nc2))
            else:  # 水平方向玩家，横走为row方向
                for dr2 in [-1, 1]:
                    nr2, nc2 = r + dr2, c
                    if self.in_bounds(nr2, nc2):
                        moves.append((nr2, nc2))
        return moves

    # ---- 胜负判断 ----
    def check_winner(self):
        """返回赢家列表，没有赢家返回空列表"""
        alive_colors = [c for c in TURN_ORDER if self.alive[c]]
        if len(alive_colors) <= 1:
            return alive_colors  # 只剩一个活着

        if self.mode == "team" and self.teams:
            # 按队伍分组
            team_groups = {}
            for c in TURN_ORDER:
                tid = self.teams.get(c, c)
                team_groups.setdefault(tid, []).append(c)
            # 检查是否有一队全灭
            for tid, colors in team_groups.items():
                alive_in_team = [c for c in colors if self.alive[c]]
                if not alive_in_team:
                    # 这队全灭，另一队获胜
                    others = [c for c in TURN_ORDER if c not in colors]
                    return [c for c in others if self.alive[c]]

        return []  # 还没结束

    def is_same_team(self, c1, c2):
        """组队模式下判断是否同一队"""
        if self.mode not in ("team", "team_stratagem") or not self.teams:
            return False
        tid1 = self.teams.get(c1, c1)
        tid2 = self.teams.get(c2, c2)
        return tid1 == tid2
