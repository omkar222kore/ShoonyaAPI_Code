/* ═══════════════════════════════════════════════════════════
   SHOONYA ALGO TERMINAL - SocketIO Live Client
   ═══════════════════════════════════════════════════════════ */

const socket = io();
let pnlHistory = [];
let orderCount = 0;
const MAX_SPARKLINE = 60;

function parseJson(r) {
  return r.text().then(t => {
    try { return JSON.parse(t); }
    catch (e) { return { error: `Server returned non-JSON response (HTTP ${r.status})` }; }
  });
}

// ── Mode switch (virtual / live) ─────────────────────────

let selectedMode = "live";
let botRunning = false;
let lastPnl = null;
let dayPnl = null;
let tradingCap = 95000;
let eodDone = false;
let eodPending = false;

function setMode(mode, fromServer = false) {
  if (botRunning && !fromServer) return;

  selectedMode = mode === "live" ? "live" : "virtual";
  const isLive = selectedMode === "live";

  const toggle = document.getElementById("modeToggle");
  if (toggle) toggle.checked = isLive;
  document.getElementById("msVirtual").classList.toggle("on", !isLive);
  document.getElementById("msLive").classList.toggle("on", isLive);

  if (!fromServer) {
    addLog(
      `[SYSTEM] Mode set to ${selectedMode.toUpperCase()}`,
      isLive ? "warn" : "success"
    );
    if (isLive) addLog("[SYSTEM] LIVE = real broker orders, real money", "error");
  }

  updateModePill();
  renderPnl();
}

function lockMode(locked) {
  const wrap = document.getElementById("modeSwitchWrap");
  const toggle = document.getElementById("modeToggle");
  if (wrap && toggle) {
    wrap.classList.toggle("locked", locked);
    toggle.disabled = locked;
  }
  const sq = document.getElementById("sqOffBtn");
  if (sq) sq.disabled = !locked;
}

// ── Mode pill + P&L idle/closed states ────────────────────

function updateModePill() {
  const pill = document.getElementById("modePill");
  if (!pill) return;
  const live = selectedMode === "live";
  pill.className = "mode-pill " + (live ? "live" : "virtual");
  pill.textContent = live ? "LIVE - REAL MONEY" : "VIRTUAL";
}

function renderPnl() {
  const el = document.getElementById("pnlValue");
  const card = document.getElementById("pnlCard");
  const chip = document.getElementById("pnlChip");
  if (!el || !card) return;

  const live = selectedMode === "live";
  card.classList.remove("pnl-positive", "pnl-negative", "pnl-idle", "pnl-closed");
  card.classList.toggle("live-accent", live);

  const fmt = (v) => (Number(v) > 0 ? "+" : "") + Number(v).toFixed(2);

  if (botRunning) {
    const pnl = lastPnl == null ? 0 : lastPnl;
    el.textContent = fmt(pnl);
    card.classList.add(pnl >= 0 ? "pnl-positive" : "pnl-negative");
    if (chip) chip.textContent = live ? "LIVE SESSION" : "VIRTUAL SESSION";
    return;
  }

  // Not running: show the day's profit (still meaningful once closed).
  const closed = eodDone || eodPending;
  const val = dayPnl != null ? dayPnl : lastPnl;
  if (val != null && (closed || Number(val) !== 0)) {
    el.textContent = fmt(val);
    card.classList.add(Number(val) >= 0 ? "pnl-positive" : "pnl-negative");
    card.classList.add(closed ? "pnl-closed" : "pnl-idle");
    if (chip) chip.textContent = closed ? "MARKET CLOSED" : "NOT RUNNING";
  } else {
    card.classList.add(closed ? "pnl-closed" : "pnl-idle");
    el.textContent = "\u2014";
    if (chip) chip.textContent = closed ? "MARKET CLOSED" : "NOT RUNNING";
  }
}

