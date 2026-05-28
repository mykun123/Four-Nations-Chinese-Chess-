"""super_ai/search.py — 并行搜索引擎

架构：
  1. 根节点并行：每步走法分配到独立 CPU 进程
  2. 迭代加深：逐步加深搜索，利用浅层结果为深层排序
  3. Alpha-Beta 剪枝 + Zobrist 转置表
  4. 历史启发 + 杀手走法 + MVV-LVA 排序
  5. 空着剪枝（Null Move Pruning）
  6. 静态搜索（Quiescence Search）
"""

import random
import time
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

from game_4p import (
    RED, BLACK, GREEN, BLUE, NEUTRAL,
    TURN_ORDER, PIECE_VALUES,
)

from config import (
    MAX_ROOT_MOVES, MAX_AI_MOVES, MAX_OPP_MOVES,
    MAX_Q_DEPTH, DEFAULT_DEPTH, DESPERATION_THRESHOLD,
    NULL_MOVE_DEPTH_REDUCTION, NULL_MOVE_MIN_DEPTH,
)
from transposition import TranspositionTable, EXACT, ALPHA, BETA, compute_hash
from move_order import HistoryHeuristic, KillerMoves, order_moves
from evaluate import fast_evaluate, _is_ally_of, _is_enemy_of


# ====== 工具函数 ======

def _serialize(game):
    """将 Game4P 序列化为 bytes（用于跨进程传递）"""
    return pickle.dumps(game, protocol=pickle.HIGHEST_PROTOCOL)


def _deserialize(data):
    """反序列化 Game4P"""
    return pickle.loads(data)


def _next_player_after(game, color):
    """返回 color 后的下一个存活玩家"""
    try:
        idx = game.turn_order.index(color)
    except ValueError:
        return game.turn_order[0]
    for i in range(1, 5):
        nxt = game.turn_order[(idx + i) % 4]
        if game.alive.get(nxt, True):
            return nxt
    return color


def _team_alive_check(game, ai_color):
    """组队模式下检查己方队伍是否还有活着的玩家"""
    if game.mode in ("team", "team_stratagem") and game.teams:
        return any(
            game.alive.get(c, True) and _is_ally_of(game, ai_color, c)
            for c in TURN_ORDER
        )
    return game.alive.get(ai_color, True)


# ====== 并行工作函数（顶层函数，确保可 pickle） ======

def _worker_evaluate_move(serialized_game, ai_color, move, depth, next_player,
                          tt_max_size, eval_fn=None):
    """工作进程：评估一个根节点走法的优劣

    返回 (move, score)
    """
    game = _deserialize(serialized_game)
    tt = TranspositionTable(max_size=tt_max_size)
    history = HistoryHeuristic()
    killers = KillerMoves()

    # 执行走子
    cap, killed = _apply_move_simple(game, move)
    if cap and cap["type"] == "K":
        # 吃王额外奖励
        base_score = 50000
    else:
        base_score = 0

    score = _minimax(
        game, ai_color, next_player, depth - 1,
        float("-inf"), float("inf"),
        tt, history, killers, ply=1, eval_fn=eval_fn,
    )
    score += base_score

    # 悔棋
    _undo_move_simple(game, move, cap, killed)

    return move, score


def _apply_move_simple(game, move):
    """轻量走子（不保存历史）"""
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


def _undo_move_simple(game, move, captured, killed):
    """撤销轻量走子"""
    fr, fc, tr, tc = move
    for rr, cc, p in killed:
        game.board[rr][cc] = p
    if killed:
        game.alive[killed[0][2]["color"]] = True
    game.board[fr][fc] = game.board[tr][tc]
    game.board[tr][tc] = captured


# ====== 内部搜索 ======

