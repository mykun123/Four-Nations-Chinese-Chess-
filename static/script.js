// ====== 常量 ======
const CELL = 38, MX = 80, MY = 80;
const RED = 0, BLACK = 1, GREEN = 2, BLUE = 3, NEUTRAL = 4;
const TURN_ORDER = [RED, GREEN, BLACK, BLUE];

const COLOR_NAMES = {0:"红方",1:"黑方",2:"绿方",3:"蓝方",4:"中立"};
const COLOR_SHORT = {0:"红",1:"黑",2:"绿",3:"蓝",4:"中"};
const COLOR_RGB = {0:"#CC3333",1:"#B8860B",2:"#2E7D32",3:"#1565C0",4:"#888888"};
const PIECE_CHARS = {
  0: {K:"帅",A:"仕",B:"相",N:"马",R:"车",C:"炮",P:"兵"},
  1: {K:"将",A:"士",B:"象",N:"馬",R:"車",C:"砲",P:"卒"},
  2: {K:"将",A:"士",B:"象",N:"马",R:"车",C:"炮",P:"卒"},
  3: {K:"帅",A:"仕",B:"相",N:"馬",R:"車",C:"砲",P:"兵"},
  4: {K:"帅",A:"士",B:"相",N:"马",R:"车",C:"炮",P:"兵"},
};

// ====== 邻居关系（用于结盟） ======
const NEXT_PLAYER = {0: 2, 2: 1, 1: 3, 3: 0};  // 逆时针
const PREV_PLAYER = {0: 3, 2: 0, 1: 2, 3: 1};  // 顺时针

// ====== 状态 ======
let ws = null;
let userId = null;
let userName = "";
let userPassword = "";
let myColor = null;
let gameState = null;      // {board: {r,c:{color,type}}, ...}
let selectedPos = null;    // {r, c}
let legalMoves = [];       // [{r,c}, ...]
let lastMoves = {};        // {color: {fr,fc,tr,tc}} 每个玩家上一步轨迹
let isMyTurn = false;
let canvas, ctx;
let gamePlayers = [];      // 玩家列表，用于显示等待谁
let currentTurnColor = null; // 当前轮到谁
let playerView = 0;        // 棋盘朝向视角（默认RED）

// 各玩家视角的旋转角度（弧度）
const VIEW_ANGLES = {};
VIEW_ANGLES[RED] = 0;              // 不变
VIEW_ANGLES[GREEN] = -Math.PI / 2; // 左→下 (逆时针90°)
VIEW_ANGLES[BLACK] = Math.PI;       // 上→下 (180°)
VIEW_ANGLES[BLUE] = Math.PI / 2;    // 右→下 (顺时针90°)

// 结盟状态
let allyPlayers = [];       // [{id, name, color}, ...]
let allyInviteSent = null;  // {to, to_name} | null
let allyInviteFrom = null;  // {from, from_name} | null
let allyTeams = [];         // [{members: [{id,name}, {id,name}]}, ...]
let inviteCooldown = 0;     // 上次邀请时间戳（冷却用）
let colorTeams = {};        // {color: team_id} 组队模式下的队伍映射
let currentRoom = null;     // 当前房间信息

// 倒计时 & 悔棋
let turnTimer = null;
let lastMoverColor = null; // ä¸ä¸æ­¥èµ°å­çç©å®¶é¢è²
let timerSeconds = 0;

// 中立 AI 移动轨迹（用于轨迹绘制和弹窗）
let neutralMoveTrajectory = null;

// 锦囊（stratagem）模式
let myStratagem = null;       // 自己的锦囊 "resurrect"|"retreat"
let allyStratagem = null;     // 盟友的锦囊
let stratagemUsed = {};       // {color: bool} 哪些人已使用
let stratagemPending = false; // 是否正在选择中
let pendingUndo = false;  // 是否有待处理的悔棋

// ====== 音效系统（Web Audio API 生成，无需外部文件） ======
let audioCtx = null;

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function playCaptureSound() {
  try {
    const ctx = getAudioContext();
    const now = ctx.currentTime;
    // 低频冲击音
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "triangle";
    osc.frequency.setValueAtTime(200, now);
    osc.frequency.exponentialRampToValueAtTime(80, now + 0.15);
    gain.gain.setValueAtTime(0.55, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc.start(now);
    osc.stop(now + 0.25);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.type = "square";
    osc2.frequency.setValueAtTime(100, now);
    gain2.gain.setValueAtTime(0.2, now);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc2.start(now);
    osc2.stop(now + 0.15);
  } catch (e) { /* AudioContext 不可用时静默忽略 */ }
}

function playMoveSound() {
  try {
    const ctx = getAudioContext();
    const now = ctx.currentTime;
    // 短促的移动音效
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(800, now);
    osc.frequency.exponentialRampToValueAtTime(600, now + 0.06);
    gain.gain.setValueAtTime(0.25, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
    osc.start(now);
    osc.stop(now + 0.08);
  } catch (e) { /* AudioContext 不可用时静默忽略 */ }
}

// ====== 背景音乐（MP3 循环播放） ======
let bgmEnabled = true;
var bgmAudio = null;

function startBGM() {
  if (!bgmEnabled) return;
  if (bgmAudio) {
    try {
      bgmAudio.currentTime = 0;
      bgmAudio.play().catch(function(e) {});
    } catch(e) {}
  }
}

function stopBGM() {
  if (bgmAudio) {
    try { bgmAudio.pause(); } catch(e) {}
  }
}

function toggleBGM() {
  bgmEnabled = !bgmEnabled;
  var btn = document.getElementById("btn-bgm");
  if (btn) btn.textContent = bgmEnabled ? "🎵 音乐" : "🎵 音乐关";
  if (bgmEnabled && document.getElementById("page-game").style.display !== "none") {
    if (bgmAudio) startBGM();
  } else {
    stopBGM();
  }
}

// ====== 语音播报（TTS） ======
function speak(text) {
  try {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-CN";
    u.rate = 0.95;
    u.volume = 1;
    window.speechSynthesis.speak(u);
  } catch (e) { /* TTS 不可用时静默忽略 */ }
}

function speakTurn(playerName, isMe) {
  if (isMe) {
    speak("轮到你了");
  } else {
    speak("轮到" + (playerName || "") + "走子");
  }
}

// ====== 页面切换 ======
function showPage(id) {
  document.querySelectorAll(".page").forEach(p => p.style.display = "none");
  document.getElementById(id).style.display = "flex";
}

// ====== 登录 ======
function doLogin() {
  const name = document.getElementById("login-name").value.trim();
  const pwd = document.getElementById("login-password").value;
  if (!name) { document.getElementById("login-error").textContent = "请输入用户名"; return; }
  userName = name;
  userPassword = pwd;
  connectWebSocket(name, pwd);
}

// ====== 退出登录 ======
function doLogout() {
  if (ws) { ws.close(); ws = null; }
  localStorage.removeItem("xiangqi_username");
  localStorage.removeItem("xiangqi_password");
  userName = "";
  userPassword = "";
  userId = null;
  currentRoom = null;
  document.getElementById("login-error").textContent = "";
  document.getElementById("login-name").value = "";
  document.getElementById("login-password").value = "";
  showPage("page-login");
}

// ====== 倒计时 & 悔棋 ======
function getCornerByColor(color) {
  if (color === undefined || color === null) return null;
  const idx = TURN_ORDER.indexOf(playerView);
  const corners = ["bl", "tl", "tr", "br"];
  for (let i = 0; i < 4; i++) {
    if (TURN_ORDER[(idx + i) % 4] === color) return corners[i];
  }
  return null;
}

function updateTimerDisplay() {
  const el = document.getElementById("turn-timer");
  const sb = document.getElementById("status-bar");
  // 清空所有卡片计时
  const corners = ["bl", "tl", "tr", "br"];
  for (let i = 0; i < corners.length; i++) {
    const te = document.getElementById("ptimer-" + corners[i]);
    if (te) te.textContent = "";
  }
  if (timerSeconds <= 0) { el.textContent = ""; if (sb) sb.textContent = ""; return; }
  el.textContent = timerSeconds + "s";
  el.className = "turn-timer" + (timerSeconds <= 5 ? " urgent" : "");
  if (sb) sb.textContent = timerSeconds + "s";
  // 当前走子玩家卡片下显示倒计时
  if (currentTurnColor !== undefined && currentTurnColor !== null) {
    const corner = getCornerByColor(currentTurnColor);
    if (corner) {
      const te = document.getElementById("ptimer-" + corner);
      if (te) te.textContent = "（走子思考中：" + timerSeconds + "s）";
    }
  }
}

function startTimer(seconds) {
  if (turnTimer) clearInterval(turnTimer);
  timerSeconds = seconds || 30;
  updateTimerDisplay();
  turnTimer = setInterval(function() {
    timerSeconds--;
    updateTimerDisplay();
    if (timerSeconds <= 0) {
      clearInterval(turnTimer);
      turnTimer = null;
    }
  }, 1000);
}

function stopTimer() {
  if (turnTimer) { clearInterval(turnTimer); turnTimer = null; }
  timerSeconds = 0;
  updateTimerDisplay();
}

function requestUndo() {
  if (pendingUndo || lastMoverColor !== myColor) return;
  pendingUndo = true;
  ws.send(JSON.stringify({type: "undo_request", user_id: userId}));
  document.getElementById("btn-undo").disabled = true;
}

function sendUndoVote(vote) {
  ws.send(JSON.stringify({type: "undo_vote", user_id: userId, vote: vote}));
  document.getElementById("undo-overlay").style.display = "none";
}

// ====== WebSocket ======
function connectWebSocket(name, password) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    ws.send(JSON.stringify({type: "login", username: name, password: password || ""}));
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      handleMessage(msg);
    } catch(err) { console.error("Parse error:", e.data); }
  };

  ws.onclose = () => {
    if (document.getElementById("page-game").style.display !== "none") {
      document.getElementById("current-turn-display").textContent = "连接断开，请刷新页面";
    }
  };

  ws.onerror = () => {
    document.getElementById("login-error").textContent = "无法连接服务器";
  };
}

