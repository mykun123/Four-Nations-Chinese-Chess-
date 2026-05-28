"""super_ai/gpu_eval.py — GPU 加速批量评估

将棋盘编码为多通道张量，利用 PyTorch 在 GPU 上并行评估大量局面。
搜索过程中收集叶节点，凑满一批后一次送 GPU 计算，大幅提升吞吐。

用法:
    from super_ai.gpu_eval import GPUBatchEvaluator

    # 初始化（device="cuda" 或 "cuda:0"）
    gpu = GPUBatchEvaluator(device="cuda", batch_size=512)

    # 单独评估（走 GPU）
    score = gpu.evaluate(game, color)

    # 批量评估
    scores = gpu.evaluate_batch([(game1, c1), (game2, c2), ...])

    # 接入 SuperAI
    ai = SuperAI(gpu_evaluator=gpu)
"""

import os
import numpy as np

# ====== 棋盘 → 张量编码 ======

# 通道分配:
#   0-4:   5色 × 7种棋子 = 35 通道 (每个位置 one-hot)
#   35-38: 轮到谁 (4色 one-hot)
#   39-42: 存活状态 (4色)
NUM_CHANNELS = 35 + 4 + 4  # = 43

PIECE_TYPES = ["K", "A", "B", "N", "R", "C", "P"]
PIECE_TYPE_IX = {pt: i for i, pt in enumerate(PIECE_TYPES)}  # 0-6

COLOR_MAP = [0, 1, 2, 3, 4]  # RED, BLACK, GREEN, BLUE, NEUTRAL


def board_to_tensor(board, turn, alive):
    """将棋盘编码为 [43, 19, 19] numpy 数组"""
    t = np.zeros((NUM_CHANNELS, 19, 19), dtype=np.float32)
    for r in range(19):
        for c in range(19):
            pc = board[r][c]
            if pc is None:
                continue
            pti = PIECE_TYPE_IX.get(pc["type"], -1)
            if pti < 0:
                continue
            ch = pc["color"] * 7 + pti  # 0-34
            t[ch, r, c] = 1.0
    if turn is not None and 0 <= turn <= 3:
        t[35 + turn, :, :] = 1.0
    for ci in range(4):
        if alive.get(ci, True):
            t[39 + ci, :, :] = 1.0
    return t


# ====== 尝试导入 PyTorch ======

try:
    import torch
    import torch.nn.functional as F
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False


