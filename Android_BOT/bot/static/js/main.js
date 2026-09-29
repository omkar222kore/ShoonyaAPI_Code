/* ═══════════════════════════════════════════════════════════
   SHOONYA ALGO TERMINAL - SocketIO Live Client (auth enabled)
   ═══════════════════════════════════════════════════════════ */

let pnlHistory = [];
let orderCount = 0;
const MAX_SPARKLINE = 60;

function getToken() { return localStorage.getItem("atoken") || ""; }
function setToken(t) { localStorage.setItem("atoken", t); }

let socket = io({ auth: { token: getToken() }, autoConnect: true });

function showLogin() {
  document.getElementById("loginOverlay").classList.remove("hidden");
}

function hideLogin() {
  document.getElementById("loginOverlay").classList.add("hidden");
}

function doLogin() {
  const token = document.getElementById("authTokenInput").value.trim();
  const err = document.getElementById("loginError");
  err.textContent = "";
  if (!token) { err.textContent = "Enter the dashboard password"; return; }
  fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        setToken(token);
        hideLogin();
        socket.auth = { token };
        socket.disconnect();
        socket.connect();
      } else {
        err.textContent = "Wrong password";
      }
    })
    .catch(() => { err.textContent = "Server unreachable"; });
}

socket.on("connect_error", (err) => {
  if (err.message && err.message.toLowerCase().includes("unauthoriz")) showLogin();
  else showLogin();
});

socket.on("error", () => showLogin());

// ── Clock ──────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    now.toLocaleTimeString("en-GB", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── Uptime + tunnel info ───────────────────────────────────

function refreshStatus() {
  fetch("/api/status")
    .then(r => r.json())
    .then(d => {
      const s = d.uptime || 0;
      const h = String(Math.floor(s / 3600)).padStart(2, "0");
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
      const sec = String(s % 60).padStart(2, "0");
      document.getElementById("uptime").textContent = `UP ${h}:${m}:${sec}`;
      document.getElementById("webhookUrl").value = d.webhook_url || "";
    })
    .catch(() => { showLogin(); });
}
setInterval(refreshStatus, 5000);
refreshStatus();

// ── PnL Sparkline ──────────────────────────────────────────