// ====== 消息处理 ======
function handleMessage(msg) {
  switch (msg.type) {
    case "login_ok":
      userId = msg.user_id;
      userName = msg.name;
      localStorage.setItem("xiangqi_username", userName);
      localStorage.setItem("xiangqi_password", userPassword);
      document.getElementById("lobby-user").textContent = "👤 " + msg.name;
      showPage("page-lobby");
      refreshRoomList();
      break;

    case "rooms_list":
    case "room_list":
      renderRoomList(msg.rooms || []);
      break;

    case "room_joined":
      showWaiting(msg.room);
      break;

    case "player_joined":
    case "room_updated":
      if (currentRoom) {
        currentRoom = msg.room;
        renderSeats(currentRoom);
      }
      if (msg.type === "player_joined") refreshRoomList();
      break;

    case "game_start":
      startGame(msg);
      break;

    case "legal_moves":
      legalMoves = msg.moves || [];
      drawBoard();
      break;

    case "turn_change":
      isMyTurn = (msg.color === myColor);
      currentTurnColor = msg.color;
      if (msg.is_ai) {
        // AI 回合 — 简单提示，不走计时
        stopTimer();
        var aiName = msg.player_name || "电脑";
        document.getElementById("current-turn-display").textContent = aiName + " 思考中...";
        document.getElementById("current-turn-display").className = "current-turn-text";
        document.getElementById("status-bar").textContent = aiName + " 思考中...";
      } else {
        updateStatus();
        showTurnNotification(msg.color, msg.player_name);
      }
      break;

    case "move_made":
      applyMove(msg);
      lastMoverColor = msg.color;
      pendingUndo = false;
      break;

    case "game_over":
      isMyTurn = false;
      lastMoverColor = null;
      lastMoves = {};
      myStratagem = null;
      allyStratagem = null;
      stratagemUsed = {};
      stratagemPending = false;
      document.getElementById("btn-end-game").style.display = "none";
      showGameOverDialog(msg);
      break;

    case "game_ended":
      isMyTurn = false;
      stopTimer();
      stopBGM();
      document.getElementById("btn-end-game").style.display = "none";
      showPage("page-lobby");
      refreshRoomList();
      break;

    case "neutral_moves":
      if (msg.moves) {
        for (const m of msg.moves) {
          const key_from = m.fr + "," + m.fc;
          const key_to = m.tr + "," + m.tc;
          // 中立吃子音效
          const captured = gameState ? gameState[key_to] : null;
          if (captured) playCaptureSound();
          const piece = gameState ? gameState[key_from] : null;
          if (piece) {
            delete gameState[key_from];
            gameState[key_to] = piece;
          }
        }
        // 重新绘制选中状态
        if (selectedPos) {
          ws.send(JSON.stringify({
            type: "get_moves", user_id: userId,
            r: selectedPos.r, c: selectedPos.c,
          }));
        } else {
          drawBoard();
        }
      }
      break;

    case "neutral_reward":
      playCaptureSound();
      document.getElementById("current-turn-display").textContent =
        `⚡ ${msg.player_name} 击杀了中立帅，获得一个车！`;
      break;

    case "board_sync":
      gameState = msg.board;
      selectedPos = null;
      legalMoves = [];
      drawBoard();
      break;

    case "ally_phase_start":
      startAllyPhase(msg);
      break;

    case "ally_invite":
      allyInviteFrom = {from: msg.from, from_name: msg.from_name};
      showInviteModal(msg.from, msg.from_name);
      break;

    case "ally_invite_sent":
      allyInviteSent = {to: msg.to, to_name: msg.to_name};
      renderAllyPanel();
      break;

    case "ally_declined":
      allyInviteSent = null;
      renderAllyPanel();
      break;

    case "ally_formed":
      allyTeams.push(msg.team);
      if (allyInviteSent && msg.team.members.some(m => m.id === userId)) {
        allyInviteSent = null;
      }
      if (allyInviteFrom) {
        if (msg.team.members.some(m => m.id === userId) ||
            msg.team.members.some(m => m.id === allyInviteFrom.from)) {
          allyInviteFrom = null;
          hideInviteModal();
        }
      }
      renderAllyPanel();
      break;

    case "ally_auto":
      allyTeams.push(msg.team);
      if (msg.team.members.some(m => m.id === userId)) {
        allyInviteSent = null;
        allyInviteFrom = null;
        hideInviteModal();
      }
      renderAllyPanel();
      break;

    case "ally_cancelled":
      allyInviteFrom = null;
      hideInviteModal();
      renderAllyPanel();
      break;

    case "stratagem_phase":
      stratagemPending = true;
      showStratagemSelection(msg);
      break;

    case "stratagem_ok":
      myStratagem = msg.choice;
      updateStratagemUI();
      break;

    case "stratagem_assigned":
      myStratagem = msg.choice;
      document.getElementById("stratagem-status").textContent = "盟友已选，你的锦囊被锁定为：" + (msg.choice === "resurrect" ? "借尸还魂" : "鸣金收兵");
      updateStratagemUI();
      break;

    case "stratagem_ready":
      myStratagem = msg.your_choice;
      allyStratagem = msg.ally_choice;
      stratagemUsed = {};
      stratagemPending = false;
      document.getElementById("stratagem-overlay").style.display = "none";
      break;

    case "stratagem_used":
      stratagemUsed[msg.color] = true;
      // 更新棋盘
      if (msg.board) {
        for (const key in msg.board) {
          const parts = key.split(",");
          const r = parseInt(parts[0]), c = parseInt(parts[1]);
          gameState[key] = msg.board[key];
          gameState[`${r},${c}`] = msg.board[key];
        }
      }
      drawBoard();
      // 显示通知
      var usedName = (gamePlayers.find(function(p) { return p.color === msg.color; }) || {}).name || COLOR_NAMES[msg.color];
      var stratName = msg.stratagem === "resurrect" ? "借尸还魂" : "鸣金收兵";
      var notifyEl = document.getElementById("stratagem-notify");
      if (notifyEl) {
        notifyEl.innerHTML = "⚡ " + usedName + " 使用了【" + stratName + "】";
        notifyEl.style.display = "block";
        setTimeout(function() { notifyEl.style.display = "none"; }, 4000);
      }
      break;

    case "error":
      if (document.getElementById("page-login").style.display !== "none" && document.getElementById("page-login").style.display !== "") {
        document.getElementById("login-error").textContent = "⚠ " + msg.message;
      } else if (document.getElementById("ally-panel").style.display === "block") {
        const list = document.getElementById("ally-player-list");
        list.innerHTML = `<div class="ally-error">⚠ ${msg.message}</div>`;
        setTimeout(() => renderAllyPanel(), 2000);
      } else {
        document.getElementById("current-turn-display").textContent = "⚠ " + msg.message;
      }
      break;

    case "turn_timeout":
      timerSeconds = 0;
      updateTimerDisplay();
      // 弹窗提示超时
      var oldColor = msg.color;
      var oldName = (gamePlayers && gamePlayers.find(function(p) { return p.color === oldColor; }));
      var statusMsg = (oldName ? oldName.name : COLOR_NAMES[oldColor]) + " 超时，已自动走子";
      document.getElementById("current-turn-display").textContent = statusMsg;
      currentTurnColor = msg.turn;
      isMyTurn = (msg.turn === myColor);
      updateStatus();
      break;

    case "neutral_notification":
        // 双重保障：同时更新棋盘
        if (gameState) {
          var __fromKey = msg.from_r + "," + msg.from_c;
          var __toKey = msg.to_r + "," + msg.to_c;
          var __pc = gameState[__fromKey];
          if (__pc) { delete gameState[__fromKey]; gameState[__toKey] = __pc; }
        }
        neutralMoveTrajectory = {
          fr: msg.from_r, fc: msg.from_c,
          tr: msg.to_r, tc: msg.to_c,
          piece_type: msg.piece_type,
        };
        showNeutralNotification(msg);
        drawBoard();
        break;

    case "undo_vote_request":
      document.getElementById("undo-overlay").style.display = "flex";
      document.getElementById("undo-vote-hint").textContent = msg.requester_name + " 请求悔棋";
      break;

    case "undo_accepted":
      document.getElementById("undo-overlay").style.display = "none";
      document.getElementById("current-turn-display").textContent = "✅ 悔棋成功";
      break;

    case "undo_rejected":
      document.getElementById("undo-overlay").style.display = "none";
      document.getElementById("current-turn-display").textContent = "悔棋被拒绝";
      break;

    case "player_disconnected":
      document.getElementById("current-turn-display").textContent = `⚠ ${msg.player_name} 断线了`;
      setTimeout(() => updateStatus(), 4000);
      break;

    case "player_reconnected":
      document.getElementById("current-turn-display").textContent = `✅ ${msg.player_name} 重新连接`;
      setTimeout(() => updateStatus(), 4000);
      break;
  }
}

