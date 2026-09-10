const socket = io();

function updateClock() {
  document.getElementById("clock").textContent =
    new Date().toLocaleTimeString("en-GB", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

socket.on("connect", () => addLog("Connected", "success"));
socket.on("disconnect", () => addLog("Disconnected", "error"));

socket.on("log", (d) => addLog(d.message));

socket.on("backtest_status", (d) => {
  const badge = document.getElementById("statusBadge");
  const text = document.getElementById("statusText");
  const btn = document.getElementById("runBtn");

  if (d.state === "running") {
    badge.classList.add("running");
    text.textContent = "RUNNING";
    btn.disabled = true;
  } else if (d.state === "done") {
    badge.classList.remove("running");
    text.textContent = "DONE";
    btn.disabled = false;
    document.getElementById("downloadBtn").disabled = false;
    if (d.summary) showSummary(d.summary);
  } else {
    badge.classList.remove("running");
    text.textContent = "ERROR";
    btn.disabled = false;
  }
});

function showSummary(s) {
  const row = document.getElementById("summaryRow");
  row.style.display = "grid";
  const pnl = s.total_pnl;
  document.getElementById("pnlValue").textContent =
    pnl >= 0 ? `+${pnl.toLocaleString("en-IN", {minimumFractionDigits:2})}` :
    pnl.toLocaleString("en-IN", {minimumFractionDigits:2});
  const card = document.getElementById("pnlCard");
  card.className = "kpi-card pnl-card " + (pnl >= 0 ? "pnl-positive" : "pnl-negative");
  document.getElementById("wrValue").textContent = s.win_rate + "%";
  document.getElementById("tradesValue").textContent = s.total_trades;
  document.getElementById("wlValue").textContent = `${s.wins} / ${s.losses}`;
}

function login() {
  const token = document.getElementById("tokenInput").value.trim();
  if (!token) { addLog("Enter SuperToken", "error"); return; }
  addLog("Logging in...");
  fetch("/api/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({super_token: token}),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) addLog(d.error, "error");
      else addLog("Login OK", "success");
    })
    .catch(e => addLog(e, "error"));
}

function runBacktest() {
  addLog("Starting backtest...");
  document.getElementById("downloadBtn").disabled = true;
  fetch("/api/backtest", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      csv_path: document.getElementById("csvInput").value,
      sl_pct: parseFloat(document.getElementById("slInput").value) || 0.6,
      tp_pct: parseFloat(document.getElementById("tpInput").value) || 1.3,
      capital: parseInt(document.getElementById("capInput").value) || 200000,
      skip_download: document.getElementById("skipDownload").checked,
    }),
  })
    .then(r => r.json())
    .then(d => { if (d.error) addLog(d.error, "error"); })
    .catch(e => addLog(e, "error"));
}

function downloadResults() {
  window.location.href = "/api/download";
}

function clearLog() {
  document.getElementById("logConsole").innerHTML = "";
}

document.getElementById("toggleToken").addEventListener("click", () => {
  const input = document.getElementById("tokenInput");
  const btn = document.getElementById("toggleToken");
  if (input.type === "password") { input.type = "text"; btn.innerHTML = "&#128064;"; }
  else { input.type = "password"; btn.innerHTML = "&#128065;"; }
});

function addLog(msg, type = "") {
  const el = document.getElementById("logConsole");
  const line = document.createElement("div");
  line.className = "log-line " + type;
  if (!type) {
    if (/error|fail|FATAL/i.test(msg)) line.className = "log-line error";
    else if (/warn|skip/i.test(msg)) line.className = "log-line warn";
    else if (/OK|done|saved|Profit/i.test(msg)) line.className = "log-line success";
    else if (/Loss|SL|CUT/i.test(msg)) line.className = "log-line warn";
  }
  const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
  line.textContent = `[${ts}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
  while (el.children.length > 500) el.removeChild(el.firstChild);
}
