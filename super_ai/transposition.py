# super_ai/transposition.py — 转置表（Zobrist 哈希）
import random
from game_4p import NEUTRAL, TURN_ORDER

# 转置表条目标记
EXACT = 0  # 精确值
ALPHA = 1  # 下限（fail-low）
BETA = 2   # 上限（fail-high）

PIECE_TYPES = [None, "K", "A", "B", "N", "R", "C", "P"]
COLORS = [0, 1, 2, 3, 4]  # RED, BLACK, GREEN, BLUE, NEUTRAL

# Zobrist 随机数表
_zobrist_piece = {}   # (r, c, color, type) -> random int
_zobrist_turn = {}    # whose turn -> random int
_zobrist_alive = {}   # (color, alive) -> random int
_zobrist_mode = {}    # mode -> random int

_initialized = False


def _init_zobrist():
    global _initialized
    if _initialized:
        return
    rng = random.Random(0x4F81EB)  # 固定种子，保证可重复
    for r in range(19):
        for c in range(19):
            for color in COLORS:
                for pt in PIECE_TYPES:
                    if pt is not None:
                        _zobrist_piece[(r, c, color, pt)] = rng.getrandbits(64)
    for color in COLORS:
        _zobrist_turn[color] = rng.getrandbits(64)
        _zobrist_alive[(color, True)] = rng.getrandbits(64)
        _zobrist_alive[(color, False)] = rng.getrandbits(64)
    for mode in ("ffa", "team", "team_stratagem"):
        _zobrist_mode[mode] = rng.getrandbits(64)
    _initialized = True


def compute_hash(game):
    """计算当前棋盘的 Zobrist 哈希值（64位整数）"""
    _init_zobrist()
    h = 0
    for r in range(19):
        for c in range(19):
            pc = game.board[r][c]
            if pc:
                key = (r, c, pc["color"], pc["type"])
                h ^= _zobrist_piece.get(key, 0)
    h ^= _zobrist_turn.get(game.turn, 0)
    for color in TURN_ORDER:
        h ^= _zobrist_alive.get((color, game.alive.get(color, True)), 0)
    h ^= _zobrist_mode.get(game.mode, 0)
    return h


class TranspositionTable:
    """转置表：缓存已评估过的局面及其最佳走法"""

    def __init__(self, max_size=5000000):
        self.max_size = max_size
        self.table = {}  # hash -> entry
        self.age = 0

    def clear(self):
        self.table.clear()

    def age_cycle(self):
        """每次迭代加深调用，逐渐淘汰旧条目"""
        self.age += 1
        if len(self.table) > self.max_size:
            # 删除最旧的一半条目（age 小于当前 age-2 的）
            cutoff = self.age - 2
            to_del = [k for k, v in self.table.items() if v.get("age", 0) < cutoff]
            for k in to_del:
                del self.table[k]

    def store(self, hash_val, depth, score, flag, best_move=None, ply=0):
        """存入条目"""
        if hash_val == 0:
            return
        entry = {
            "depth": depth,
            "score": score,
            "flag": flag,
            "best_move": best_move,
            "age": self.age,
            "ply": ply,
        }
        # 已存在且深度更大时不覆盖
        existing = self.table.get(hash_val)
        if existing and existing["depth"] > depth:
            return
        self.table[hash_val] = entry

    def lookup(self, hash_val):
        """查询，返回条目或 None"""
        return self.table.get(hash_val)

    def get_best_move(self, hash_val):
        """获取缓存的 best_move（用于走法排序）"""
        entry = self.table.get(hash_val)
        if entry:
            return entry.get("best_move")
        return None

    @property
    def size(self):
        return len(self.table)