// ====== 大厅 ======
function createRoom() {
  const mode = document.getElementById("room-mode").value;
  ws.send(JSON.stringify({type: "create_room", user_id: userId, mode}));
}

function joinRoom(rid) {
  ws.send(JSON.stringify({type: "join_room", user_id: userId, room_id: rid}));
}

function refreshRoomList() {
  ws.send(JSON.stringify({type: "list_rooms", user_id: userId}));
}

function renderRoomList(rooms) {
  const el = document.getElementById("room-list");
  if (rooms.length === 0) {
    el.innerHTML = '<div class="empty-msg">暂无房间，点击上方创建</div>';
    return;
  }
  el.innerHTML = rooms.map(r => `
    <div class="room-item">
      <span class="room-mode">${r.mode === "ffa" ? "自由" : r.mode === "team_stratagem" ? "锦囊" : "组队"}</span>
      <span style="flex:1;font-size:13px;color:#b8956a;padding:0 8px">房间 ${r.id}</span>
      <span class="room-players">${r.count}/4 人</span>
      <button onclick="joinRoom('${r.id}')">加入</button>
    </div>
  `).join("");
}

function showWaiting(room) {
  currentRoom = room;
  document.getElementById("room-id-display").textContent = room.id || "";
  var modeNames = {"ffa":"自由对战","team":"组队对战","team_stratagem":"组队对战（锦囊）"};
  document.getElementById("room-mode-display").textContent = modeNames[room.mode] || room.mode;
  renderSeats(room);
  showPage("room-waiting");
}

function renderSeats(room) {
  const seats = room.players || [];
  for (let i = 0; i < 4; i++) {
    const seat = seats.find(function(p) { return p.seat === i; });
    const el = document.getElementById("seat-" + i);
    const nameEl = document.getElementById("seat-name-" + i);
    const readyEl = document.getElementById("seat-ready-" + i);
    const actionsEl = document.getElementById("seat-actions-" + i);
    if (seat) {
      el.className = "seat occupied";
      if (seat.is_ai) {
        nameEl.textContent = seat.name + " 🤖";
        readyEl.textContent = "已加入";
        if (actionsEl) {
          actionsEl.innerHTML = '<button class="btn-remove-ai" onclick="removeAIPlayer(\'' + seat.id + '\')">移除</button>';
        }
      } else {
        nameEl.textContent = seat.name;
        readyEl.textContent = "已加入";
        if (actionsEl) actionsEl.innerHTML = "";
      }
    } else {
      el.className = "seat";
      nameEl.textContent = "等待加入...";
      readyEl.textContent = "";
      if (actionsEl) {
        actionsEl.innerHTML = '<button class="btn-add-ai" onclick="addAIPlayer(' + i + ')">+ 添加电脑</button>';
      }
    }
  }
  // 满人时显示开始按钮
  var startBtn = document.getElementById("btn-start-game");
  if (startBtn) {
    startBtn.style.display = (seats.length >= 4) ? "inline-block" : "none";
  }
}

