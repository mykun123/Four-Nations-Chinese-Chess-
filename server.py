# server.py — 四国象棋 Web 服务器（局域网对战）
import asyncio
import json
import time
import uuid
import socket
import random
import traceback
import concurrent.futures
from aiohttp import web

from game_4p import (
    Game4P, RED, BLACK, GREEN, BLUE, NEUTRAL, TURN_ORDER,
    NEXT_PLAYER, PREV_PLAYER, COLOR_NAMES, COLOR_SHORT, COLOR_RGB,
    compute_alternating_turn_order,
)

# 进程池执行器（多房间 AI 并行搜索，利用多核 CPU）
_ai_executor = None

def _ai_search_worker(game_dict, color):
    """在子进程中反序列化 game 并执行 AI 搜索"""
    g = Game4P.__new__(Game4P)
    g.__dict__.update(game_dict)
    from ai_4p import best_move
    debug_info = {"scores": [], "chosen": None}
    move = best_move(g, color, debug_out=debug_info)
    return move, debug_info["scores"], debug_info["chosen"]

# 锦囊模式：各颜色初始棋子位置（含类型）
INITIAL_PIECES = {
    RED: [(18,5,"R"),(18,6,"N"),(18,7,"B"),(18,8,"A"),(18,9,"K"),(18,10,"A"),(18,11,"B"),(18,12,"N"),(18,13,"R"),
          (16,6,"C"),(16,12,"C"),
          (15,5,"P"),(15,7,"P"),(15,9,"P"),(15,11,"P"),(15,13,"P")],
    BLACK: [(0,5,"R"),(0,6,"N"),(0,7,"B"),(0,8,"A"),(0,9,"K"),(0,10,"A"),(0,11,"B"),(0,12,"N"),(0,13,"R"),
            (2,6,"C"),(2,12,"C"),
            (3,5,"P"),(3,7,"P"),(3,9,"P"),(3,11,"P"),(3,13,"P")],
    GREEN: [(5,0,"R"),(6,0,"N"),(7,0,"B"),(8,0,"A"),(9,0,"K"),(10,0,"A"),(11,0,"B"),(12,0,"N"),(13,0,"R"),
            (6,2,"C"),(12,2,"C"),
            (5,3,"P"),(7,3,"P"),(9,3,"P"),(11,3,"P"),(13,3,"P")],
    BLUE: [(5,18,"R"),(6,18,"N"),(7,18,"B"),(8,18,"A"),(9,18,"K"),(10,18,"A"),(11,18,"B"),(12,18,"N"),(13,18,"R"),
           (6,16,"C"),(12,16,"C"),
           (5,15,"P"),(7,15,"P"),(9,15,"P"),(11,15,"P"),(13,15,"P")],
}

INITIAL_ROOK_POSITIONS = {
    RED: [(18,5),(18,13)],
    BLACK: [(0,5),(0,13)],
    GREEN: [(5,0),(13,0)],
    BLUE: [(5,18),(13,18)],
}

# ====== 玩家 & 房间管理 ======

class Player:
    __slots__ = ("id", "name", "password", "ws", "color", "seat", "is_ai")
    def __init__(self, pid, name, password, ws):
        self.id = pid
        self.name = name
        self.password = password
        self.ws = ws
        self.color = None
        self.seat = -1
        self.is_ai = False


class Room:
    def __init__(self, rid, mode, creator):
        self.id = rid
        self.mode = mode
        self.players = [creator]
        self.game = None
        self.running = False
        self.ally_phase = False
        self.ally_invites = {}
        self.ally_invite_times = {}
        self.ally_teams = {}
        # 悔棋状态
        self.undo_request = None  # {"requester_id": str, "votes": {pid: bool}}
        # 锦囊（stratagem）模式
        self.stratagem_phase = False
        self.stratagems = {}       # {color: "resurrect"|"retreat"}
        self.stratagem_used = {}   # {color: bool} 是否已使用
        # 倒计时任务
        self.timer_task = None
        # 中立 AI 移动计数器：每 2 步人类走子触发一次中立移动
        self.moves_since_neutral = 0
        self.last_mover = None  # ä¸ä¸æ­¥èµ°å­çç©å®¶é¢è²

    @property
    def full(self):
        return len(self.players) >= 4

    @property
    def all_allied(self):
        """是否所有玩家都已结盟"""
        return len(self.ally_teams) >= 4

    def resolve_color_teams(self):
        """将玩家ID结盟关系转为颜色队伍字典 {color: team_id}"""
        ct = {}
        for p in self.players:
            if p.id in self.ally_teams and p.color is not None:
                ct[p.color] = self.ally_teams[p.id]
        return ct

    def get_empty_seat(self):
        """返回第一个空座位索引，无空位返回 -1"""
        taken = {p.seat for p in self.players}
        for s in range(4):
            if s not in taken:
                return s
        return -1

    def is_seat_empty(self, seat):
        return all(p.seat != seat for p in self.players)

    def assign_colors(self):
        """按座位分配颜色"""
        order = [RED, GREEN, BLACK, BLUE]
        for p in self.players:
            if 0 <= p.seat < 4:
                p.color = order[p.seat]
            else:
                # 容错：按 players 列表顺序
                idx = self.players.index(p)
                p.color = order[idx] if idx < 4 else None

    def to_dict(self):
        return {
            "id": self.id,
            "mode": self.mode,
            "players": [{"id": p.id, "name": p.name, "ready": p.color is not None,
                         "is_ai": p.is_ai, "seat": p.seat}
                        for p in self.players],
            "count": len(self.players),
            "full": self.full,
            "running": self.running,
        }