def _quiescence(game, ai_color, current_color, alpha, beta, qdepth,
                tt, history, killers, ply=0, eval_fn=None):
    """静态搜索：只搜吃子走法，解决水平线效应"""
    if eval_fn is None:
        eval_fn = fast_evaluate
    stand_pat = eval_fn(game, ai_color)

    is_ally = current_color == ai_color or _is_ally_of(game, ai_color, current_color)

    # Stand-pat 剪枝
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

    # 胜负判定
    if not _team_alive_check(game, ai_color):
        return -99999
    winners = game.check_winner()
    if ai_color in winners:
        return 99999
    if game.mode in ("team", "team_stratagem") and game.teams and winners:
        for w in winners:
            if _is_ally_of(game, ai_color, w):
                return 99999

    if not game.alive.get(current_color, True):
        nxt = _next_player_after(game, current_color)
        return _quiescence(game, ai_color, nxt, alpha, beta, qdepth,
                          tt, history, killers, ply, eval_fn)

    moves = game.get_legal_moves(current_color)
    # 只保留吃子走法
    captures = []
    for m in moves:
        fr, fc, tr, tc = m
        tgt = game.board[tr][tc]
        if tgt and tgt["color"] != current_color:
            if _is_ally_of(game, ai_color, tgt["color"]):
                continue
            captures.append(m)

    if not captures:
        return stand_pat

    # MVV-LVA 排序
    def cap_key(m):
        tgt = game.board[m[2]][m[3]]
        atk = game.board[m[0]][m[1]]
        return PIECE_VALUES.get(tgt["type"], 0) * 10 - PIECE_VALUES.get(atk["type"], 0)
    captures.sort(key=cap_key, reverse=True)

    nxt = _next_player_after(game, current_color)

    if is_ally:
        best = alpha
        for move in captures[:3]:  # 最多搜3个吃子
            cap, killed = _apply_move_simple(game, move)
            val = _quiescence(game, ai_color, nxt, alpha, beta, qdepth - 1,
                             tt, history, killers, ply + 1, eval_fn)
            _undo_move_simple(game, move, cap, killed)
            if val > best:
                best = val
            alpha = max(alpha, val)
            if alpha >= beta:
                break
        return best
    else:
        best = beta
        for move in captures[:3]:
            cap, killed = _apply_move_simple(game, move)
            val = _quiescence(game, ai_color, nxt, alpha, beta, qdepth - 1,
                             tt, history, killers, ply + 1, eval_fn)
            _undo_move_simple(game, move, cap, killed)
            if val < best:
                best = val
            beta = min(beta, val)
            if alpha >= beta:
                break
        return best