function addAIPlayer(seatIndex) {
  ws.send(JSON.stringify({type: "add_ai", user_id: userId, seat_index: seatIndex}));
}

function removeAIPlayer(aiId) {
  ws.send(JSON.stringify({type: "remove_ai", user_id: userId, ai_id: aiId}));
}

function requestStartGame() {
  ws.send(JSON.stringify({type: "start_game_request", user_id: userId}));
}

function leaveRoom() {
  ws.send(JSON.stringify({type: "leave_room", user_id: userId}));
  currentRoom = null;
  document.getElementById("ally-panel").style.display = "none";
  showPage("page-lobby");
  refreshRoomList();
}

// ====== 游戏开始 ======
function startGame(msg) {
  myColor = msg.your_color;
  gameState = msg.board_state || {};
  selectedPos = null;
  legalMoves = [];
  lastMoves = {};
  neutralMoveTrajectory = null;
  isMyTurn = (msg.turn !== undefined ? msg.turn : msg.turn_order[0]) === myColor;
  gamePlayers = msg.players || [];
  currentTurnColor = msg.turn !== undefined ? msg.turn : (msg.turn_order || [])[0];
  playerView = myColor; // 视角设为自己的颜色
  colorTeams = msg.color_teams || {};

  currentRoom = null;
  document.getElementById("ally-panel").style.display = "none";
  showPage("page-game");

  // 设置画布
  canvas = document.getElementById("board-canvas");
  canvas.width = MX * 2 + 18 * CELL;
  canvas.height = MY * 2 + 18 * CELL;
  ctx = canvas.getContext("2d");

  // 锦囊初始化
  if (msg.stratagems) {
    myStratagem = msg.stratagems[myColor];
    stratagemUsed = msg.stratagem_used || {};
    // 查找盟友颜色
    if (colorTeams && Object.keys(colorTeams).length > 0) {
      var myTeamId = colorTeams[myColor];
      for (var colStr in colorTeams) {
        var col = parseInt(colStr);
        if (col !== myColor && colorTeams[col] === myTeamId) {
          allyStratagem = msg.stratagems[col];
          break;
        }
      }
    }
  } else {
    myStratagem = null;
    allyStratagem = null;
  }

  // 玩家标签
  const modeText = msg.mode === "ffa" ? "自由对战" : (msg.mode === "team_stratagem" ? "组队对战（锦囊）" : "组队对战");
  document.getElementById("game-info").textContent =
    `${modeText} | 你是 ${COLOR_NAMES[myColor]}`;

  setPlayerTags(msg.players);
  // 组队模式：通知盟友
  if (msg.mode === "team" && colorTeams && Object.keys(colorTeams).length > 0) {
    const myTeam = colorTeams[myColor];
    if (myTeam !== undefined) {
      for (const colStr of Object.keys(colorTeams)) {
        const col = parseInt(colStr);
        if (col !== myColor && colorTeams[col] === myTeam) {
          const ally = gamePlayers.find(p => p.color === col);
          const allyName = ally ? ally.name : COLOR_NAMES[col];
          showAllyNotification(allyName);
          speak("你的盟友是" + allyName);
          break;
        }
      }
    }
  }
  // 显示结束游戏按钮
  document.getElementById("btn-end-game").style.display = "";
  updateStatus();

  // 绘制棋盘
  drawBoard();

  // 点击事件
  canvas.addEventListener("pointerdown", handleCanvasClick);
  // 启动背景音乐
  startBGM();
}

function getAvatarChar(name) {
  return name ? name.charAt(0) : "?";
}

function setPlayerTags(players) {
  const idx = TURN_ORDER.indexOf(playerView);
  const p = TURN_ORDER;
  // corner顺序: bl(自己/左下), tl(左边/左上), tr(对面/右上), br(右边/右下)
  const corners = ["bl", "tl", "tr", "br"];
  // 固定位置（百分比，适配画布缩放）
  const pos = { bl: {x:20.38,y:85.55}, tl: {x:15.64,y:20.38}, tr: {x:80.81,y:15.64}, br: {x:85.55,y:80.81} };
  for (const c of corners) {
    const el = document.getElementById("player-card-" + c);
    if (el) { el.style.left = pos[c].x + "%"; el.style.top = pos[c].y + "%"; }
  }

  function renderCard(corner, color) {
    const card = document.getElementById("player-card-" + corner);
    if (!card) return;
    const pl = players && players.find(pl => pl.color === color);
    const name = pl ? pl.name : COLOR_SHORT[color] + "方";
    const rgb = COLOR_RGB[color];
    let suffix = "";
    if (myColor !== null && colorTeams && Object.keys(colorTeams).length > 0) {
      const myTeam = colorTeams[myColor];
      const pTeam = colorTeams[color];
      if (color === myColor) suffix = " (我)";
      else if (myTeam !== undefined && pTeam !== undefined && pTeam === myTeam) suffix = " (盟友)";
    } else if (color === myColor) {
      suffix = " (我)";
    }
    var aiBadge = (pl && pl.is_ai) ? '<span class="ai-badge">电脑</span>' : '';
    card.innerHTML =
      '<div class="p-avatar" style="border-color:' + rgb + ';color:' + rgb + '">' +
      getAvatarChar(name) + '</div>' +
      '<div style="display:flex;flex-direction:column">' +
      '<span class="p-name" style="color:' + rgb + '">' + name + suffix + aiBadge + '</span>' +
      '<span class="p-timer" id="ptimer-' + corner + '"></span>' +
      '<span class="stratagem-icon" id="sgicon-' + corner + '"></span>' +
      '</div>';
  }

  for (let i = 0; i < 4; i++) {
    renderCard(corners[i], p[(idx + i) % 4]);
  }
  // 更新锦囊图标
  updateStratagemIcons();
}

// ====== 锦囊（stratagem）相关 ======
var STRATAGEM_NAMES = { resurrect: "借尸还魂", retreat: "鸣金收兵" };
var STRATAGEM_COLORS = { resurrect: "#4caf50", retreat: "#ff9800" };

function showStratagemSelection(msg) {
  document.getElementById("stratagem-overlay").style.display = "flex";
  document.getElementById("stratagem-status").textContent = "请选择一种锦囊...";
  var cards = document.querySelectorAll(".stratagem-card");
  for (var i = 0; i < cards.length; i++) {
    cards[i].className = "stratagem-card";
  }
}

function selectStratagem(choice) {
  if (!stratagemPending) return;
  ws.send(JSON.stringify({type: "stratagem_select", user_id: userId, choice: choice}));
  var cards = document.querySelectorAll(".stratagem-card");
  for (var i = 0; i < cards.length; i++) {
    cards[i].className = "stratagem-card disabled";
  }
  document.getElementById("stratagem-status").textContent = "已选择 " + STRATAGEM_NAMES[choice] + "，等待其他玩家...";
}

