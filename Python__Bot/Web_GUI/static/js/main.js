/* ═══════════════════════════════════════════════════════════
   SHOONYA ALGO TERMINAL - SocketIO Live Client
   ═══════════════════════════════════════════════════════════ */

const socket = io();
let pnlHistory = [];
let orderCount = 0;
const MAX_SPARKLINE = 60;

// ── Clock ──────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    now.toLocaleTimeString("en-GB", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── Uptime ─────────────────────────────────────────────────

function updateUptime() {
  fetch("/api/status")
    .then(r => r.json())
    .then(d => {
      const s = d.uptime || 0;
      const h = String(Math.floor(s / 3600)).padStart(2, "0");
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
      const sec = String(s % 60).padStart(2, "0");
      document.getElementById("uptime").textContent = `UP ${h}:${m}:${sec}`;
    })
    .catch(() => {});
}
setInterval(updateUptime, 5000);
updateUptime();

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

  // Glow fill
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
  const el = document.getElementById("pnlValue");
  el.textContent = pnl >= 0 ? `+${pnl.toFixed(2)}` : pnl.toFixed(2);

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

socket.on("ngrok", (data) => {
  const urls = data.urls || {};
  const chips = document.getElementById("ngrokChips");
  const webhookInput = document.getElementById("webhookUrl");

  chips.innerHTML = "";
  const colors = { 5000: "cyan", 5001: "green", 5002: "orange" };

  for (const [port, url] of Object.entries(urls)) {
    const chip = document.createElement("a");
    chip.className = `ngrok-chip ${colors[port] || "cyan"}`;
    chip.href = url + "/webhook";
    chip.target = "_blank";
    chip.textContent = `:${port} -> ${url}`;
    chips.appendChild(chip);
  }

  if (urls[5000]) {
    webhookInput.value = urls[5000] + "/webhook";
  }
});

// ── Actions ────────────────────────────────────────────────

function startBot() {
  const token = document.getElementById("tokenInput").value.trim();
  const cap = document.getElementById("capInput").value;

  if (!token) {
    addLog("[ERROR] Enter SuperToken first", "error");
    return;
  }

  addLog("[SYSTEM] Starting bot...", "success");

  fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ super_token: token, trading_cap: parseInt(cap) || 1000 }),
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

  // Auto-classify
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

  // Limit lines
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
});