class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.player_rooms = {}  # pid -> room_id
        self.players = {}       # pid -> Player object
        self.connections = {}   # pid -> WebSocketResponse (for global broadcast)
        self.registered_users = {}  # name -> password (已注册的账户)
        self.ai_counter = 0

    def add_player(self, player, ws):
        """注册一个新玩家"""
        self.players[player.id] = player
        self.connections[player.id] = ws
        self.player_rooms[player.id] = None

    def get_player(self, pid):
        return self.players.get(pid)

    def create_room(self, mode, player):
        rid = uuid.uuid4().hex[:6]
        room = Room(rid, mode, player)
        self.rooms[rid] = room
        self.player_rooms[player.id] = rid
        player.seat = 0  # 创建者固定坐 0 号位
        return room

    def join_room(self, rid, player):
        room = self.rooms.get(rid)
        if not room or room.full or room.running:
            return False
        # 找到第一个空座位
        taken = {p.seat for p in room.players}
        for s in range(4):
            if s not in taken:
                player.seat = s
                break
        room.players.append(player)
        self.player_rooms[player.id] = rid
        return True

    def get_room(self, rid):
        return self.rooms.get(rid)

    def get_player_room(self, pid):
        rid = self.player_rooms.get(pid)
        return self.rooms.get(rid) if rid else None

    def disconnect_player(self, pid):
        """玩家断开连接，保留房间和游戏状态以便重连"""
        player = self.players.get(pid)
        if player:
            player.ws = None
        self.connections.pop(pid, None)

    def get_disconnected_player(self, name):
        """按用户名查找断线玩家（ws 为 None 或已关闭的都算断线）"""
        for p in self.players.values():
            if p.name == name:
                if p.ws is None:
                    return p
                try:
                    if p.ws.closed:
                        return p
                except Exception:
                    pass
        return None

    def remove_player(self, pid):
        """彻底移除玩家"""
        room = self.get_player_room(pid)
        if room:
            room.players = [p for p in room.players if p.id != pid]
            if not room.players:
                del self.rooms[room.id]
            else:
                if room.running:
                    room.running = False
        self.player_rooms.pop(pid, None)
        self.players.pop(pid, None)
        self.connections.pop(pid, None)

    def leave_room(self, pid):
        """让玩家离开房间，不删除登录信息"""
        room = self.get_player_room(pid)
        if room:
            room.players = [p for p in room.players if p.id != pid]
            if not room.players:
                del self.rooms[room.id]
        self.player_rooms[pid] = None

    def list_rooms(self):
        return [r.to_dict() for r in self.rooms.values() if not r.running]


async def _broadcast_room_update(room):
    """发送 room_updated 给房间内所有人类玩家"""
    payload = json.dumps({"type": "room_updated", "room": room.to_dict()})
    for p in room.players:
        if p.ws is not None and not p.ws.closed:
            try:
                await p.ws.send_str(payload)
            except Exception:
                pass


async def _auto_ally_ai_players(room, manager=None):
    """AI 自动结盟 — 有玩家时 AI 不自动配对，等玩家邀请；全 AI 房间才自动配对"""
    changed = False
    has_humans = any(not p.is_ai for p in room.players)

    if not has_humans:
        # 全 AI 房间：自动两两配对
        for p in list(room.players):
            if p.color is None or p.id in room.ally_teams:
                continue
            partner = None
            for other in room.players:
                if other.id != p.id and other.id not in room.ally_teams:
                    partner = other
                    break
            if not partner:
                continue
            used_teams = set(v for v in room.ally_teams.values())
            team_id = 0 if 0 not in used_teams else (1 if 1 not in used_teams else max(used_teams) + 1)
            room.ally_teams[p.id] = team_id
            room.ally_teams[partner.id] = team_id
            changed = True
    else:
        # 有人类玩家：AI 不自动配对，等人类通过 ally_invite 邀请（AI auto-accept）
        pass

    # 所有人类都已结盟 → 自动配对剩余 AI
    human_ids = {pl.id for pl in room.players if not pl.is_ai}
    allied_ids = set(room.ally_teams.keys())
    if has_humans and not (human_ids - allied_ids):
        all_ids = {pl.id for pl in room.players}
        remaining = list(all_ids - allied_ids)
        if len(remaining) == 2 and all(
            next(pl for pl in room.players if pl.id == pid).is_ai for pid in remaining
        ):
            used_teams = set(v for v in room.ally_teams.values())
            team_id = 0 if 0 not in used_teams else 1
            p0 = next((pl for pl in room.players if pl.id == remaining[0]), None)
            p1 = next((pl for pl in room.players if pl.id == remaining[1]), None)
            if p0 and p1:
                for pid in remaining:
                    room.ally_teams[pid] = team_id
                for pp in room.players:
                    if pp.ws is not None:
                        try:
                            await pp.ws.send_json({
                                "type": "ally_auto",
                                "team": {"members": [{"id": p0.id, "name": p0.name},
                                                     {"id": p1.id, "name": p1.name}]},
                            })
                        except Exception:
                            pass
                changed = True

    # 全部结盟后进入下一阶段
    if room.all_allied:
        if room.mode == "team_stratagem":
            await _start_stratagem_phase(room, manager)
        else:
            await _start_game(room, manager)


# ====== 游戏逻辑 ======

def start_game(room):
    """初始化游戏，返回各玩家颜色信息"""
    room.assign_colors()
    teams = None
    turn_order = None
    if room.mode in ("team", "team_stratagem"):
        teams = room.resolve_color_teams()
        print(f"[DEBUG] resolve_color_teams: {teams}")
        if teams:
            turn_order = compute_alternating_turn_order(teams)
        else:
            teams = {RED: 0, GREEN: 0, BLACK: 1, BLUE: 1}
            turn_order = compute_alternating_turn_order(teams)
    else:
        turn_order = list(TURN_ORDER)
    game = Game4P(mode=room.mode, teams=teams, turn_order=turn_order)
    room.game = game
    room.moves_since_neutral = 0
    room.running = True
    room.last_mover = None
    print(f"[DEBUG] start_game mode={room.mode} teams={teams} turn_order={turn_order} moves_since_neutral init to 1")
    return game


def _build_teams_list(room):
    """从 ally_teams 构建前端 teams 列表 [{members: [{id,name},...]}, ...]"""
    teams_map = {}
    for pid, team_id in room.ally_teams.items():
        if team_id not in teams_map:
            teams_map[team_id] = []
        p = next((pl for pl in room.players if pl.id == pid), None)
        if p:
            teams_map[team_id].append({"id": p.id, "name": p.name})
    return [{"members": members} for members in teams_map.values()]


async def _start_ally_phase(room, manager=None):
    """开始结盟阶段（仅组队模式）"""
    room.assign_colors()
    room.ally_phase = True
    player_list = []
    for p in room.players:
        player_list.append({
            "id": p.id,
            "name": p.name,
            "color": p.color,
        })
    teams_list = _build_teams_list(room)
    payload = json.dumps({
        "type": "ally_phase_start",
        "players": player_list,
        "teams": teams_list,
    })
    for p in room.players:
        try:
            if p.ws is not None and not p.ws.closed:
                await p.ws.send_str(payload)
        except Exception:
            pass

    # AI 自动结盟
    await _auto_ally_ai_players(room, manager)


# ====== 倒计时 & 悔棋 ======