function updateStratagemUI() {
  if (myStratagem) {
    var cards = document.querySelectorAll(".stratagem-card");
    for (var i = 0; i < cards.length; i++) {
      cards[i].className = "stratagem-card disabled";
    }
    document.getElementById("stratagem-status").textContent = "你的锦囊：" + STRATAGEM_NAMES[myStratagem];
  }
}

function updateStratagemIcons() {
  if (!myStratagem) return;
  var idx = TURN_ORDER.indexOf(playerView);
  var corners = ["bl", "tl", "tr", "br"];
  for (var i = 0; i < 4; i++) {
    var color = TURN_ORDER[(idx + i) % 4];
    var el = document.getElementById("sgicon-" + corners[i]);
    if (!el) continue;
    var sg = null;
    if (color === myColor) {
      sg = myStratagem;
    } else if (allyStratagem && colorTeams && colorTeams[myColor] !== undefined && colorTeams[color] === colorTeams[myColor]) {
      sg = allyStratagem;
    }
    if (sg) {
      var used = stratagemUsed && stratagemUsed[color];
      var name = STRATAGEM_NAMES[sg] || sg;
      var bg = STRATAGEM_COLORS[sg] || "#888";
      el.textContent = used ? "✗ " + name : "⚡" + name;
      el.style.borderColor = used ? "#666" : bg;
      el.style.color = used ? "#666" : bg;
      el.style.display = "inline-block";
      el.className = "stratagem-icon" + (used ? " used" : "");
      if (color === myColor && isMyTurn && !used) {
        el.className = "stratagem-icon clickable";
        el.style.pointerEvents = "auto";
        el.title = "点击使用【" + name + "】";
        el.onclick = function(sg) {
          return function() { useStratagem(sg); };
        }(sg);
      } else {
        el.style.pointerEvents = "";
        el.onclick = null;
      }
    } else {
      el.textContent = "";
      el.style.display = "none";
      el.onclick = null;
    }
  }
}

function useStratagem(sg) {
  if (!isMyTurn) return;
  if (stratagemUsed && stratagemUsed[myColor]) return;
  if (!confirm("确定使用【" + STRATAGEM_NAMES[sg] + "】吗？只能使用一次。")) return;
  ws.send(JSON.stringify({type: "use_stratagem", user_id: userId}));
}

function updateStatus() {
  const undoBtn = document.getElementById("btn-undo");
  const turnDisplay = document.getElementById("current-turn-display");
  const statusBar = document.getElementById("status-bar");
  
  // ææç©å®¶é½çå°åè®¡æ¶
  startTimer(30);
  
  // ææ£æé®æ»æ¯å¯è§ï¼ä½åªæåèµ°å®çäººå¯ç¨
  const canUndo = (lastMoverColor !== null && lastMoverColor === myColor && !pendingUndo);
  undoBtn.disabled = !canUndo;
  undoBtn.style.opacity = canUndo ? "1" : "0.4";
  undoBtn.style.cursor = canUndo ? "pointer" : "not-allowed";
  undoBtn.style.display = "inline-block";
  
  if (isMyTurn) {
    turnDisplay.textContent = `ä½ çåå`;
    turnDisplay.className = "current-turn-text my-turn";
    if (statusBar) statusBar.textContent = `è½®å°ä½ äº (${COLOR_NAMES[myColor]})`;
  } else {
    const turnColor = currentTurnColor;
    let waitName = "å¶ä»ç©å®¶";
    if (turnColor !== undefined && gamePlayers.length > 0) {
      const pl = gamePlayers.find(p => p.color === turnColor);
      if (pl) waitName = pl.name;
    }
    turnDisplay.textContent = `ç­å¾ ${waitName}`;
    turnDisplay.className = "current-turn-text";
    if (statusBar) statusBar.textContent = `ç­å¾ ${waitName}`;
  }
  // 锦囊图标随回合刷新（点击状态）
  updateStratagemIcons();
}

// ====== Canvas 绘制 ======
function drawBoard() {
  if (!ctx) return;
  const p = ctx;
  const W = canvas.width, H = canvas.height;

  // 背景（不旋转）
  p.fillStyle = "#2c1810";
  p.fillRect(0, 0, W, H);

  // 棋盘内容旋转
  ctx.save();
  ctx.translate(W / 2, H / 2);
  ctx.rotate(VIEW_ANGLES[playerView] || 0);
  ctx.translate(-W / 2, -H / 2);

  // 棋盘底色
  p.fillStyle = "#3d2415";
  p.fillRect(10, 10, W - 20, H - 20);

  // 网格线
  p.strokeStyle = "#C49A6C";
  p.lineWidth = 1.5;

  // 水平线段
  for (let r = 0; r < 19; r++) {
    for (let c = 0; c < 18; c++) {
      if (inBlank(r, c) || inBlank(r, c + 1)) continue;
      if (r >= 6 && r <= 12 && c === 4) continue;
      if (r >= 6 && r <= 12 && c === 13) continue;
      const x1 = MX + c * CELL, x2 = MX + (c + 1) * CELL;
      const y = MY + r * CELL;
      p.beginPath(); p.moveTo(x1, y); p.lineTo(x2, y); p.stroke();
    }
  }

  // 垂直线段
  for (let r = 0; r < 18; r++) {
    for (let c = 0; c < 19; c++) {
      if (inBlank(r, c) || inBlank(r + 1, c)) continue;
      if (c >= 6 && c <= 12 && r === 4) continue;
      if (c >= 6 && c <= 12 && r === 13) continue;
      const x = MX + c * CELL;
      const y1 = MY + r * CELL, y2 = MY + (r + 1) * CELL;
      p.beginPath(); p.moveTo(x, y1); p.lineTo(x, y2); p.stroke();
    }
  }

  // 九宫斜线
  p.strokeStyle = "#C49A6C";
  p.lineWidth = 1.5;
  const palaces = [[0,2,8,10],[16,18,8,10],[8,10,0,2],[8,10,16,18]];
  for (const [r1,r2,c1,c2] of palaces) {
    p.beginPath(); p.moveTo(MX+c1*CELL, MY+r1*CELL); p.lineTo(MX+c2*CELL, MY+r2*CELL); p.stroke();
    p.beginPath(); p.moveTo(MX+c2*CELL, MY+r1*CELL); p.lineTo(MX+c1*CELL, MY+r2*CELL); p.stroke();
  }

  // 楚河汉界（反旋转以保持可读）
  const rotAngle = VIEW_ANGLES[playerView] || 0;
  function drawRotatedText(text, x, y) {
    if (rotAngle !== 0) {
      p.save();
      p.translate(x, y);
      p.rotate(-rotAngle);
      p.textAlign = "center";
      p.textBaseline = "middle";
      p.fillText(text, 0, 0);
      p.restore();
    } else {
      p.fillText(text, x, y);
    }
  }

  p.fillStyle = "#8B6914";
  p.font = "bold 13px SimSun, serif";
  drawRotatedText("楚  河", MX + 9 * CELL, MY + 4 * CELL + CELL/2);
  drawRotatedText("汉  界", MX + 9 * CELL, MY + 13 * CELL + CELL/2);

  p.font = "bold 11px SimSun, serif";
  drawRotatedText("楚", MX + 4 * CELL + CELL/2, MY + 7 * CELL);
  drawRotatedText("河", MX + 4 * CELL + CELL/2, MY + 9 * CELL);
  drawRotatedText("汉", MX + 13 * CELL + CELL/2, MY + 7 * CELL);
  drawRotatedText("界", MX + 13 * CELL + CELL/2, MY + 9 * CELL);

  // 高亮（在棋子下层）
  drawHighlights(p);

  // 绘制棋子
  drawPieces(p);

  ctx.restore();
}

