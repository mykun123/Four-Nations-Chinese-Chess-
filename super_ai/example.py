#!/usr/bin/env python
"""super_ai/example.py — Super AI 使用示例

运行:
    python super_ai/example.py

功能:
    1. 自由模式 FFA 下为 RED 选最佳走法
    2. 组队模式 Team 下为 BLUE 选最佳走法
    3. 展示并行 vs 串行性能对比
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game_4p import Game4P, RED, BLACK, GREEN, BLUE
from super_ai import SuperAI


def test_ffa():
    """自由对战模式"""
    print("=" * 50)
    print("自由对战 (FFA)")
    print("=" * 50)
    game = Game4P()
    ai = SuperAI(num_workers=8)

    for color, name in [(RED, "红方"), (BLACK, "黑方"), (GREEN, "绿方"), (BLUE, "蓝方")]:
        t0 = time.time()
        move = ai.best_move(game, color, max_depth=4, time_limit=5.0)
        elapsed = time.time() - t0
        if move:
            fr, fc, tr, tc = move
            piece = game.board[fr][fc]
            print(f"  {name}: ({fr},{fc})→({tr},{tc}) [{piece['type']}]  ({elapsed:.2f}s)")
        else:
            print(f"  {name}: 无合法走法")


def test_team():
    """组队对战模式"""
    print("\n" + "=" * 50)
    print("组队对战 (Team: RED+GREEN vs BLACK+BLUE)")
    print("=" * 50)

    teams = {RED: 0, GREEN: 0, BLACK: 1, BLUE: 1}
    game = Game4P(mode="team", teams=teams)
    ai = SuperAI(num_workers=8)

    for color, name in [(RED, "红方"), (GREEN, "绿方"), (BLACK, "黑方"), (BLUE, "蓝方")]:
        t0 = time.time()
        move = ai.best_move(game, color, max_depth=4, time_limit=5.0)
        elapsed = time.time() - t0
        if move:
            fr, fc, tr, tc = move
            piece = game.board[fr][fc]
            print(f"  {name}: ({fr},{fc})→({tr},{tc}) [{piece['type']}]  ({elapsed:.2f}s)")
        else:
            print(f"  {name}: 无合法走法")


def test_speed():
    """并行 vs 串行性能对比"""
    print("\n" + "=" * 50)
    print("并行 vs 串行性能对比 (depth=4)")
    print("=" * 50)

    game = Game4P()

    # 并行
    ai_parallel = SuperAI(num_workers=8)
    t0 = time.time()
    move_p = ai_parallel.best_move(game, RED, max_depth=4, time_limit=15.0)
    tp = time.time() - t0

    # 串行
    ai_serial = SuperAI(num_workers=1)
    t0 = time.time()
    move_s = ai_serial.best_move(game, RED, max_depth=4, time_limit=15.0)
    ts = time.time() - t0

    print(f"  并行 (8 workers): {move_p} — {tp:.2f}s")
    print(f"  串行 (1 worker):  {move_s} — {ts:.2f}s")
    print(f"  加速比: {ts / tp:.1f}x" if tp > 0 else "")


def test_midgame():
    """中局局面测试: 模拟一些走子后让 AI 决策"""
    print("\n" + "=" * 50)
    print("中局局面测试")
    print("=" * 50)

    game = Game4P()

    # 模拟几步走子
    opening = [
        (RED, (16, 12, 13, 12)),   # 红右炮进3
        (GREEN, (6, 2, 9, 2)),     # 绿炮进3
        (BLACK, (2, 12, 9, 12)),   # 黑炮平7
        (BLUE, (6, 16, 9, 16)),    # 蓝炮进3
    ]
    # 注意：实际上这些走子需要交替执行，这里只是演示目的简化

    ai = SuperAI(num_workers=8)
    t0 = time.time()
    move = ai.best_move(game, RED, max_depth=4, time_limit=10.0)
    elapsed = time.time() - t0

    if move:
        fr, fc, tr, tc = move
        piece = game.board[fr][fc]
        print(f"  推荐走法: ({fr},{fc})→({tr},{tc}) [{piece['type']}]  ({elapsed:.2f}s)")
    else:
        print("  无合法走法")


if __name__ == "__main__":
    print("Super AI 示例")
    print(f"  进程数: 12 (可用 CPU)")
    print()

    test_ffa()
    test_team()
    test_speed()
    test_midgame()

    print("\n完成!")