const modeToggleEl = document.getElementById("modeToggle");
if (modeToggleEl) {
  modeToggleEl.addEventListener("change", () => {
    setMode(modeToggleEl.checked ? "live" : "virtual");
  });
}

// ── Square-off time + manual square-off ───────────────────

const eodInput = document.getElementById("eodInput");
let eodTime = "15:10";
let eodDoneLogged = false;

if (eodInput) {
  eodInput.addEventListener("change", () => {
    const t = eodInput.value;
    if (!t) return;
    fetch("/api/eod", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time: t }),
    })
      .then(parseJson)
      .then(d => {
        if (d.error) {
          addLog(`[ERROR] ${d.error}`, "error");
          eodInput.value = eodTime;
          return;
        }
        eodTime = d.eod_time || t;
        addLog(`[SYSTEM] Square-off time set to ${eodTime}`, "success");
        showToast(`Auto square-off at ${eodTime}`);
      })
      .catch(e => addLog(`[ERROR] ${e}`, "error"));
  });
}

function squareOff() {
  if (!botRunning) {
    addLog("[SYSTEM] Bot is not running", "warn");
    return;
  }
  const live = selectedMode === "live";
  const msg = live
    ? "LIVE mode - this places REAL buy orders to close every position. Continue?"
    : "Close every open position now? (bot keeps running)";
  if (!confirm(msg)) return;

  fetch("/api/squareoff", { method: "POST" })
    .then(parseJson)
    .then(d => {
      if (d.error) {
        addLog(`[ERROR] ${d.error}`, "error");
        return;
      }
      addLog("[SYSTEM] Square-off requested - closing all positions", "warn");
      showToast("Square-off requested");
    })
    .catch(e => addLog(`[ERROR] ${e}`, "error"));
}

function openTradeLog() {
  fetch("/api/tradelog")
    .then(r => {
      if (!r.ok) {
        return r.json().then(d => { throw new Error(d.error || "No trade log yet"); });
      }
      return r.blob();
    })
    .then(blob => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "trade_log.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
      showToast("Trade log downloaded");
    })
    .catch(e => addLog(`[ERROR] ${e.message || e}`, "error"));
}

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
    .then(parseJson)
    .then(d => {
      const s = d.uptime || 0;
      const h = String(Math.floor(s / 3600)).padStart(2, "0");
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
      const sec = String(s % 60).padStart(2, "0");
      document.getElementById("uptime").textContent = `UP ${h}:${m}:${sec}`;

      if (d.mode && d.running) setMode(d.mode, true);
      if (d.eod_time && d.eod_time !== eodTime &&
          document.activeElement !== eodInput) {
        eodTime = d.eod_time;
        if (eodInput) eodInput.value = eodTime;
      }
      eodDone = !!d.eod_done;
      eodPending = !!d.eod_pending;
      if (typeof d.trading_cap === "number") tradingCap = d.trading_cap;
      if (typeof d.pnl === "number") dayPnl = d.pnl;
      if (d.eod_done && !eodDoneLogged) {
        eodDoneLogged = true;
        addLog(`[EOD] Auto square-off at ${eodTime} complete - positions flattened`, "success");
      }
      if (typeof d.running === "boolean" && d.running !== botRunning) {
        botRunning = d.running;
        lockMode(botRunning);
        if (!botRunning && eodDoneLogged) {
          addLog("[SYSTEM] Bot auto-stopped after square-off", "warn");
        }
      }
      if (typeof d.logged_in === "boolean") setLoginStatus(d.logged_in, d.user);

      updateModePill();
      renderPnl();
    })
    .catch(() => {});
}
setInterval(updateUptime, 500);
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
  lastPnl = data.value;
  renderPnl();

  pnlHistory.push(lastPnl);
  if (pnlHistory.length > MAX_SPARKLINE) pnlHistory.shift();
  drawSparkline();
});

// ── Positions: live rows + recently closed rows ───────────

