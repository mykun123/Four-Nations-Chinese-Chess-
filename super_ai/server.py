"""super_ai/server.py — SuperAI HTTP API 服务

在服务器上独立运行，通过 Flask 暴露 API，供主游戏服务器调用。

启动:
    python server.py --port 5000 --workers 8

调用示例 (主游戏服务器端):
    import requests
    resp = requests.post("http://192.168.163.190:5000/api/best_move", json={
        "board": board_2d_list,   # 19×19, 每格 {"type":"K","color":0} 或 None
        "turn": 0,                # 当前轮到谁 0-3
        "alive": [True]*4,        # 四家存活状态
        "mode": "ffa",            # ffa / team / team_stratagem
        "teams": {},              # 组队映射 {0:0, 1:1, 2:0, 3:1}
        "color": 0,               # AI 执哪家
        "max_depth": 6,           # 可选，默认 8
        "time_limit": 10.0,       # 可选，默认 15
    })
    data = resp.json()
    # data == {"move": [16,12,13,12], "score": 1250, "depth": 6, "time": 3.5}
"""

import sys
import os
import time
import argparse
import traceback

# 将自身目录加入 sys.path，确保直接导入生效
_self_dir = os.path.dirname(__file__)
if _self_dir not in sys.path:
    sys.path.insert(0, _self_dir)

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("[SuperAI-Server] 请先安装 Flask: pip install flask")
    sys.exit(1)

from game_4p import (
    Game4P, RED, BLACK, GREEN, BLUE, NEUTRAL,
    TURN_ORDER, in_blank,
)
from search import SuperAI

# ====== 全局 AI 实例 ======
ai_instance = None


def _make_game_from_state(state):
    """从 API 请求的 state 重建 Game4P 实例"""
    game = Game4P()
    game.mode = state.get("mode", "ffa")
    game.teams = state.get("teams", {})

    # 重建 board
    raw = state["board"]
    for r in range(19):
        for c in range(19):
            cell = raw[r][c]
            if cell is None:
                game.board[r][c] = None
            else:
                game.board[r][c] = {
                    "type": cell["type"],
                    "color": cell["color"],
                }

    # 重建存活状态
    alive = state.get("alive", [True, True, True, True])
    for i, a in enumerate(alive):
        game.alive[i] = a

    # 重建 turn：找到颜色在 turn_order 中的索引
    turn_color = state.get("turn", 0)
    try:
        game.turn_idx = game.turn_order.index(turn_color)
    except ValueError:
        game.turn_idx = 0

    return game


# ====== Flask API ======

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    global ai_instance
    return jsonify({
        "status": "ok",
        "workers": ai_instance.num_workers if ai_instance else 0,
    })


@app.route("/api/best_move", methods=["POST"])
def api_best_move():
    """获取最佳走法"""
    global ai_instance
    if ai_instance is None:
        return jsonify({"error": "AI not initialized"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "empty request"}), 400

        game = _make_game_from_state(data)
        color = data["color"]
        max_depth = data.get("max_depth", 8)
        time_limit = data.get("time_limit", 15.0)

        t0 = time.time()
        move = ai_instance.best_move(game, color, max_depth=max_depth, time_limit=time_limit)
        elapsed = time.time() - t0

        return jsonify({
            "move": list(move) if move else None,
            "depth": max_depth,
            "time": round(elapsed, 3),
        })

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[SuperAI-Server] /api/best_move 错误: {tb}")
        return jsonify({"error": str(e), "traceback": tb}), 500


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    """评估局面分数"""
    try:
        data = request.get_json()
        game = _make_game_from_state(data)
        color = data["color"]

        from evaluate import fast_evaluate
        score = fast_evaluate(game, color)

        return jsonify({
            "score": score,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clear_cache", methods=["POST"])
def api_clear_cache():
    """清空 AI 缓存"""
    global ai_instance
    if ai_instance:
        ai_instance.clear_cache()
    return jsonify({"status": "ok"})


# ====== 启动入口 ======

def main():
    global ai_instance

    parser = argparse.ArgumentParser(description="SuperAI HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument("--tt-size", type=int, default=2000000, help="转置表大小")
    parser.add_argument("--gpu", action="store_true", help="启用 GPU 加速（需要 PyTorch + CUDA）")
    parser.add_argument("--debug", action="store_true", help="Flask debug 模式")
    args = parser.parse_args()

    # 初始化 AI
    eval_fn = None
    if args.gpu:
        try:
            from gpu_eval import GPUBatchEvaluator
            gpu = GPUBatchEvaluator(device="cuda", batch_size=512)
            eval_fn = gpu.evaluate
            print(f"[SuperAI-Server] GPU 加速已启用: {gpu.device}")
        except Exception as e:
            print(f"[SuperAI-Server] GPU 初始化失败，回退 CPU: {e}")

    ai_instance = SuperAI(
        num_workers=args.workers,
        tt_size=args.tt_size,
        eval_fn=eval_fn,
    )
    print(f"[SuperAI-Server] 已启动: host={args.host} port={args.port}"
          f" workers={args.workers} tt_size={args.tt_size}")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
