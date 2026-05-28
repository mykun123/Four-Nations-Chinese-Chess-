"""super_ai/move_order.py — 走法排序（历史启发 + 杀手走法 + MVV-LVA）"""

from game_4p import PIECE_VALUES

HISTORY_MAX = 1 << 30


class HistoryHeuristic:
    """历史启发表：记录走法在剪枝中的成功次数"""

    def __init__(self):
        # history[from_r][from_c][to_r][to_c] = 分数
        self.table = [[[[0] * 19 for _ in range(19)] for _ in range(19)] for _ in range(19)]
        self.max_score = 0

    def record(self, fr, fc, tr, tc, depth):
        """记录一次成功的剪枝"""
        bonus = depth * depth
        self.table[fr][fc][tr][tc] += bonus
        if self.table[fr][fc][tr][tc] > HISTORY_MAX:
            # 防溢出：所有值减半
            for a in range(19):
                for b in range(19):
                    for c in range(19):
                        for d in range(19):
                            self.table[a][b][c][d] //= 2
        self.max_score = max(self.max_score, self.table[fr][fc][tr][tc])

    def get(self, fr, fc, tr, tc):
        return self.table[fr][fc][tr][tc]

    def clear(self):
        for a in range(19):
            for b in range(19):
                for c in range(19):
                    for d in range(19):
                        self.table[a][b][c][d] = 0
        self.max_score = 0


class KillerMoves:
    """杀手走法：每层最多2个非吃子走法，用于剪枝"""

    def __init__(self, max_depth=32):
        self.killers = [[None, None] for _ in range(max_depth)]

    def record(self, move, ply):
        if ply < len(self.killers):
            # 不重复
            if move == self.killers[ply][0]:
                return
            self.killers[ply][1] = self.killers[ply][0]
            self.killers[ply][0] = move

    def get(self, ply):
        if ply < len(self.killers):
            return [m for m in self.killers[ply] if m is not None]
        return []

    def clear(self):
        self.killers = [[None, None] for _ in range(32)]


def order_moves(moves, game, current_color, ply=0,
                history=None, killers=None, tt_best=None):
    """综合排序：转置表最佳 > 吃子(MVV-LVA) > 杀手 > 历史分数

    返回排序后的 moves（原地修改）
    """
    def key(m):
        fr, fc, tr, tc = m
        score = 0
        target = game.board[tr][tc]

        # 转置表最佳走法最高优先级
        if tt_best and m == tt_best:
            return 100000000

        # 吃子走法：MVV-LVA
        if target:
            attacker = game.board[fr][fc]
            tv = PIECE_VALUES.get(target["type"], 0)
            av = PIECE_VALUES.get(attacker["type"], 0) if attacker else 0
            score = tv * 100 - av  # MVV-LVA

        # 杀手走法（非吃子）
        if not target and killers:
            for i, k in enumerate(killers.get(ply) if hasattr(killers, 'get') else []):
                if m == k:
                    score = 5000 - i * 1000  # 第一杀手 > 第二杀手
                    break

        # 历史分数
        if history and not target:
            hist = history.get(fr, fc, tr, tc)
            if hist > 0:
                # 归一化到 [0, 3000]
                max_h = max(1, history.max_score)
                score += int(hist / max_h * 3000)

        return score

    moves.sort(key=key, reverse=True)
    return moves
