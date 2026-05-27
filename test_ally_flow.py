"""Test team-mode ally phase start"""
import asyncio, json, aiohttp
from aiohttp import web
from server import ws_handler, RoomManager

async def test():
    app = web.Application()
    mgr = RoomManager()
    app["manager"] = mgr
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8890)
    await site.start()
    print("Server started")

    sessions = {}
    async def connect(name):
        s = aiohttp.ClientSession()
        ws = await s.ws_connect("http://127.0.0.1:8890/ws")
        await ws.send_json({"type": "login", "username": name})
        r = await ws.receive_json()
        assert r["type"] == "login_ok"
        uid = r["user_id"]
        r2 = await ws.receive_json()  # rooms_list
        sessions[name] = (s, ws)
        return uid

    async def recv(name, timeout=5):
        _, ws = sessions[name]
        return await asyncio.wait_for(ws.receive_json(), timeout=timeout)

    async def send(name, msg):
        _, ws = sessions[name]
        await ws.send_json(msg)

    ids = {}
    for n in ["A","B","C","D"]:
        ids[n] = await connect(n)
        print(f"{n} logged in")

    # A creates team room
    await send("A", {"type": "create_room", "user_id": ids["A"], "mode": "team"})
    r = await recv("A")
    print(f"A: {r['type']} (expected room_joined)")
    r = await recv("A")  # rooms_list
    rid = r.get("rooms", [{}])[0].get("id") if r.get("rooms") else None
    if not rid:
        # Try getting room id from the room_joined response
        pass
    rid = None

    # Re-read: get room ID from server state
    for room_id, room_obj in list(mgr.rooms.items()):
        if len(room_obj.players) == 1 and room_obj.players[0].id == ids["A"]:
            rid = room_id
            break

    print(f"Room ID: {rid}")

    # B joins
    await send("B", {"type": "join_room", "user_id": ids["B"], "room_id": rid})
    r = await recv("B")
    print(f"B: {r['type']} (expected room_joined)")
    r = await recv("B")  # rooms_list
    r = await recv("A")  # player_joined
    print(f"A: {r['type']} (expected player_joined)")

    # C joins
    await send("C", {"type": "join_room", "user_id": ids["C"], "room_id": rid})
    r = await recv("C")
    print(f"C: {r['type']} (expected room_joined)")
    r = await recv("C")  # rooms_list
    r = await recv("A")  # player_joined
    print(f"A: {r['type']} (expected player_joined)")
    r = await recv("B")
    print(f"B: {r['type']} (expected player_joined)")

    # D joins — triggers ally_phase_start in team mode
    print("\n--- D joining (team mode) ---")
    await send("D", {"type": "join_room", "user_id": ids["D"], "room_id": rid})

    print("Waiting for D's responses...")
    r = await recv("D")
    print(f"D: {r['type']} (expected room_joined)")

    # This should be ally_phase_start
    r = await recv("D")
    print(f"D: {r['type']} (expected ally_phase_start)")

    if r['type'] == 'ally_phase_start':
        print(f"  players: {len(r.get('players', []))}")
        print(f"  teams: {r.get('teams', [])}")
        print("SUCCESS: Ally phase started!")

    # Other players should also get ally_phase_start
    for n in ["A", "B", "C"]:
        r = await recv(n)
        print(f"{n}: {r['type']} (expected ally_phase_start)")

    # Cleanup
    await runner.cleanup()
    for s, ws in sessions.values():
        await ws.close()
        await s.close()
    print("\nTEST DONE")

asyncio.run(test())