let openPos = [];
let closedTrades = [];
const MAX_CLOSED = 50;
let flashOrderId = null;

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtPnl(v) {
  const n = Number(v || 0);
  return n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2);
}

function pnlClass(v) {
  const n = Number(v || 0);
  return n > 0 ? "pos-positive" : n < 0 ? "pos-negative" : "pos-zero";
}

function fmtPrice(v) {
  const n = Number(v);
  return isFinite(n) && n ? n.toFixed(2) : "&mdash;";
}

function statusBadge(reason) {
  const r = String(reason || "").toUpperCase();
  if (r.indexOf("STOP") === 0) return '<span class="badge badge-sl">SL HIT</span>';
  if (r.indexOf("TAKE") === 0) return '<span class="badge badge-tp">TP HIT</span>';
  if (r === "TRAIL-COST") return '<span class="badge badge-eod">TRAIL-COST</span>';
  if (r === "TRAIL-LOCK") return '<span class="badge badge-eod">TRAIL-LOCK</span>';
  if (r.indexOf("EOD") === 0) return `<span class="badge badge-eod">${esc(reason)}</span>`;
  if (r === "MANUAL") return '<span class="badge badge-manual">MANUAL</span>';
  return `<span class="badge badge-manual">${esc(reason || "CLOSED")}</span>`;
}

function levelChip(value, kind) {
  if (value == null || !isFinite(Number(value))) return "&mdash;";
  return `<span class="level-chip level-${kind}">${fmtPnl(value)}</span>`;
}

function levelCells(reason) {
  const r = String(reason || "").toUpperCase();
  if (r.indexOf("STOP") === 0) {
    return [levelChip(-tradingCap * 0.006, "sl"), "&mdash;"];
  }
  if (r.indexOf("TAKE") === 0) {
    return ["&mdash;", levelChip(tradingCap * 0.014, "tp")];
  }
  if (r === "TRAIL-COST") {
    return [levelChip(0, "sl"), "&mdash;"];
  }
  if (r === "TRAIL-LOCK") {
    return [levelChip(tradingCap * 0.005, "sl"), "&mdash;"];
  }
  return ["&mdash;", "&mdash;"];
}

function renderPositions() {
  const tbody = document.getElementById("posBody");
  document.getElementById("posCount").textContent = openPos.length;

  const live = openPos.map(p => `<tr class="row-open">
      <td>${esc(p.time) || "&mdash;"}</td>
      <td>${esc(p.symbol)}</td>
      <td>${p.qty}</td>
      <td>${fmtPrice(p.entry)}</td>
      <td class="dim">&mdash;</td>
      <td class="${pnlClass(p.pnl)}">${fmtPnl(p.pnl)}</td>
      <td><span class="badge badge-live">LIVE</span></td>
      <td>${levelChip(p.sl, "sl")}</td>
      <td>${levelChip(p.tp, "tp")}</td>
    </tr>`);

  const closed = closedTrades.map(t => {
    const flashing = flashOrderId && t.order_id === flashOrderId;
    const [slCell, tpCell] = levelCells(t.reason);
    return `<tr class="row-closed${flashing ? " row-flash" : ""}">
      <td>${esc(t.time) || "&mdash;"}</td>
      <td>${esc(t.symbol)}</td>
      <td>${t.qty}</td>
      <td>${fmtPrice(t.entry)}</td>
      <td>${fmtPrice(t.exit)}</td>
      <td class="${pnlClass(t.pnl)}">${fmtPnl(t.pnl)}</td>
      <td>${statusBadge(t.reason)}</td>
      <td>${slCell}</td>
      <td>${tpCell}</td>
    </tr>`;
  });

  if (!live.length && !closed.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No positions yet</td></tr>';
    return;
  }
  tbody.innerHTML = live.concat(closed).join("");
}

function addClosedTrade(row) {
  if (!row) return;
  closedTrades.unshift(row);
  if (closedTrades.length > MAX_CLOSED) closedTrades.length = MAX_CLOSED;
  flashOrderId = row.order_id || null;
  renderPositions();
  setTimeout(() => {
    flashOrderId = null;
    renderPositions();
  }, 3000);
}