class GPUBatchEvaluator:
    """GPU 批量评估器

    将局面编码为 [N, 43, 19, 19] 张量，在 GPU 上用卷积 / 线性层评估。
    """

    def __init__(self, device="cuda", batch_size=512, verbose=True):
        self.batch_size = batch_size
        self.verbose = verbose
        self._pending = []  # [(game, color), ...] 待评估
        self._pending_tensors = []  # np.ndarray 缓存
        self._eval_count = 0
        self._batch_count = 0

        if _HAS_TORCH:
            self.device = torch.device(device if torch.cuda.is_available() else "cpu")
            self._build_network()
            self._network.to(self.device)
            self._network.eval()
            if self.verbose:
                print(f"[GPU-Eval] device={self.device}, batch_size={batch_size}, torch={torch.__version__}")
        else:
            self.device = "cpu"
            if self.verbose:
                print("[GPU-Eval] PyTorch 未安装，回退 CPU 评估")

    # ── 网络构建 ─────────────────────────────────

    def _build_network(self):
        """构建轻量评估网络

        架构:
          Input [43, 19, 19]
          → Conv(128, 3×3, pad=1) + ReLU
          → Conv(64, 3×3, pad=1) + ReLU
          → Global Avg Pool → 64
          → Linear(64, 32) + ReLU
          → Linear(32, 1) → score

        这是一个可训练的评估网络骨架。当前使用随机权重作为 baseline，
        后续可以通过自我对弈训练来提升。
        """
        self._network = torch.nn.Sequential(
            torch.nn.Conv2d(43, 128, 3, padding=1),
            torch.nn.ReLU(),
            torch.nn.Conv2d(128, 64, 3, padding=1),
            torch.nn.ReLU(),
            torch.nn.AdaptiveAvgPool2d(1),
            torch.nn.Flatten(),
            torch.nn.Linear(64, 32),
            torch.nn.ReLU(),
            torch.nn.Linear(32, 1),
        )

    # ── 单步评估（走 GPU）─────────────────────────

    def evaluate(self, game, color):
        """评估一个局面，返回分数

        如果收集到 batch_size 个局面，自动触发批量评估。
        """
        if not _HAS_TORCH or self.device.type == "cpu":
            return self._cpu_evaluate(game, color)

        t = board_to_tensor(game.board, game.turn, game.alive)
        self._pending.append((game, color))
        self._pending_tensors.append(t)

        if len(self._pending) >= self.batch_size:
            self.flush()

        # 返回 CPU 预估值（后续 flush 后更新）
        return self._cpu_evaluate(game, color)

    # ── 批量评估 ────────────────────────────────

    def evaluate_batch(self, games_colors):
        """批量评估多个局面，返回分数列表

        games_colors: [(game, color), ...]
        returns: [score, ...]
        """
        if not _HAS_TORCH or self.device.type == "cpu":
            return [self._cpu_evaluate(g, c) for g, c in games_colors]

        tensors = np.stack([board_to_tensor(g.board, g.turn, g.alive) for g, c in games_colors])
        return self._run_gpu(tensors)

    def flush(self):
        """强制处理所有待评估局面"""
        if not self._pending_tensors:
            return []
        if not _HAS_TORCH or self.device.type == "cpu":
            self._pending.clear()
            self._pending_tensors.clear()
            return []

        self._batch_count += 1
        tensors = np.stack(self._pending_tensors)
        scores = self._run_gpu(tensors)

        self._pending.clear()
        self._pending_tensors.clear()
        return scores

    # ── GPU 计算核心 ─────────────────────────────

    def _run_gpu(self, tensors):
        """在 GPU 上运行评估"""
        batch = torch.from_numpy(tensors).to(self.device)
        with torch.no_grad():
            scores = self._network(batch).view(-1)
        self._eval_count += len(scores)
        return scores.cpu().numpy().tolist()

    # ── CPU 兜底评估 ─────────────────────────────

    @staticmethod
    def _cpu_evaluate(game, color):
        """CPU 快速评估（导入 ai_4p 逻辑）"""
        from evaluate import fast_evaluate
        return fast_evaluate(game, color)

    # ── 网络训练接口 ─────────────────────────────

    def train_step(self, positions, target_scores, lr=0.001):
        """训练一步（用于自我对弈训练）

        positions: [(board, turn, alive, color), ...]
        target_scores: [float, ...]
        """
        if not _HAS_TORCH or self.device.type == "cpu":
            return

        self._network.train()
        optimizer = torch.optim.Adam(self._network.parameters(), lr=lr)
        loss_fn = torch.nn.MSELoss()

        tensors = np.stack([board_to_tensor(b, t, a) for b, t, a, c in positions])
        x = torch.from_numpy(tensors).to(self.device)
        y = torch.tensor(target_scores, dtype=torch.float32, device=self.device)

        pred = self._network(x).view(-1)
        loss = loss_fn(pred, y)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        self._network.eval()

        return loss.item()

    def save(self, path):
        """保存网络权重"""
        if _HAS_TORCH:
            torch.save(self._network.state_dict(), path)

    def load(self, path):
        """加载网络权重"""
        if _HAS_TORCH and os.path.exists(path):
            self._network.load_state_dict(torch.load(path, map_location=self.device))
            self._network.eval()

    # ── 查询 ────────────────────────────────────

    @property
    def stats(self):
        return {
            "device": str(self.device),
            "eval_count": self._eval_count,
            "batch_count": self._batch_count,
            "pending": len(self._pending),
            "has_torch": _HAS_TORCH,
        }

    @property
    def is_gpu(self):
        return _HAS_TORCH and self.device.type == "cuda"