function drawSparkline() {
  const canvas = document.getElementById("pnlSparkline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  if (pnlHistory.length < 2) return;

  const vals = pnlHistory.slice(-MAX_SPARKLINE);
  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  const range = mx - mn || 1;
  const step = W / (vals.length - 1);

  const lastVal = vals[vals.length - 1];
  const color = lastVal >= 0 ? "#00ff88" : "#ff3366";

  ctx.beginPath();
  vals.forEach((v, i) => {
    const x = i * step;
    const y = H - 8 - ((v - mn) / range) * (H - 16);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.lineTo(W, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, lastVal >= 0 ? "rgba(0,255,136,0.15)" : "rgba(255,51,102,0.15)");
  grad.addColorStop(1, "transparent");
  ctx.fillStyle = grad;
  ctx.fill();
}

// ── Socket Events ──────────────────────────────────────────

socket.on("connect", () => {
  addLog("[SYSTEM] Connected to server", "success");
});

socket.on("disconnect", () => {
  addLog("[SYSTEM] Disconnected from server", "error");
});

socket.on("log", (data) => {
  addLog(data.message);
});

socket.on("pnl", (data) => {
  const pnl = data.value;
  document.getElementById("pnlValue").textContent = pnl >= 0 ? `+${pnl.toFixed(2)}` : pnl.toFixed(2);

  const card = document.getElementById("pnlCard");
  card.className = "kpi-card pnl-card " + (pnl >= 0 ? "pnl-positive" : "pnl-negative");

  pnlHistory.push(pnl);
  if (pnlHistory.length > MAX_SPARKLINE) pnlHistory.shift();
  drawSparkline();
});

socket.on("positions", (data) => {
  const positions = data.data || [];
  const tbody = document.getElementById("posBody");
  document.getElementById("posCount").textContent = positions.length;

  if (positions.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="3">No open positions</td></tr>';
    return;
  }

  tbody.innerHTML = positions.map(p => {
    const pnlClass = p.pnl > 0 ? "pos-positive" : p.pnl < 0 ? "pos-negative" : "pos-zero";
    const pnlStr = p.pnl >= 0 ? `+${p.pnl.toFixed(2)}` : p.pnl.toFixed(2);
    return `<tr>
      <td>${p.symbol}</td>
      <td>${p.qty}</td>
      <td class="${pnlClass}">${pnlStr}</td>
    </tr>`;
  }).join("");
});

socket.on("status", (data) => {
  const badge = document.getElementById("statusBadge");
  const text = document.getElementById("statusText");
  const state = data.state;

  if (state === "RUNNING" || state === "CONNECTED") {
    badge.classList.add("running");
    text.textContent = state === "RUNNING" ? "RUNNING" : "CONNECTED";
  } else {
    badge.classList.remove("running");
    text.textContent = state || "OFFLINE";
  }
});

socket.on("order", (data) => {
  orderCount++;
  document.getElementById("orderCount").textContent = orderCount;
  const o = data.data;
  addLog(`ORDER: ${o.direction} ${o.symbol} x${o.qty} @ ${o.price || "MKT"} -> ${o.order_id}`, "order");
});

// ── Actions ────────────────────────────────────────────────

function startBot() {
  const token = document.getElementById("tokenInput").value.trim();
  const cap = parseInt(document.getElementById("capInput").value) || 1000;
  const pwd = document.getElementById("pwdInput").value.trim();

  if (!token) {
    addLog("[ERROR] Enter SuperToken first", "error");
    return;
  }

  addLog("[SYSTEM] Starting bot...", "success");

  const body = { super_token: token, trading_cap: cap };
  if (pwd) body.pwd = pwd;

  fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) addLog(`[ERROR] ${d.error}`, "error");
      else addLog("[SYSTEM] Bot started", "success");
    })
    .catch(e => addLog(`[ERROR] ${e}`, "error"));
}

function stopBot() {
  addLog("[SYSTEM] Stopping bot...", "warn");
  fetch("/api/stop", { method: "POST" })
    .then(r => r.json())
    .then(() => addLog("[SYSTEM] Bot stopped", "warn"))
    .catch(e => addLog(`[ERROR] ${e}`, "error"));
}

function copyWebhook() {
  const url = document.getElementById("webhookUrl").value;
  if (!url) return;
  navigator.clipboard.writeText(url).then(() => {
    showToast("Webhook URL copied!");
  });
}

function clearLog() {
  document.getElementById("logConsole").innerHTML = "";
}

// ── Token show/hide ────────────────────────────────────────

document.getElementById("toggleToken").addEventListener("click", () => {
  const input = document.getElementById("tokenInput");
  const btn = document.getElementById("toggleToken");
  if (input.type === "password") {
    input.type = "text";
    btn.innerHTML = "&#128064;";
  } else {
    input.type = "password";
    btn.innerHTML = "&#128065;";
  }
});

// ── Log helper ─────────────────────────────────────────────

function addLog(msg, type = "") {
  const el = document.getElementById("logConsole");
  const line = document.createElement("div");
  line.className = "log-line " + type;

  if (!type) {
    if (/error|fail|ERROR|FAIL/i.test(msg)) line.className = "log-line error";
    else if (/warn|WARN|skip/i.test(msg)) line.className = "log-line warn";
    else if (/SELL|BUY|ORDER|EXIT/i.test(msg)) line.className = "log-line order";
    else if (/EXITED|success|STARTED/i.test(msg)) line.className = "log-line success";
  }

  const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
  line.textContent = `[${ts}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;

  while (el.children.length > 500) el.removeChild(el.firstChild);
}

// ── Toast ──────────────────────────────────────────────────

function showToast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ── Keyboard shortcuts ─────────────────────────────────────

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && document.activeElement === document.getElementById("tokenInput")) {
    startBot();
  }
  if (e.key === "Enter" && document.activeElement === document.getElementById("authTokenInput")) {
    doLogin();
  }
});