fetch("/api/closedtrades")
  .then(parseJson)
  .then(d => {
    const rows = Array.isArray(d.data) ? d.data : [];
    const todays = rows.filter(t => !d.date || String(t.date) === d.date);
    if (todays.length) {
      closedTrades = todays.slice(0, MAX_CLOSED);
      renderPositions();
    }
  })
  .catch(() => {});

socket.on("positions", (data) => {
  openPos = data.data || [];
  renderPositions();
});

socket.on("closed_trade", (data) => {
  addClosedTrade(data && data.data);
});

socket.on("status", (data) => {
  const badge = document.getElementById("statusBadge");
  const text = document.getElementById("statusText");
  const state = data.state;

  if (state === "RUNNING" || state === "LIVE" || state === "CONNECTED") {
    badge.classList.add("running");
    if (state === "RUNNING") text.textContent = "VIRTUAL RUNNING";
    else if (state === "LIVE") text.textContent = "LIVE RUNNING";
    else text.textContent = "CONNECTED";
  } else {
    badge.classList.remove("running");
    text.textContent = state || "OFFLINE";
  }
});

socket.on("order", (data) => {
  orderCount++;
  document.getElementById("orderCount").textContent = orderCount;
  const o = data.data;
  const tag = o.virtual ? "V-ORDER" : "ORDER";
  addLog(`${tag}: ${o.direction} ${o.symbol} x${o.qty} @ ${o.price || "MKT"} -> ${o.order_id}`, "order");
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
  const tokenInput = document.getElementById("tokenInput");
  let token = tokenInput ? tokenInput.value.trim() : "";
  const cap = document.getElementById("capInput").value;

  if (selectedMode === "live") {
    const ok = confirm(
      "LIVE MODE\n\n" +
      "Real broker orders will be placed with real money.\n" +
      "Virtual mode will NOT be used.\n\n" +
      "Continue?"
    );
    if (!ok) {
      addLog("[SYSTEM] LIVE start cancelled", "warn");
      return;
    }
    addLog("[SYSTEM] WARNING: LIVE mode - real orders enabled", "error");
  } else {
    addLog("[SYSTEM] Starting bot in VIRTUAL mode (no real orders)", "success");
  }

  const body = {
    trading_cap: parseInt(cap) || 95000,
    virtual: selectedMode === "virtual",
  };
  if (token) {
    body.super_token = token;
  } else {
    // Try auto-login using credentials from login panel
    const uid = (document.getElementById("uidInput") || {}).value || "";
    const pwd = (document.getElementById("pwdInput") || {}).value || "";
    const otp = (document.getElementById("otpInput") || {}).value || "";
    if (uid) body.user_id = uid.trim();
    if (pwd) body.password = pwd;
    if (otp) body.otp = otp.trim();
    addLog("[AUTO-LOGIN] No token provided, attempting auto-fetch from saved/entered credentials...", "warn");
  }

  fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(parseJson)
    .then(d => {
      if (d.error) {
        addLog(`[ERROR] ${d.error}`, "error");
        return;
      }
      addLog(`[SYSTEM] Bot started (${(d.mode || selectedMode).toUpperCase()})`, "success");
      botRunning = true;
      lockMode(true);
      eodDoneLogged = false;
    })
    .catch(e => addLog(`[ERROR] ${e}`, "error"));
}

function stopBot() {
  addLog("[SYSTEM] Stopping bot...", "warn");
  fetch("/api/stop", { method: "POST" })
    .then(parseJson)
    .then(() => {
      addLog("[SYSTEM] Bot stopped", "warn");
      botRunning = false;
      lockMode(false);
    })
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

// ── Login panel ────────────────────────────────────────────

function toggleLoginPanel() {
  const panel = document.getElementById("loginPanel");
  if (panel) panel.classList.toggle("open");
}

function togglePwd() {
  const input = document.getElementById("pwdInput");
  const btn = document.getElementById("togglePwd");
  if (!input) return;
  if (input.type === "password") {
    input.type = "text";
    btn.innerHTML = "&#128064;";
  } else {
    input.type = "password";
    btn.innerHTML = "&#128065;";
  }
}

function setLoginStatus(ok, user) {
  const el = document.getElementById("loginStatus");
  if (!el) return;
  el.classList.toggle("ok", !!ok);
  el.classList.toggle("off", !ok);
  el.textContent = ok ? `LOGGED IN${user ? " - " + user : ""}` : "NOT LOGGED IN";
}

function loginValues() {
  return {
    user_id: (document.getElementById("uidInput") || {}).value || "",
    password: (document.getElementById("pwdInput") || {}).value || "",
    otp: (document.getElementById("otpInput") || {}).value || "",
    jkey: (document.getElementById("jkeyInput") || {}).value || "",
  };
}

function fetchJkeyFromWeb() {
  const body = loginValues();
  body.user_id = body.user_id.trim();
  body.otp = body.otp.trim();
  const btn = document.getElementById("fetchJkeyBtn");
  const reset = () => {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "FETCH JKEY FROM WEB";
    }
  };
  if (btn) {
    btn.disabled = true;
    btn.textContent = "LOGGING IN... (up to 1 min)";
  }
  addLog("[SYSTEM] Logging into Shoonya web terminal...", "warn");
  fetch("/api/getjkey", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(parseJson)
    .then(d => {
      if (d.error) {
        addLog(`[ERROR] ${d.error}`, "error");
        showToast("Login failed");
        return;
      }
      const jk = document.getElementById("jkeyInput");
      if (jk) jk.value = d.jkey || d.supertoken || "";
      addLog("[SUCCESS] JKEY fetched from web login", "success");
      showToast("JKEY fetched");
    })
    .catch(e => addLog(`[ERROR] ${e}`, "error"))
    .finally(reset);
}

function copyJkey() {
  const j = document.getElementById("jkeyInput");
  if (!j || !j.value.trim()) {
    addLog("[ERROR] No jkey to copy", "error");
    return;
  }
  navigator.clipboard.writeText(j.value.trim()).then(() => {
    addLog("[SYSTEM] JKEY copied to clipboard", "success");
    showToast("JKEY copied");
  });
}

function useJkey() {
  const jkey = (document.getElementById("jkeyInput") || {}).value || "";
  if (!jkey.trim()) {
    addLog("[ERROR] Paste a JKEY first", "error");
    return;
  }
  const tokenInput = document.getElementById("tokenInput");
  if (tokenInput) tokenInput.value = jkey.trim();
  addLog("[SYSTEM] JKEY copied into SuperToken field", "success");
  showToast("JKEY copied");
}

function saveLogin() {
  const body = loginValues();
  body.user_id = body.user_id.trim();
  body.otp = body.otp.trim();
  body.jkey = body.jkey.trim();
  fetch("/api/login/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(parseJson)
    .then(d => {
      if (d.error) {
        addLog(`[ERROR] ${d.error}`, "error");
        return;
      }
      addLog(`[SYSTEM] ${d.message || "Credentials saved"}`, "success");
      showToast("Saved");
    })
    .catch(e => addLog(`[ERROR] ${e}`, "error"));
}

socket.on("auth", (data) => {
  setLoginStatus(!!(data && data.logged_in), data && data.user);
});

const togglePwdBtn = document.getElementById("togglePwd");
if (togglePwdBtn) togglePwdBtn.addEventListener("click", togglePwd);

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

// ── Initial render ─────────────────────────────────────────

updateModePill();
renderPnl();

// ── Keyboard shortcuts ─────────────────────────────────────

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && document.activeElement === document.getElementById("tokenInput")) {
    startBot();
  }
});