async def _broadcast_move(room, color, player_name, fr, fc, tr, tc, game, manager):
    """走子后的统一广播逻辑：处理击杀、中立移动、胜负检查、turn_change、计时器"""
    # 记录上一步走子的玩家
    room.last_mover = color
    # 检查是否击杀了将/帅
    last = game.move_history[-1]
    king_killed = False
    if last["captured"] and last["captured"]["type"] == "K":
        king_killed = True
        if last["captured"]["color"] == NEUTRAL:
            game.board[fr][fc] = game.board[tr][tc]
            game.board[tr][tc] = {"color": color, "type": "R"}
            game.remove_all_neutral()
            for p in room.players:
                if p.ws is not None:
                    try:
                        await p.ws.send_json({
                            "type": "neutral_reward",
                            "color": color,
                            "player_name": player_name,
                            "r": tr, "c": tc,
                        })
                    except Exception:
                        pass

    # 发送走子消息或完整棋盘同步
    if king_killed:
        board_dict = _board_to_dict(game.board)
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({"type": "board_sync", "board": board_dict})
                except Exception:
                    pass
    else:
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({
                        "type": "move_made",
                        "fr": fr, "fc": fc, "tr": tr, "tc": tc, "color": color,
                    })
                except Exception:
                    pass

    # 中立 AI：4人都存活时每2步触发，有人阵亡后每1步触发
    if not king_killed:
        room.moves_since_neutral += 1
        alive_humans = sum(1 for c in [RED, GREEN, BLACK, BLUE] if game.alive.get(c, True))
        threshold = 2 if alive_humans == 4 else 1
        print(f"[DEBUG] neutral check: alive={alive_humans} threshold={threshold} moves={room.moves_since_neutral}")
        if room.moves_since_neutral >= threshold:
            room.moves_since_neutral = 0
            neutral_move = game.get_single_neutral_ai_move()
            print(f"[DEBUG] get_single_neutral_ai_move() returned: {neutral_move}")
            if neutral_move is not None:
                nfr, nfc, ntr, ntc = neutral_move
                moving_piece = game.board[nfr][nfc]
                game.apply_neutral_move(nfr, nfc, ntr, ntc)
                game.last_neutral_moves = [(nfr, nfc, ntr, ntc)]
                print(f"[DEBUG] neutral AI moved: ({nfr},{nfc}) -> ({ntr},{ntc})")
                for p in room.players:
                    if p.ws is not None:
                        try:
                            await p.ws.send_json({
                                "type": "neutral_moves",
                                "moves": [{"fr": nfr, "fc": nfc, "tr": ntr, "tc": ntc}],
                            })
                        except Exception:
                            pass
                for p in room.players:
                    if p.ws is not None:
                        try:
                            await p.ws.send_json({
                                "type": "neutral_notification",
                                "from_r": nfr, "from_c": nfc,
                                "to_r": ntr, "to_c": ntc,
                                "piece_type": moving_piece["type"],
                            })
                        except Exception:
                            pass

    # 检查胜负
    winners = game.check_winner()
    if winners:
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({
                        "type": "game_over",
                        "winners": winners,
                        "winner_names": [COLOR_NAMES[c] for c in winners],
                    })
                except Exception:
                    pass
        room.last_mover = None
        room.running = False
        # 全 AI 房间自动清理
        has_human = any(p.ws is not None for p in room.players)
        if not has_human and manager:
            manager.rooms.pop(room.id, None)
        return

    print(f"[DEBUG] _broadcast_move: {COLOR_NAMES[color]} moved -> next turn: {COLOR_NAMES[game.turn]} (turn_idx={game.turn_idx})")

    # 广播 turn_change
    current_name = None
    current_is_ai = False
    for pp in room.players:
        if pp.color == game.turn:
            current_name = pp.name
            current_is_ai = pp.is_ai
            break
    for p in room.players:
        if p.ws is not None:
            try:
                await p.ws.send_json({
                    "type": "turn_change",
                    "color": game.turn,
                    "player_name": current_name,
                    "is_ai": current_is_ai,
                })
            except Exception:
                pass

    # 注意：调用方需自行启动下一轮计时器（避免 _timer_tick 自取消）


def _cancel_timer(room):
    if room.timer_task:
        room.timer_task.cancel()
        room.timer_task = None

def _start_turn_timer(room, manager):
    _cancel_timer(room)
    if not room.game:
        return
    color = room.game.turn
    is_ai = any(p.color == color and p.is_ai for p in room.players)
    delay = 1.5 if is_ai else 30
    print(f"[DEBUG] _start_turn_timer: color={COLOR_NAMES[color]} is_ai={is_ai} delay={delay}s", flush=True)
    room.timer_task = asyncio.create_task(_timer_tick(room, manager, delay))