function inBlank(r, c) {
  return (r <= 4 && c <= 4) || (r <= 4 && c >= 14) ||
         (r >= 14 && c <= 4) || (r >= 14 && c >= 14);
}

function drawPieces(p) {
  const R = 15;
  for (let r = 0; r < 19; r++) {
    for (let c = 0; c < 19; c++) {
      const key = r + "," + c;
      const piece = gameState ? gameState[key] : null;
      if (!piece) continue;
      const x = MX + c * CELL, y = MY + r * CELL;
      const col = piece.color;
      const rgb = COLOR_RGB[col];
      const char = PIECE_CHARS[col]?.[piece.type] || "?";

      // 阵营标记：只在队友（自己+盟友）的棋子上显示花边
      let showTeamBorder = false;
      if (colorTeams && Object.keys(colorTeams).length > 0 && myColor !== null) {
        const myTeam = colorTeams[myColor];
        const pieceTeam = colorTeams[col];
        if (myTeam !== undefined && pieceTeam !== undefined && pieceTeam === myTeam) {
          showTeamBorder = true;
        }
      }

      // 投影
      p.fillStyle = "#333";
      p.beginPath(); p.arc(x+1, y+1, R, 0, Math.PI*2); p.fill();

      // 深色外边框（加深棋子轮廓）
      p.strokeStyle = "#1a0e08";
      p.lineWidth = 3;
      p.beginPath(); p.arc(x, y, R, 0, Math.PI*2); p.stroke();

      // 本体（颜色边框）
      p.strokeStyle = rgb;
      p.lineWidth = 1.5;
      p.fillStyle = "#F5F5DC";
      p.beginPath(); p.arc(x, y, R, 0, Math.PI*2); p.fill();
      p.stroke();

      // 内圈（颜色边框）
      p.strokeStyle = rgb;
      p.lineWidth = 1.5;
      p.beginPath(); p.arc(x, y, R-3, 0, Math.PI*2); p.stroke();

      // 队友花边：金色虚线外圈 + 菱形装饰
      if (showTeamBorder) {
        // 金色虚线外圈
        p.strokeStyle = "#FFD700";
        p.lineWidth = 2;
        p.setLineDash([3, 3]);
        p.beginPath(); p.arc(x, y, R+3, 0, Math.PI*2); p.stroke();
        p.setLineDash([]);

        // 四个角的菱形装饰
        const d = 4, off = R + 1;
        const pts = [[0, -off], [off, 0], [0, off], [-off, 0]];
        p.fillStyle = "#FFD700";
        for (const [dx, dy] of pts) {
          p.beginPath();
          p.moveTo(x + dx, y + dy - d);
          p.lineTo(x + dx + d, y + dy);
          p.lineTo(x + dx, y + dy + d);
          p.lineTo(x + dx - d, y + dy);
          p.closePath();
          p.fill();
        }
      }

      // 文字（反旋转，保持正向可读）
      p.save();
      p.translate(x, y);
      p.rotate(-(VIEW_ANGLES[playerView] || 0));
      p.fillStyle = rgb;
      p.font = "bold 11px SimSun, serif";
      p.textAlign = "center";
      p.textBaseline = "middle";
      p.fillText(char, 0, 0);
      p.restore();
    }
  }
}

function drawHighlights(p) {
  const R = 15;
  const LW = 10;          // 线宽
  const COLOR_ALLY = "#FFD700";
  const COLOR_ENEMY = "#CC3333";

  // 收集所有轨迹（附带颜色信息）
  const allMoves = [];
  const moveColors = Object.keys(lastMoves);
  for (let i = 0; i < moveColors.length; i++) {
    const color = parseInt(moveColors[i]);
    const move = lastMoves[color];
    if (!move) continue;
    let isAlly = false;
    if (myColor !== null && colorTeams && Object.keys(colorTeams).length > 0) {
      const myTeam = colorTeams[myColor];
      const moveTeam = colorTeams[color];
      if (myTeam !== undefined && moveTeam !== undefined && moveTeam === myTeam) {
        isAlly = true;
      }
    }
    allMoves.push({fr: move.fr, fc: move.fc, tr: move.tr, tc: move.tc, isAlly: isAlly});
  }
  if (neutralMoveTrajectory) {
    allMoves.push({fr: neutralMoveTrajectory.fr, fc: neutralMoveTrajectory.fc,
                   tr: neutralMoveTrajectory.tr, tc: neutralMoveTrajectory.tc, isAlly: false});
  }

  for (let i = 0; i < allMoves.length; i++) {
    const m = allMoves[i];
    const x1 = MX + m.fc * CELL, y1 = MY + m.fr * CELL;
    const x2 = MX + m.tc * CELL, y2 = MY + m.tr * CELL;
    const color = m.isAlly ? COLOR_ALLY : COLOR_ENEMY;

    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx*dx + dy*dy);
    if (len <= 1) continue;

    const nx = dx / len, ny = dy / len;
    const off = Math.min(R + 2, len * 0.35);
    const sx = x1 + nx * off, sy = y1 + ny * off;
    const ex = x2 - nx * off, ey = y2 - ny * off;

    // 双层线：外层实色，内层半透明
    p.strokeStyle = color;
    p.lineCap = "butt";
    p.lineWidth = LW;
    p.globalAlpha = 1.0;
    p.beginPath(); p.moveTo(sx, sy); p.lineTo(ex, ey); p.stroke();
    p.lineWidth = LW * 0.5;
    p.globalAlpha = 0.25;
    p.beginPath(); p.moveTo(sx, sy); p.lineTo(ex, ey); p.stroke();
    p.globalAlpha = 1;
  }

  // 选中
  if (selectedPos) {
    const x = MX + selectedPos.c * CELL, y = MY + selectedPos.r * CELL;
    p.fillStyle = "rgba(76, 175, 80, 0.4)";
    p.beginPath(); p.arc(x, y, R, 0, Math.PI*2); p.fill();
    p.strokeStyle = "#4CAF50";
    p.lineWidth = 2;
    p.stroke();
  }

  // 合法走法
  for (const m of legalMoves) {
    const x = MX + m.c * CELL, y = MY + m.r * CELL;
    const key = m.r + "," + m.c;
    const target = gameState ? gameState[key] : null;
    if (target) {
      p.fillStyle = "rgba(255, 87, 34, 0.4)";
      p.beginPath(); p.arc(x, y, R, 0, Math.PI*2); p.fill();
      p.strokeStyle = "#FF5722";
      p.lineWidth = 2;
      p.stroke();
    } else {
      p.fillStyle = "rgba(76, 175, 80, 0.6)";
      p.beginPath(); p.arc(x, y, 4, 0, Math.PI*2); p.fill();
    }
  }
}