def _minimax(game, ai_color, current_color, depth, alpha, beta,
             tt, history, killers, ply=0, eval_fn=None):
    """核心搜索：Alpha-Beta + 转置表 + 空着剪枝"""

    # 转置表查询
    board_hash = compute_hash(game)
    tt_entry = tt.lookup(board_hash)
    if tt_entry and tt_entry["depth"] >= depth:
        if tt_entry["flag"] == EXACT:
            return tt_entry["score"]
        elif tt_entry["flag"] == BETA and tt_entry["score"] >= beta:
            return tt_entry["score"]
        elif tt_entry["flag"] == ALPHA and tt_entry["score"] <= alpha:
            return tt_entry["score"]

    if depth <= 0:
        val = _quiescence(game, ai_color, current_color, alpha, beta,
                         MAX_Q_DEPTH, tt, history, killers, ply, eval_fn)
        return val

    # 胜负判定
    if not _team_alive_check(game, ai_color):
        return -99999 + (8 - depth)
    winners = game.check_winner()
    if ai_color in winners:
        return 99999 - (8 - depth)
    if game.mode in ("team", "team_stratagem") and game.teams and winners:
        for w in winners:
            if _is_ally_of(game, ai_color, w):
                return 99999 - (8 - depth)
    if winners:
        return -99999

    if not game.alive.get(current_color, True):
        nxt = _next_player_after(game, current_color)
        return _minimax(game, ai_color, nxt, depth, alpha, beta,
                       tt, history, killers, ply, eval_fn)

    moves = game.get_legal_moves(current_color)
    if not moves:
        nxt = _next_player_after(game, current_color)
        return _minimax(game, ai_color, nxt, depth, alpha, beta,
                       tt, history, killers, ply, eval_fn)

    # 空着剪枝（Null Move Pruning）
    is_ally = current_color == ai_color or _is_ally_of(game, ai_color, current_color)
    if is_ally and depth >= NULL_MOVE_MIN_DEPTH:
        king_pos = game._find_king(current_color)
        if king_pos and not game._is_square_attacked(king_pos[0], king_pos[1], own_color=current_color):
            # 尝试空着：让对手走一步，看是否仍能到达 beta
            nxt = _next_player_after(game, current_color)
            val = -_minimax(game, ai_color, nxt, depth - 1 - NULL_MOVE_DEPTH_REDUCTION,
                           -beta, -beta + 1, tt, history, killers, ply + 1, eval_fn)
            if val >= beta:
                return beta

    # 走法排序
    tt_best_move = tt.get_best_move(board_hash)
    order_moves(moves, game, current_color, ply, history, killers, tt_best_move)

    is_ally = current_color == ai_color or _is_ally_of(game, ai_color, current_color)
    top_n = MAX_AI_MOVES if is_ally else MAX_OPP_MOVES
    moves = moves[:top_n]
    nxt = _next_player_after(game, current_color)

    best_score = float("-inf") if is_ally else float("inf")
    best_move = None
    flag = ALPHA if is_ally else BETA
    original_alpha = alpha

    if is_ally:
        # MAX 节点
        for move in moves:
            cap, killed = _apply_move_simple(game, move)
            val = _minimax(game, ai_color, nxt, depth - 1, alpha, beta,
                          tt, history, killers, ply + 1, eval_fn)
            _undo_move_simple(game, move, cap, killed)

            if val > best_score:
                best_score = val
                best_move = move
            alpha = max(alpha, val)
            if alpha >= beta:
                # Beta 剪枝：记录杀手走法和历史
                if not cap:
                    killers.record(move, ply)
                    if ply > 0 and depth > 1:
                        history.record(move[0], move[1], move[2], move[3], depth)
                flag = BETA
                break
    else:
        # MIN 节点
        for move in moves:
            cap, killed = _apply_move_simple(game, move)
            val = _minimax(game, ai_color, nxt, depth - 1, alpha, beta,
                          tt, history, killers, ply + 1, eval_fn)
            _undo_move_simple(game, move, cap, killed)

            if val < best_score:
                best_score = val
                best_move = move
            beta = min(beta, val)
            if beta <= alpha:
                if not cap:
                    killers.record(move, ply)
                    if ply > 0 and depth > 1:
                        history.record(move[0], move[1], move[2], move[3], depth)
                flag = ALPHA
                break

    if best_score >= beta:
        flag = BETA
    elif best_score <= original_alpha:
        flag = ALPHA
    else:
        flag = EXACT

    # 存入转置表
    tt.store(board_hash, depth, best_score, flag, best_move, ply)

    return best_score


# ====== 并行搜索入口 ======

