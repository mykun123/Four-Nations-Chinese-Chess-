# 4-Player Xiangqi (四国象棋)

4-Player Xiangqi is a web-based multiplayer board game for four players, playable over LAN. Each player sits on one side of the board, taking turns in counter-clockwise order. Supports **Free-for-All**, **Team Battle**, and **Team Stratagem** modes — all modes support AI opponents.

![Free-for-All](image/game_ffa.png)
*Free-for-All mode: every player for themselves*

![Mobile](image/game_mobile.png)
*Mobile responsive layout*

## Game Modes

### Free-for-All (FFA)
Four players fight individually; the last survivor wins. Turn order: **Red → Green → Black → Blue**.

![Team Battle](image/game_team.png)
*Team Battle: 2v2 alliance mode*

### Team Battle
2v2 mode. Adjacent players form teams of two. A team wins when both members of the opposing team are eliminated. Teams are formed through the in-game alliance system at the start.

### Team Stratagem
Builds on Team Battle with a stratagem system. After forming alliances, each player chooses one of two stratagems; their ally automatically receives the other:

- **Resurrect (借尸还魂)** — Use on your turn to revive a Rook at a random empty position
- **Retreat (鸣金收兵)** — Use on your turn to recall all moved pieces back to their starting positions

![Stratagem Selection](image/game_stratagem.png)
*Stratagem selection interface*

Each stratagem can be used only once per game.

## Features

- **AI Opponents** — Minimax search with α-β pruning; add computer players to any empty seat
- **Parallel AI Processing** — AI search runs in a separate process pool, so multiple AI in different rooms think simultaneously without blocking each other
- **Reconnection** — Disconnect and reconnect to rejoin your game in progress
- **Undo System** — Request an undo after your move; teammates vote to approve
- **Auto-rotating View** — Each player always sees their own pieces at the bottom of the screen
- **Neutral Units** — Neutral pieces in the center of the board; capturing the neutral King grants a reward
- **Elimination Bonus** — When a player is eliminated, the killer gets a bonus Cannon randomly placed on the dead player's back rank
- **Voice Notifications** — Automatic TTS voice prompts on turn changes
- **Sound Effects & BGM** — Web Audio API generates move/capture sounds; background music support
- **Responsive Layout** — Works on desktop and mobile browsers with automatic screen adaptation

## Dependencies

- Python 3.8+
- [aiohttp](https://docs.aiohttp.org/) — Web server & WebSocket communication

All other code uses only the Python standard library.

## Quick Start

### 1. Install dependencies

```bash
pip install aiohttp
```

### 2. Start the server

```bash
cd xiangqi_game
python server.py
```

### 3. Open a browser

- Local access: `http://127.0.0.1:8888`
- LAN access: `http://<server-IP>:8888`

Enter a username and password to auto-register and log in.

### 4. Start a game

1. Click "Create Room" in the lobby
2. Select a game mode (Free-for-All / Team Battle / Team Stratagem)
3. Click "+ Add AI" on empty seats, or wait for friends to join
4. Once all 4 seats are filled, click "Start Game"

### 5. Expose to public internet (optional)

Use Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:8888
```

## Controls

- Click your own piece to see legal moves, then click a destination to move
- Gold dashed border on a piece indicates it belongs to you or your ally
- Stratagem icon appears below the player name (Stratagem mode); click to activate
- Turn times out after 30 seconds, at which point a random legal move is played

## File Structure

```
xiangqi_game/
├── server.py          # Web server + WebSocket handler
├── game_4p.py         # Core game logic (board, moves, win conditions)
├── ai_4p.py           # AI search engine (Minimax + α-β pruning)
├── ai_debug.log       # AI debug log
├── image/
│   ├── game_ffa.png
│   ├── game_team.png
│   ├── game_stratagem.png
│   └── game_mobile.png
├── static/
│   ├── index.html     # Frontend page
│   ├── style.css      # Stylesheet
│   └── script.js      # Frontend logic
├── README.md          # This file (English)
└── README-ch.md       # Chinese version
```

## Notes

- Accounts are auto-registered; just enter a username and password to log in
- In Team mode, the game starts automatically once any alliance is formed
- AI search depth can be adjusted via the `_MAX_DEPTH` constant in `ai_4p.py`
- Default port is 8888; change it in `server.py`