// ====== 点击处理 ======
function handleCanvasClick(e) {
  if (!isMyTurn) return;

  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const px = (e.clientX - rect.left) * scaleX;
  const py = (e.clientY - rect.top) * scaleY;

  // 根据视角旋转反向转换点击坐标
  const angle = VIEW_ANGLES[playerView] || 0;
  let px2 = px, py2 = py;
  if (angle !== 0) {
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const dx = px - cx, dy = py - cy;
    const cos = Math.cos(-angle), sin = Math.sin(-angle);
    px2 = cx + dx * cos - dy * sin;
    py2 = cy + dx * sin + dy * cos;
  }
  const col = Math.round((px2 - MX) / CELL);
  const row = Math.round((py2 - MY) / CELL);

  if (row < 0 || row >= 19 || col < 0 || col >= 19) return;
  if (inBlank(row, col)) return;

  const dist = Math.sqrt((px2 - (MX + col * CELL)) ** 2 + (py2 - (MY + row * CELL)) ** 2);
  if (dist > CELL * 0.6) return;

  const key = row + "," + col;
  const clicked = gameState ? gameState[key] : null;

  // 选自己的棋子 — 向服务端请求合法走法
  if (clicked && clicked.color === myColor) {
    selectedPos = {r: row, c: col};
    ws.send(JSON.stringify({
      type: "get_moves", user_id: userId,
      r: row, c: col,
    }));
    drawBoard();
    return;
  }

  // 走子
  if (selectedPos) {
    ws.send(JSON.stringify({
      type: "move", user_id: userId,
      fr: selectedPos.r, fc: selectedPos.c,
      tr: row, tc: col,
    }));
    selectedPos = null;
    legalMoves = [];
  }
}

// ====== 应用走子 ======
function applyMove(msg) {
  const key_from = msg.fr + "," + msg.fc;
  const key_to = msg.tr + "," + msg.tc;
  // 检测吃子并播放音效
  const captured = gameState ? gameState[key_to] : null;
  if (captured) {
    playCaptureSound();
  } else {
    playMoveSound();
  }
  const piece = gameState ? gameState[key_from] : null;
  if (piece) {
    delete gameState[key_from];
    gameState[key_to] = piece;
  }
  // 清除中立移动轨迹（新的走子覆盖后不再显示）
  neutralMoveTrajectory = null;
  lastMoves[msg.color] = {fr: msg.fr, fc: msg.fc, tr: msg.tr, tc: msg.tc};
  selectedPos = null;
  legalMoves = [];
  drawBoard();
}

// ====== 退出游戏 ======
function leaveGame() {
  ws.send(JSON.stringify({type: "leave_room", user_id: userId}));
  stopBGM();
  currentRoom = null;
  document.getElementById("ally-panel").style.display = "none";
  showPage("page-lobby");
  refreshRoomList();
}

// ====== 结盟系统 ======
function startAllyPhase(msg) {
  allyPlayers = msg.players || [];
  allyInviteSent = null;
  allyInviteFrom = null;
  allyTeams = msg.teams || [];
  inviteCooldown = 0;
  document.getElementById("ally-panel").style.display = "block";
  renderAllyPanel();
}

function sendAllyInvite(targetId) {
  const now = Date.now();
  if (now - inviteCooldown < 2000) {
    return;
  }
  inviteCooldown = now;
  ws.send(JSON.stringify({type: "ally_invite", user_id: userId, target_id: targetId}));
}

function acceptAllyInvite(inviterId) {
  ws.send(JSON.stringify({type: "ally_accept", user_id: userId, inviter_id: inviterId}));
}

function declineAllyInvite(inviterId) {
  ws.send(JSON.stringify({type: "ally_decline", user_id: userId, inviter_id: inviterId}));
  allyInviteFrom = null;
  hideInviteModal();
  renderAllyPanel();
}

function cancelAllyInvite() {
  if (allyInviteSent) {
    ws.send(JSON.stringify({type: "ally_cancel", user_id: userId}));
    allyInviteSent = null;
    renderAllyPanel();
  }
}

function renderAllyPanel() {
  const me = allyPlayers.find(p => p.id === userId);
  if (!me) return;

  const leftColor = PREV_PLAYER[me.color];
  const rightColor = NEXT_PLAYER[me.color];
  const leftPlayer = allyPlayers.find(p => p.color === leftColor);
  const rightPlayer = allyPlayers.find(p => p.color === rightColor);
  const myTeam = allyTeams.find(t => t.members.some(m => m.id === userId));

  function renderNeighbor(neighbor, sideLabel) {
    if (!neighbor) return '';
    const nid = neighbor.id;
    const inMyTeam = myTeam && myTeam.members.some(m => m.id === nid);
    const inOtherTeam = !inMyTeam && allyTeams.some(t => t.members.some(m => m.id === nid));
    const invitedByMe = allyInviteSent && allyInviteSent.to === nid;
    const invitingMe = allyInviteFrom && allyInviteFrom.from === nid;

    let h = `<div class="ally-player-row">`;
    h += `<span class="ally-player-name" style="color:${COLOR_RGB[neighbor.color]}">${sideLabel} ${neighbor.name}</span>`;

    if (inMyTeam) {
      h += `<span class="ally-status allied">✓ 已结盟</span>`;
    } else if (inOtherTeam) {
      h += `<span class="ally-status">已有盟友</span>`;
    } else if (invitedByMe) {
      h += `<span class="ally-status">等待回应...</span>`;
      h += `<button class="ally-btn ally-btn-cancel" onclick="cancelAllyInvite()">取消</button>`;
    } else if (invitingMe) {
      h += `<span class="ally-status">请在弹窗中选择</span>`;
    } else {
      const onCooldown = (Date.now() - inviteCooldown) < 2000;
      const btnDisabled = onCooldown ? 'disabled' : '';
      const btnText = onCooldown ? '冷却中...' : '邀请结盟';
      h += `<button class="ally-btn ally-btn-invite" onclick="sendAllyInvite('${nid}')" ${btnDisabled}>${btnText}</button>`;
      if (onCooldown) {
        setTimeout(() => renderAllyPanel(), 2100);
      }
    }
    h += `</div>`;
    return h;
  }

  let html = renderNeighbor(leftPlayer, '← 左邻');
  html += renderNeighbor(rightPlayer, '→ 右邻');
  document.getElementById("ally-player-list").innerHTML = html;
  document.getElementById("ally-notification").style.display = 'none';
}

// ====== 中立移动弹窗（右上角）======
function showNeutralNotification(msg) {
  const existing = document.getElementById("neutral-move-popup");
  if (existing) existing.remove();

  const chars = {K:"帅",A:"仕",B:"相",N:"马",R:"车",C:"炮",P:"兵"};
  const pChar = chars[msg.piece_type] || msg.piece_type;

  const div = document.createElement("div");
  div.id = "neutral-move-popup";
  div.className = "board-popup-tr";
  div.innerHTML = `⚔ ${pChar} (${msg.from_r},${msg.from_c})→(${msg.to_r},${msg.to_c})`;
  document.querySelector(".board-wrap").appendChild(div);

  setTimeout(function() {
    const el = document.getElementById("neutral-move-popup");
    if (el) el.remove();
  }, 1500);
}