async def _timer_tick(room, manager, delay=30):
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    if not room.running or not room.game:
        return
    game = room.game
    color = game.turn
    print(f"[DEBUG] timer_tick firing for {COLOR_NAMES[color]}", flush=True)
    # 获取当前玩家
    player_obj = None
    for p in room.players:
        if p.color == color:
            player_obj = p
            break
    # 获取合法走法
    try:
        moves = game.get_legal_moves(color)
    except Exception as e:
        print(f"[ERROR] get_legal_moves failed: {e}", flush=True)
        return
    if moves:
        if player_obj and player_obj.is_ai:
            try:
                loop = asyncio.get_event_loop()
                ai_move, debug_scores, debug_chosen = await loop.run_in_executor(
                    _ai_executor, _ai_search_worker, game.__dict__, color)
                game.ai_debug_log.append(
                    (len(game.move_history), color, debug_scores, debug_chosen))
            except Exception as e:
                print(f"[ERROR] AI move failed: {e}", flush=True)
                traceback.print_exc()
                ai_move = None
                debug_scores = []
                debug_chosen = None
            if ai_move:
                fr, fc, tr, tc = ai_move
            else:
                fr, fc, tr, tc = random.choice(moves)
        else:
            fr, fc, tr, tc = random.choice(moves)
        game.make_move(fr, fc, tr, tc, is_ai=True)
        if player_obj and player_obj.is_ai:
            try: game.write_ai_debug()
            except Exception: pass
        try:
            await _broadcast_move(room, color, player_obj.name if player_obj else COLOR_NAMES[color],
                                  fr, fc, tr, tc, game, manager)
        except Exception as e:
            print(f"[ERROR] _broadcast_move failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return
        # 先清除当前任务引用，避免 _start_turn_timer 自取消
        room.timer_task = None
        if room.running:
            _start_turn_timer(room, manager)
    else:
        # 无合法走法，跳过
        game.next_turn()
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({"type": "turn_timeout", "color": color, "turn": game.turn})
                except Exception:
                    pass
        room.timer_task = None
        _start_turn_timer(room, manager)


async def handle_message(ws, data, manager):
    """处理客户端消息"""
    msg_type = data.get("type")

    if msg_type == "login":
        username = data["username"]
        password = data.get("password", "")
        # 验证密码或自动注册
        if username in manager.registered_users:
            if manager.registered_users[username] != password:
                await ws.send_json({"type": "error", "message": "密码错误"})
                return
        else:
            manager.registered_users[username] = password
        # 检查是否断线重连
        existing = manager.get_disconnected_player(username)
        if existing:
            room = manager.get_player_room(existing.id)
            if room:
                # 重连：恢复 ws 连接（支持游戏、结盟、等待三种状态）
                existing.ws = ws
                manager.connections[existing.id] = ws
                await ws.send_json({"type": "login_ok", "user_id": existing.id, "name": data["username"]})
                if room.running:
                    game = room.game
                    await ws.send_json({
                        "type": "game_start",
                        "your_color": existing.color,
                        "turn_order": game.turn_order,
                        "mode": room.mode,
                        "board_state": _board_to_dict(game.board),
                        "turn": game.turn,
                        "players": [{"id": pl.id, "name": pl.name, "color": pl.color}
                                    for pl in room.players],
                        "color_teams": game.teams if room.mode == "team" else {},
                    })
                elif room.ally_phase:
                    # 结盟阶段
                    await ws.send_json({"type": "room_joined", "room": room.to_dict()})
                    await ws.send_json({
                        "type": "ally_phase_start",
                        "players": [{"id": p.id, "name": p.name, "color": p.color} for p in room.players],
                        "teams": _build_teams_list(room),
                    })
                else:
                    # 等待阶段
                    await ws.send_json({"type": "room_joined", "room": room.to_dict()})
                # 通知其他玩家
                for p in room.players:
                    if p.id != existing.id and p.ws is not None:
                        try:
                            await p.ws.send_json({
                                "type": "player_reconnected",
                                "player_id": existing.id,
                                "player_name": existing.name,
                            })
                        except Exception:
                            pass
                return existing
            # 不在任何房间 — 清理旧记录重新登录
            manager.players.pop(existing.id, None)
            manager.connections.pop(existing.id, None)
            manager.player_rooms.pop(existing.id, None)

        pid = uuid.uuid4().hex[:8]
        player = Player(pid, username, password, ws)
        manager.add_player(player, ws)
        await ws.send_json({"type": "login_ok", "user_id": pid, "name": username})
        await ws.send_json({"type": "rooms_list", "rooms": manager.list_rooms()})
        return player

    elif msg_type == "list_rooms":
        await ws.send_json({"type": "room_list", "rooms": manager.list_rooms()})

    elif msg_type == "create_room":
        player_obj = manager.get_player(data.get("user_id"))
        if not player_obj:
            await ws.send_json({"type": "error", "message": "未登录"})
            return
        manager.leave_room(player_obj.id)
        room = manager.create_room(data.get("mode", "ffa"), player_obj)
        await ws.send_json({"type": "room_joined", "room": room.to_dict()})
        await _update_room_lobby(manager)

    elif msg_type == "join_room":
        rid = data["room_id"]
        player_obj = manager.get_player(data.get("user_id"))
        if not player_obj:
            await ws.send_json({"type": "error", "message": "玩家不存在"})
            return
        manager.leave_room(player_obj.id)
        if manager.join_room(rid, player_obj):
            room = manager.get_room(rid)
            await ws.send_json({"type": "room_joined", "room": room.to_dict()})
            # 直接通知其他房间成员
            for p in room.players:
                if p.id != player_obj.id:
                    try:
                        await p.ws.send_json({"type": "player_joined", "room": room.to_dict()})
                    except Exception:
                        pass
            await _update_room_lobby(manager)
        else:
            await ws.send_json({"type": "error", "message": "加入房间失败"})

    elif msg_type == "end_game":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if room and room.running:
            _cancel_timer(room)
            room.running = False
            # 通知所有玩家游戏已结束
            payload = json.dumps({"type": "game_ended"})
            for p in room.players:
                if p.ws is not None and not p.ws.closed:
                    try:
                        await p.ws.send_str(payload)
                    except Exception:
                        pass
            # 删除房间
            manager.rooms.pop(room.id, None)
            # 清理玩家房间引用
            for p in room.players:
                manager.player_rooms[p.id] = None
        await _update_room_lobby(manager)

    elif msg_type == "leave_room":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        manager.leave_room(user_id)
        if room and room.players and room.id in manager.rooms:
            has_human = any(p.ws is not None for p in room.players)
            if has_human:
                await _broadcast_room_update(room)
            else:
                # 没有人类玩家了，删除房间
                _cancel_timer(room)
                room.running = False
                manager.rooms.pop(room.id, None)
        await _update_room_lobby(manager)

    elif msg_type == "restart_game":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room:
            await ws.send_json({"type": "error", "message": "不在房间中"})
            return
        if room.running:
            await ws.send_json({"type": "error", "message": "游戏仍在进行中"})
            return
        # 检查人数是否足够
        if len(room.players) < 2:
            await ws.send_json({"type": "error", "message": "人数不足，无法开始"})
            return
        # 重新初始化游戏
        room.undo_request = None
        room.stratagem_phase = False
        room.stratagems = {}
        room.stratagem_used = {}
        room.moves_since_neutral = 0
        room.last_mover = None
        room.ally_invites = {}
        room.ally_invite_times = {}
        # 重新开始游戏（保留原队伍、模式）
        if room.mode in ("team", "team_stratagem") and room.ally_teams:
            await _start_game(room, manager)
        else:
            await _start_game(room, manager)

    elif msg_type == "add_ai":
        user_id = data.get("user_id")
        player_obj = manager.get_player(user_id)
        if not player_obj:
            await ws.send_json({"type": "error", "message": "未登录"})
            return
        room = manager.get_player_room(user_id)
        if not room or room.running:
            await ws.send_json({"type": "error", "message": "房间不存在或已开始"})
            return
        if room.full:
            await ws.send_json({"type": "error", "message": "房间已满"})
            return
        seat_index = data.get("seat_index", -1)
        if seat_index < 0 or not room.is_seat_empty(seat_index):
            seat_index = room.get_empty_seat()
            if seat_index < 0:
                await ws.send_json({"type": "error", "message": "没有空座位"})
                return
        manager.ai_counter += 1
        ai_id = f"ai_{manager.ai_counter}"
        ai_player = Player(ai_id, f"电脑{manager.ai_counter}", "", None)
        ai_player.seat = seat_index
        ai_player.is_ai = True
        room.players.append(ai_player)
        await _broadcast_room_update(room)

    elif msg_type == "remove_ai":
        user_id = data.get("user_id")
        player_obj = manager.get_player(user_id)
        if not player_obj:
            await ws.send_json({"type": "error", "message": "未登录"})
            return
        room = manager.get_player_room(user_id)
        if not room or room.running:
            await ws.send_json({"type": "error", "message": "房间不存在或已开始"})
            return
        ai_id = data.get("ai_id", "")
        before = len(room.players)
        room.players = [p for p in room.players if p.id != ai_id]
        if len(room.players) == before:
            await ws.send_json({"type": "error", "message": "未找到该 AI"})
            return
        await _broadcast_room_update(room)

    elif msg_type == "start_game_request":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or room.running:
            await ws.send_json({"type": "error", "message": "房间不存在或已开始"})
            return
        if len(room.players) < 4:
            await ws.send_json({"type": "error", "message": "人数不足，无法开始"})
            return
        if room.mode in ("team", "team_stratagem"):
            await _start_ally_phase(room, manager)
        else:
            await _start_game(room, manager)

    elif msg_type == "get_moves":
        """客户端请求某棋子的合法走法（仅显示用，服务端仍会验证最终走法）"""
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.running:
            return
        player_obj = manager.get_player(user_id)
        if not player_obj:
            return
        color = player_obj.color
        game = room.game
        if game.turn != color:
            return
        r, c = data["r"], data["c"]
        all_moves = game.get_legal_moves(color)
        piece_moves = [{"r": m[2], "c": m[3]} for m in all_moves if m[0] == r and m[1] == c]
        await ws.send_json({"type": "legal_moves", "moves": piece_moves})

    elif msg_type == "ally_invite":
        user_id = data.get("user_id")
        target_id = data.get("target_id")
        room = manager.get_player_room(user_id)
        if not room or not room.ally_phase:
            return
        player_obj = manager.get_player(user_id)
        if not player_obj:
            return
        # 查找目标（AI 不在 manager.players 中，需从 room.players 查找）
        target_obj = manager.get_player(target_id)
        if not target_obj:
            target_obj = next((p for p in room.players if p.id == target_id), None)
        if not target_obj:
            await ws.send_json({"type": "error", "message": "玩家不存在"})
            return
        if target_obj.id in room.ally_teams:
            await ws.send_json({"type": "error", "message": "该玩家已有队伍"})
            return
        if player_obj.id in room.ally_teams:
            await ws.send_json({"type": "error", "message": "你已有队伍"})
            return

        if target_obj.is_ai:
            # AI 自动同意结盟
            used_teams = set(v for v in room.ally_teams.values())
            team_id = 0 if 0 not in used_teams else (1 if 1 not in used_teams else max(used_teams) + 1)
            room.ally_teams[player_obj.id] = team_id
            room.ally_teams[target_obj.id] = team_id
            # 广播结盟
            for p in room.players:
                if p.ws is not None:
                    try:
                        await p.ws.send_json({
                            "type": "ally_formed",
                            "team": {"members": [{"id": player_obj.id, "name": player_obj.name},
                                                 {"id": target_obj.id, "name": target_obj.name}]},
                        })
                    except Exception:
                        pass
            # 检查剩余 2 人自动配对
            all_ids = {pl.id for pl in room.players}
            allied_ids = set(room.ally_teams.keys())
            remaining = list(all_ids - allied_ids)
            if len(remaining) == 2:
                other_team_id = 1 if team_id == 0 else 0
                p0 = next((p for p in room.players if p.id == remaining[0]), None)
                p1 = next((p for p in room.players if p.id == remaining[1]), None)
                if p0 and p1:
                    for pid in remaining:
                        room.ally_teams[pid] = other_team_id
                    for p in room.players:
                        if p.ws is not None:
                            try:
                                await p.ws.send_json({
                                    "type": "ally_auto",
                                    "team": {"members": [{"id": p0.id, "name": p0.name},
                                                         {"id": p1.id, "name": p1.name}]},
                                })
                            except Exception:
                                pass
            # 全部结盟后进入下一阶段
            if room.all_allied:
                if room.mode == "team_stratagem":
                    await _start_stratagem_phase(room, manager)
                else:
                    await _start_game(room, manager)
            return

        # 人类 — 以下为正常邀请流程
        # 检查冷却（2秒内不能重复邀请）
        now = time.time()
        last = room.ally_invite_times.get(user_id, 0)
        if now - last < 2:
            await ws.send_json({"type": "error", "message": "请等待2秒后再邀请"})
            return
        # 检查自己是否已有待处理邀请
        if user_id in room.ally_invites:
            await ws.send_json({"type": "error", "message": "你已有一个待处理的邀请"})
            return
        # 检查自己是否正在被其他人邀请
        if user_id in list(room.ally_invites.values()):
            await ws.send_json({"type": "error", "message": "你正在被其他人邀请，请先处理"})
            return
        # 检查目标是否已被其他人邀请
        if target_id in room.ally_invites.values():
            await ws.send_json({"type": "error", "message": "该玩家已被其他人邀请"})
            return
        # 检查目标是否正在邀请其他人
        if target_id in room.ally_invites:
            await ws.send_json({"type": "error", "message": "该玩家正在邀请其他人"})
            return
        room.ally_invite_times[user_id] = now
        room.ally_invites[user_id] = target_id
        # 通知目标
        try:
            await target_obj.ws.send_json({
                "type": "ally_invite", "from": user_id, "from_name": player_obj.name,
            })
        except Exception:
            pass
        await ws.send_json({"type": "ally_invite_sent", "to": target_id, "to_name": target_obj.name})

    elif msg_type == "ally_accept":
        user_id = data.get("user_id")
        inviter_id = data.get("inviter_id")
        room = manager.get_player_room(user_id)
        if not room or not room.ally_phase:
            return
        # 验证确实是收到邀请的人
        if room.ally_invites.get(inviter_id) != user_id:
            return
        # 分配队伍ID
        used_teams = set(v for v in room.ally_teams.values())
        team_id = 0 if 0 not in used_teams else (1 if 1 not in used_teams else max(used_teams) + 1)
        room.ally_teams[inviter_id] = team_id
        room.ally_teams[user_id] = team_id
        del room.ally_invites[inviter_id]
        # 清理已结盟玩家的其他邀请
        to_clean = [k for k, v in list(room.ally_invites.items())
                    if k in room.ally_teams or v in room.ally_teams]
        for k in to_clean:
            del room.ally_invites[k]

        # 广播结盟成功
        inviter = manager.get_player(inviter_id)
        accepter = manager.get_player(user_id)
        if inviter and accepter:
            for p in room.players:
                try:
                    if p.ws is not None:
                        await p.ws.send_json({
                            "type": "ally_formed",
                            "team": {"members": [{"id": inviter.id, "name": inviter.name},
                                                 {"id": accepter.id, "name": accepter.name}]},
                        })
                except Exception:
                    pass

        # 自动组队剩余的2名玩家
        all_ids = {p.id for p in room.players}
        allied_ids = set(room.ally_teams.keys())
        remaining = list(all_ids - allied_ids)
        if len(remaining) == 2:
            other_team_id = 1 if team_id == 0 else 0
            for pid in remaining:
                room.ally_teams[pid] = other_team_id
            p0 = next((p for p in room.players if p.id == remaining[0]), None)
            p1 = next((p for p in room.players if p.id == remaining[1]), None)
            if p0 and p1:
                for p in room.players:
                    try:
                        if p.ws is not None:
                            await p.ws.send_json({
                                "type": "ally_auto",
                                "team": {"members": [{"id": p0.id, "name": p0.name},
                                                     {"id": p1.id, "name": p1.name}]},
                            })
                    except Exception:
                        pass

        if room.mode == "team_stratagem":
            await _start_stratagem_phase(room, manager)
        else:
            await _start_game(room, manager)

    elif msg_type == "ally_decline":
        user_id = data.get("user_id")
        inviter_id = data.get("inviter_id")
        room = manager.get_player_room(user_id)
        if not room or not room.ally_phase:
            return
        if room.ally_invites.get(inviter_id) == user_id:
            del room.ally_invites[inviter_id]
        inviter = manager.get_player(inviter_id)
        if inviter:
            try:
                await inviter.ws.send_json({"type": "ally_declined", "by": user_id})
            except Exception:
                pass

    elif msg_type == "ally_cancel":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.ally_phase:
            return
        if user_id in room.ally_invites:
            target_id = room.ally_invites.pop(user_id)
            target = manager.get_player(target_id)
            if target:
                try:
                    await target.ws.send_json({"type": "ally_cancelled", "by": user_id})
                except Exception:
                    pass
            await ws.send_json({"type": "ally_cancel_ok", "target": target_id})

    elif msg_type == "stratagem_select":
        user_id = data.get("user_id")
        choice = data.get("choice")  # "resurrect" or "retreat"
        room = manager.get_player_room(user_id)
        if not room or not room.stratagem_phase:
            return
        player_obj = manager.get_player(user_id)
        if not player_obj or player_obj.color is None:
            return
        color = player_obj.color
        if color in room.stratagems:
            await ws.send_json({"type": "error", "message": "你已经选择过了"})
            return
        # 检查盟友是否已选了相同的
        color_teams = room.resolve_color_teams()
        my_team = color_teams.get(color)
        teammate_color = None
        if my_team is not None:
            for c, t in color_teams.items():
                if t == my_team and c != color:
                    teammate_color = c
                    break
            if teammate_color is not None and teammate_color in room.stratagems:
                if room.stratagems[teammate_color] == choice:
                    await ws.send_json({"type": "error", "message": "盟友已选择相同锦囊，请选择另一个"})
                    return

        room.stratagems[color] = choice
        # 自动锁定盟友的锦囊为另一个
        if teammate_color is not None and teammate_color not in room.stratagems:
            other = "retreat" if choice == "resurrect" else "resurrect"
            room.stratagems[teammate_color] = other
            for p in room.players:
                if p.color == teammate_color and p.ws is not None:
                    try:
                        await p.ws.send_json({"type": "stratagem_assigned", "choice": other})
                    except Exception:
                        pass

        await ws.send_json({"type": "stratagem_ok", "choice": choice})

        # 所有人都选好 → 进入游戏
        if len(room.stratagems) >= 4:
            room.stratagem_phase = False
            for c in room.stratagems:
                room.stratagem_used[c] = False
            for p in room.players:
                if p.ws is not None:
                    try:
                        c = p.color
                        # 查找该玩家的盟友
                        ac = None
                        for sc, st in color_teams.items():
                            if st == color_teams.get(c) and sc != c:
                                ac = room.stratagems.get(sc)
                                break
                        await p.ws.send_json({
                            "type": "stratagem_ready",
                            "stratagems": dict(room.stratagems),
                            "your_choice": room.stratagems.get(c),
                            "ally_choice": ac,
                        })
                    except Exception:
                        pass
            await _start_game(room, manager)

    elif msg_type == "use_stratagem":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.running or not room.game:
            return
        player_obj = manager.get_player(user_id)
        if not player_obj:
            return
        color = player_obj.color
        if room.game.turn != color:
            await ws.send_json({"type": "error", "message": "还没轮到你"})
            return
        if room.stratagem_used.get(color, True):
            await ws.send_json({"type": "error", "message": "锦囊已使用"})
            return
        choice = room.stratagems.get(color)
        if not choice:
            return
        if choice == "resurrect":
            ok, err = _use_resurrect(room, color)
        else:
            ok, err = _use_retreat(room, color)
        if not ok:
            await ws.send_json({"type": "error", "message": err or "锦囊使用失败"})
            return
        room.stratagem_used[color] = True
        board_dict = _board_to_dict(room.game.board)
        # 同步最新棋盘给所有人
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({
                        "type": "stratagem_used",
                        "color": color,
                        "stratagem": choice,
                        "board": board_dict,
                    })
                except Exception:
                    pass

    elif msg_type == "move":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.running:
            return
        player_obj = manager.get_player(user_id)
        if not player_obj:
            return

        fr, fc, tr, tc = data["fr"], data["fc"], data["tr"], data["tc"]
        color = player_obj.color
        game = room.game

        if game.turn != color:
            await ws.send_json({"type": "error", "message": "还没轮到你"})
            return

        moves = game.get_legal_moves(color)
        valid = any(m[0] == fr and m[1] == fc and m[2] == tr and m[3] == tc for m in moves)
        if not valid:
            await ws.send_json({"type": "error", "message": "非法走法"})
            return

        _cancel_timer(room)
        room.undo_request = None
        game.last_neutral_moves = None

        game.make_move(fr, fc, tr, tc)
        await _broadcast_move(room, color, player_obj.name, fr, fc, tr, tc, game, manager)
        if room.running:
            _start_turn_timer(room, manager)  # 启动下一轮计时



    elif msg_type == "undo_request":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.running or not room.game:
            return
        if room.undo_request:
            await ws.send_json({"type": "error", "message": "已有悔棋请求在处理中"})
            return
        game = room.game
        if not game.move_history:
            await ws.send_json({"type": "error", "message": "没有可悔的棋"})
            return
        # 检查是否上一步走子的玩家
        player_obj = manager.get_player(user_id)
        if not player_obj or player_obj.color != room.last_mover:
            await ws.send_json({"type": "error", "message": "你不能悔棋"})
            return
        # 暂停倒计时
        _cancel_timer(room)
        room.undo_request = {"requester_id": user_id, "votes": {}}
        # AI 自动同意悔棋
        for p in room.players:
            if p.is_ai:
                room.undo_request["votes"][p.id] = True
        for p in room.players:
            if p.ws is not None:
                try:
                    await p.ws.send_json({
                        "type": "undo_vote_request",
                        "requester_id": user_id,
                        "requester_name": manager.get_player(user_id).name if manager.get_player(user_id) else "",
                    })
                except Exception:
                    pass

    elif msg_type == "undo_vote":
        user_id = data.get("user_id")
        room = manager.get_player_room(user_id)
        if not room or not room.undo_request:
            return
        vote = data.get("vote")
        if vote not in ("yes", "no"):
            return
        room.undo_request["votes"][user_id] = (vote == "yes")
        # 检查是否所有人都投了
        if len(room.undo_request["votes"]) < len(room.players):
            return
        all_yes = all(room.undo_request["votes"].values())
        if all_yes:
            game = room.game
            # 撤销中立走子
            game.undo_neutral_moves()
            # 撤销玩家走子
            result = game.undo_last()
            if result:
                room.last_mover = None
                board_dict = _board_to_dict(game.board)
                for p in room.players:
                    if p.ws is not None:
                        try:
                            await p.ws.send_json({"type": "undo_accepted"})
                            await p.ws.send_json({
                                "type": "board_sync",
                                "board": board_dict,
                            })
                        except Exception:
                            pass
                # 通知当前轮到谁
                current_name = None
                for pp in room.players:
                    if pp.color == game.turn:
                        current_name = pp.name
                        break
                for p in room.players:
                    if p.ws is not None:
                        try:
                            await p.ws.send_json({
                                "type": "turn_change",
                                "color": game.turn,
                                "player_name": current_name,
                            })
                        except Exception:
                            pass
                _start_turn_timer(room, manager)
        else:
            for p in room.players:
                if p.ws is not None:
                    try:
                        await p.ws.send_json({"type": "undo_rejected"})
                    except Exception:
                        pass
        room.undo_request = None

async def _start_stratagem_phase(room, manager):
    """开始锦囊选择阶段"""
    room.stratagem_phase = True
    room.stratagems = {}
    color_teams = room.resolve_color_teams()
    for p in room.players:
        if p.ws is not None:
            try:
                await p.ws.send_json({
                    "type": "stratagem_phase",
                    "options": ["resurrect", "retreat"],
                    "your_color": p.color,
                    "color_teams": color_teams,
                })
            except Exception:
                pass

    # AI 自动选锦囊
    await _auto_select_ai_stratagems(room, manager)


async def _auto_select_ai_stratagems(room, manager=None):
    """AI 玩家自动选择锦囊"""
    if not room.stratagem_phase:
        return
    for p in room.players:
        if not p.is_ai or p.color is None:
            continue
        if p.color in room.stratagems:
            continue
        choice = random.choice(["resurrect", "retreat"])
        # 检查盟友是否已选了相同的（与人类相同的逻辑）
        color_teams = room.resolve_color_teams()
        my_team = color_teams.get(p.color)
        teammate_color = None
        if my_team is not None:
            for c, t in color_teams.items():
                if t == my_team and c != p.color:
                    teammate_color = c
                    break
            if teammate_color is not None and teammate_color in room.stratagems:
                if room.stratagems[teammate_color] == choice:
                    choice = "retreat" if choice == "resurrect" else "resurrect"
        room.stratagems[p.color] = choice
        # 如果盟友也是 AI 且未选，自动锁定另一个
        if teammate_color is not None and teammate_color not in room.stratagems:
            tp = next((pl for pl in room.players if pl.color == teammate_color), None)
            if tp and tp.is_ai:
                other = "retreat" if choice == "resurrect" else "resurrect"
                room.stratagems[teammate_color] = other
        # 通知前端
        for pp in room.players:
            if pp.ws is not None:
                try:
                    await pp.ws.send_json({
                        "type": "stratagem_ok",
                        "choice": choice,
                    })
                except Exception:
                    pass
    # 全都选好后进入游戏
    if len(room.stratagems) >= 4:
        room.stratagem_phase = False
        for c in room.stratagems:
            room.stratagem_used[c] = False
        color_teams = room.resolve_color_teams()
        for p in room.players:
            if p.ws is not None:
                try:
                    c = p.color
                    ac = None
                    for sc, st in color_teams.items():
                        if st == color_teams.get(c) and sc != c:
                            ac = room.stratagems.get(sc)
                            break
                    await p.ws.send_json({
                        "type": "stratagem_ready",
                        "stratagems": dict(room.stratagems),
                        "your_choice": room.stratagems.get(c),
                        "ally_choice": ac,
                    })
                except Exception:
                    pass
        await _start_game(room, manager)


def _use_resurrect(room, color):
    """借尸还魂：自己损失了一个车才能发动"""
    game = room.game
    board = game.board
    # 检查是否确实损失了车（场上少于2个车）
    rook_count = 0
    for rr in range(19):
        for cc in range(19):
            piece = board[rr][cc]
            if piece and piece["color"] == color and piece["type"] == "R":
                rook_count += 1
    if rook_count >= 2:
        return False, "你还有两个车，无需使用借尸还魂"

    # 先尝试初始车的位置
    positions = list(INITIAL_ROOK_POSITIONS[color])
    random.shuffle(positions)
    for r, c in positions:
        if board[r][c] is None:
            board[r][c] = {"color": color, "type": "R"}
            return True, None
    # 如果两个车位置都被占了，找该方任意初始空位
    all_init = list(INITIAL_PIECES[color])
    random.shuffle(all_init)
    for r, c, pt in all_init:
        if board[r][c] is None:
            board[r][c] = {"color": color, "type": "R"}
            return True, None
    return False, "无空位可以复活车"


def _use_retreat(room, color):
    """鸣金收兵：将所有棋子召回初始位置（迭代直到无变化）"""
    game = room.game
    board = game.board
    initial = INITIAL_PIECES[color]

    # 按类型分组初始位置
    type_to_init = {}
    for r, c, pt in initial:
        type_to_init.setdefault(pt, []).append((r, c))

    moved = False

    # 迭代：每次有棋子被移走释放空位后，重新检查所有类型
    changed = True
    while changed:
        changed = False
        for pt, init_positions in type_to_init.items():
            empty_init = [(r, c) for r, c in init_positions if board[r][c] is None]
            if not empty_init:
                continue
            for rr in range(19):
                for cc in range(19):
                    piece = board[rr][cc]
                    if piece and piece["color"] == color and piece["type"] == pt:
                        if (rr, cc) in init_positions:
                            continue  # 已在初始位置
                        tr, tc = empty_init.pop(0)
                        board[tr][tc] = piece
                        board[rr][cc] = None
                        moved = True
                        changed = True
                        if not empty_init:
                            break
                if not empty_init:
                    break

    # 第二遍：仍被其他类型占据的初始位置，交换（迭代）
    changed = True
    while changed:
        changed = False
        for pt, init_positions in type_to_init.items():
            displaced = []
            for rr in range(19):
                for cc in range(19):
                    piece = board[rr][cc]
                    if piece and piece["color"] == color and piece["type"] == pt:
                        if (rr, cc) not in init_positions:
                            displaced.append((rr, cc))
            if not displaced:
                continue
            for ir, ic in init_positions:
                occupant = board[ir][ic]
                if occupant and occupant["color"] == color and occupant["type"] != pt:
                    if not displaced:
                        break
                    dr, dc = displaced.pop(0)
                    board[ir][ic] = board[dr][dc]
                    board[dr][dc] = occupant
                    moved = True
                    changed = True

    if not moved:
        return False, "所有棋子已在初始位置"
    return True, None


async def _start_game(room, manager):
    """开始游戏"""
    game = start_game(room)
    room.ally_phase = False
    room.stratagem_phase = False
    turn_order = game.turn_order
    color_teams = game.teams if game.mode in ("team", "team_stratagem") else {}
    for p in room.players:
        if p.ws is not None:
            try:
                msg = {
                    "type": "game_start",
                    "your_color": p.color,
                    "turn_order": turn_order,
                    "mode": room.mode,
                    "board_state": _board_to_dict(game.board),
                    "turn": game.turn,
                    "players": [{"id": pl.id, "name": pl.name, "color": pl.color, "is_ai": pl.is_ai}
                                for pl in room.players],
                    "color_teams": color_teams,
                }
                if room.mode == "team_stratagem":
                    msg["stratagems"] = dict(room.stratagems)
                    msg["stratagem_used"] = dict(room.stratagem_used)
                await p.ws.send_json(msg)
            except Exception:
                pass

    # 游戏开始后立即启动倒计时
    _start_turn_timer(room, manager)


async def _update_room_lobby(manager):
    """通知所有连接的客户端刷新房间列表"""
    payload = json.dumps({"type": "rooms_list", "rooms": manager.list_rooms()})
    for pid, client_ws in list(manager.connections.items()):
        if client_ws is not None and not client_ws.closed:
            try:
                await client_ws.send_str(payload)
            except Exception as e:
                print(f"_update_room_lobby send error for {pid}: {e}")


def _board_to_dict(board):
    """把棋盘转为可序列化格式"""
    result = {}
    for r in range(19):
        for c in range(19):
            p = board[r][c]
            if p:
                result[f"{r},{c}"] = {"color": p["color"], "type": p["type"]}
    return result


# ====== WebSocket Handler ======

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    player = None
    manager = request.app["manager"]

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("type") == "login":
                        player = await handle_message(ws, data, manager)
                    elif player:
                        await handle_message(ws, data, manager)
                except json.JSONDecodeError:
                    pass
            elif msg.type == web.WSMsgType.ERROR:
                print(f"WS error: {ws.exception()}")
    finally:
        if player:
            room = manager.get_player_room(player.id)
            manager.disconnect_player(player.id)
            if room and room.running:
                has_human = any(p.ws is not None for p in room.players)
                if not has_human:
                    # 没有人类玩家了，结束游戏
                    room.running = False
                    manager.rooms.pop(room.id, None)
                else:
                    for p in room.players:
                        if p.id != player.id and p.ws is not None:
                            try:
                                await p.ws.send_json({
                                    "type": "player_disconnected",
                                    "player_id": player.id,
                                    "player_name": player.name,
                                })
                            except Exception:
                                pass

    return ws


# ====== HTTP Static ======

# 启动时缓存 HTML/JS
_INDEX_HTML = open("./static/index.html", encoding="utf-8").read()

async def index_handler(request):
    return web.Response(text=_INDEX_HTML, content_type="text/html", charset="utf-8")


# ====== 获取局域网IP ======

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ====== 启动 ======

async def _js_handler(request):
    resp = web.FileResponse("./static/script.js")
    resp.content_type = "text/javascript"
    resp.charset = "utf-8"
    return resp

def main():
    app = web.Application()
    app["manager"] = RoomManager()

    app.router.add_get("/", index_handler)
    app.router.add_get("/static/script.js", _js_handler)
    app.router.add_static("/static/", path="./static", name="static")
    app.router.add_static("/music/", path="./music", name="music")
    app.router.add_get("/ws", ws_handler)

    port = 8888
    lan_ip = get_lan_ip()

    # 启动 AI 进程池（自动匹配 CPU 核心数）
    global _ai_executor
    _ai_executor = concurrent.futures.ProcessPoolExecutor(max_workers=4)

    print("=" * 50)
    print("  四国象棋 服务器已启动")
    print(f"  本机访问:  http://127.0.0.1:{port}")
    print(f"  局域网访问: http://{lan_ip}:{port}")
    print("  其他人用浏览器打开上述网址即可加入")
    print("  输入用户名即可进入，无需密码")
    print(f"  AI 进程池: 4 个并行工作进程")
    print("=" * 50)

    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