class SuperAI:
    """高性能四国象棋 AI

    用法:
        ai = SuperAI(num_workers=8)
        move = ai.best_move(game, color)
    """

    def __init__(self, num_workers=None, tt_size=2000000, eval_fn=None):
        self.num_workers = num_workers or min(12, 8)
        self.tt_size = tt_size
        self.eval_fn = eval_fn
        self.tt = TranspositionTable(max_size=tt_size)
        self.history = HistoryHeuristic()
        self.killers = KillerMoves()

    def best_move(self, game, color, max_depth=DEFAULT_DEPTH, time_limit=15.0, eval_fn=None):
        """返回最佳走法 (fr, fc, tr, tc) 或 None

        参数:
            game: Game4P 实例
            color: 玩家颜色 (RED/BLACK/GREEN/BLUE)
            max_depth: 最大搜索深度
            time_limit: 搜索时间上限（秒）
        """
        eval_fn = eval_fn or self.eval_fn

        moves = game.get_legal_moves(color)
        if not moves:
            return None

        if not _team_alive_check(game, color):
            return None

        # 序列化游戏状态（跨进程传递）
        game_data = _serialize(game)

        # 走法排序（根节点）
        board_hash = compute_hash(game)
        tt_best = self.tt.get_best_move(board_hash)
        order_moves(moves, game, color, tt_best=tt_best)
        top_moves = moves[:MAX_ROOT_MOVES]

        if len(top_moves) == 1:
            return top_moves[0]

        nxt = _next_player_after(game, color)

        best_move = top_moves[0]
        start_time = time.time()

        # 迭代加深
        for depth in range(2, max_depth + 1):
            elapsed = time.time() - start_time
            if elapsed > time_limit:
                break

            try:
                # 并行评估每个根节点走法
                move_scores = self._parallel_root_search(
                    game_data, color, top_moves, depth, nxt,
                    time_limit - elapsed, eval_fn=eval_fn,
                )
            except Exception:
                move_scores = []

            if not move_scores:
                continue

            # 选择最佳走法
            move_scores.sort(key=lambda x: -x[1])
            best_val = move_scores[0][1]
            best_list = [m for m, s in move_scores if abs(s - best_val) < 5]
            if not best_list:
                best_list = [move_scores[0][0]]
            best_move = random.choice(best_list)

            # 转置表存根节点结果（用于下一轮迭代）
            if best_list:
                self.tt.store(board_hash, depth, best_val, EXACT, best_list[0])

            # 更新历史启发表
            for m, s in move_scores:
                if s >= best_val - 5:
                    self.history.record(m[0], m[1], m[2], m[3], depth)

            # 如果已超时，停止加深
            if time.time() - start_time > time_limit * 0.8:
                break

            # 如果搜索时间还很充裕，继续加深
            iteration_time = time.time() - start_time - elapsed
            if iteration_time * 3 > (time_limit - elapsed):
                break  # 预估下次来不及

        return best_move

    def _parallel_root_search(self, game_data, color, moves, depth, nxt,
                               time_left, eval_fn=None):
        """并行搜索根节点走法

        使用 ProcessPoolExecutor 在多个 CPU 上同时评估不同走法
        """
        results = []

        if eval_fn is not None:
            n_workers = 1  # GPU evaluator 不可跨进程序列化
        else:
            n_workers = min(self.num_workers, len(moves))

        if n_workers <= 1 or len(moves) <= 1:
            # 单线程回退
            game = _deserialize(game_data)
            for move in moves:
                cap, killed = _apply_move_simple(game, move)
                val = _minimax(game, color, nxt, depth - 1,
                              float("-inf"), float("inf"),
                              self.tt, self.history, self.killers, ply=1,
                              eval_fn=eval_fn)
                if cap and cap["type"] == "K":
                    val += 50000
                _undo_move_simple(game, move, cap, killed)
                results.append((move, val))
            return results

        try:
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = {}
                for move in moves:
                    fut = executor.submit(
                        _worker_evaluate_move,
                        game_data, color, move, depth, nxt,
                        self.tt_size // len(moves),
                        eval_fn,
                    )
                    futures[fut] = move

                for fut in as_completed(futures):
                    try:
                        move, score = fut.result(timeout=max(5, time_left))
                        results.append((move, score))
                    except Exception:
                        # 某个进程出错，分配替罪羊分数
                        move = futures[fut]
                        results.append((move, -99999))

            # 按原始走法顺序返回
            results.sort(key=lambda x: moves.index(x[0]))
            return results

        except Exception:
            # ProcessPoolExecutor 失败（如 Windows 兼容问题），回退单线程
            game = _deserialize(game_data)
            for move in moves:
                cap, killed = _apply_move_simple(game, move)
                val = _minimax(game, color, nxt, depth - 1,
                              float("-inf"), float("inf"),
                              self.tt, self.history, self.killers, ply=1,
                              eval_fn=eval_fn)
                if cap and cap["type"] == "K":
                    val += 50000
                _undo_move_simple(game, move, cap, killed)
                results.append((move, val))
            return results

    def clear_cache(self):
        """清空转置表和历史记录"""
        self.tt.clear()
        self.history.clear()
        self.killers.clear()