// ====== 游戏结束弹窗 ======
function showGameOverDialog(msg) {
  const names = msg.winner_names || msg.winners.map(c => COLOR_NAMES[c]);
  const overlay = document.getElementById("gameover-modal");
  if (overlay) overlay.remove();

  const isWinner = msg.winners && msg.winners.includes(myColor);
  const titleText = isWinner ? "🎉 你赢了！" : "💀 游戏结束";

  const div = document.createElement("div");
  div.className = "modal-overlay";
  div.id = "gameover-modal";
  div.innerHTML =
    '<div class="modal-box">' +
    '<div class="modal-invite-text" style="font-size:28px">' + titleText + '</div>' +
    '<div class="modal-hint" style="font-size:20px;margin:16px 0;color:#FFD700">' +
    names.join(" & ") + ' 获胜！</div>' +
    '<div class="modal-buttons">' +
    '<button class="ally-btn ally-btn-accept" onclick="restartGame()" style="padding:10px 32px;font-size:16px;border-radius:8px">再来一局</button>' +
    '<button class="ally-btn ally-btn-decline" onclick="closeGameOverDialog(); leaveGame()" style="padding:10px 32px;font-size:16px;border-radius:8px">离开房间</button>' +
    '</div></div>';
  document.body.appendChild(div);
}

function restartGame() {
  ws.send(JSON.stringify({type: "restart_game", user_id: userId}));
  closeGameOverDialog();
}

function closeGameOverDialog() {
  const el = document.getElementById("gameover-modal");
  if (el) el.remove();
}

// ====== endGame (结束游戏) ======
function endGame() {
  if (!confirm("确定要结束当前游戏吗？")) return;
  ws.send(JSON.stringify({type: "end_game", user_id: userId}));
}

// ====== leaveGame (modified to also send leave_room) ======
function leaveGame() {
  ws.send(JSON.stringify({type: "leave_room", user_id: userId}));
  stopBGM();
  currentRoom = null;
  document.getElementById("ally-panel").style.display = "none";
  showPage("page-lobby");
  refreshRoomList();
}

// ====== 轮到走子弹窗 ======
function showTurnNotification(color, playerName) {
  var popup = document.getElementById("turn-board-popup");
  var textEl = document.getElementById("turn-popup-text");
  var hintEl = document.getElementById("turn-popup-hint");
  if (!popup) return;

  var isMe = (color === myColor);
  var name = playerName || COLOR_NAMES[color] || "未知";
  if (isMe) {
    textEl.textContent = "⏰ 轮到你了！";
    var secs = timerSeconds > 0 ? timerSeconds : 30;
    hintEl.textContent = secs + "s   ";
    hintEl.style.color = secs <= 5 ? "#ff6b6b" : "#d4aa7c";
  } else {
    textEl.textContent = "⏰ 轮到 " + name + " 走子";
    hintEl.textContent = "30s";
    hintEl.style.color = "#d4aa7c";
  }
  popup.style.display = "block";
  // 语音播报
  speakTurn(name, isMe);

  // 1.2 秒后自动消失
  if (popup._timer) clearTimeout(popup._timer);
  popup._timer = setTimeout(dismissTurnNotification, 1200);
}

function dismissTurnNotification() {
  var popup = document.getElementById("turn-board-popup");
  if (popup) {
    if (popup._timer) clearTimeout(popup._timer);
    popup.style.display = "none";
  }
}

// ====== 盟友通知弹窗 ======
function showAllyNotification(allyName) {
  var existing = document.getElementById("ally-notif-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = "ally-notif-modal";
  overlay.innerHTML =
    '<div class="modal-box">' +
    '<div class="modal-invite-text" style="font-size:28px">🤝 你的盟友</div>' +
    '<div class="modal-hint" style="font-size:22px;color:#FFD700;margin:16px 0">' + allyName + '</div>' +
    '<div class="modal-buttons">' +
    '<button class="ally-btn ally-btn-accept" onclick="dismissAllyNotification()" style="padding:10px 32px;font-size:16px;border-radius:8px">开始游戏</button>' +
    '</div></div>';
  document.body.appendChild(overlay);
  overlay._autoTimer = setTimeout(dismissAllyNotification, 4000);
}

function dismissAllyNotification() {
  var el = document.getElementById("ally-notif-modal");
  if (el) {
    if (el._autoTimer) clearTimeout(el._autoTimer);
    el.remove();
  }
}

// ====== 邀请弹窗 ======
function showInviteModal(fromId, fromName) {
  hideInviteModal();  // 移除旧弹窗
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = "invite-modal";
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-invite-text">🤝 ${fromName} 邀请你结盟</div>
      <div class="modal-hint">是否同意与 ${fromName} 组成队伍？</div>
      <div class="modal-buttons">
        <button class="ally-btn ally-btn-accept" id="modal-accept-btn" style="padding:10px 32px;font-size:16px;border-radius:8px">接受</button>
        <button class="ally-btn ally-btn-decline" id="modal-decline-btn" style="padding:10px 32px;font-size:16px;border-radius:8px">拒绝</button>
      </div>
    </div>`;
  overlay._inviterId = fromId;
  document.body.appendChild(overlay);

  document.getElementById("modal-accept-btn").onclick = () => {
    if (overlay._inviterId) {
      ws.send(JSON.stringify({
        type: "ally_accept", user_id: userId,
        inviter_id: overlay._inviterId,
      }));
    }
    allyInviteFrom = null;
    hideInviteModal();
  };

  document.getElementById("modal-decline-btn").onclick = () => {
    if (overlay._inviterId) {
      ws.send(JSON.stringify({
        type: "ally_decline", user_id: userId,
        inviter_id: overlay._inviterId,
      }));
    }
    allyInviteFrom = null;
    hideInviteModal();
    renderAllyPanel();
  };
}

function hideInviteModal() {
  const existing = document.getElementById("invite-modal");
  if (existing) existing.remove();
}

// ====== 自动登录（刷新后保持登录状态） ======
(function() {
  // 用户首次点击时创建 AudioContext 和 BGM 音频（浏览器自动播放策略）
  document.addEventListener("click", function initAudio() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    // 在用户手势内创建 Audio 元素，确保后续可播放
    if (!bgmAudio) {
      bgmAudio = new Audio("/music/" + encodeURIComponent("三国恋-Tank#8V9K.mp3"));
      bgmAudio.loop = true;
      bgmAudio.volume = 0.18;
    }
    if (bgmEnabled && document.getElementById("page-game").style.display !== "none") {
      startBGM();
    }
  }, { once: true });
})();

(function() {
  const savedName = localStorage.getItem("xiangqi_username");
  const savedPwd = localStorage.getItem("xiangqi_password");
  if (savedName && savedPwd !== undefined && savedPwd !== null) {
    document.getElementById("login-name").value = savedName;
    document.getElementById("login-password").value = savedPwd || "";
    // 短暂延迟后自动登录（确保 DOM 就绪）
    setTimeout(doLogin, 100);
  } else if (savedName) {
    document.getElementById("login-name").value = savedName;
    document.getElementById("login-password").value = savedPwd || "";
  }
})();

// 回车键触发登录（用户名和密码框均可）
document.getElementById("login-name").addEventListener("keydown", function(e) {
  if (e.key === "Enter") doLogin();
});
document.getElementById("login-password").addEventListener("keydown", function(e) {
  if (e.key === "Enter") doLogin();
});
