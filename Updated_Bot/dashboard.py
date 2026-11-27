import json
import os
import subprocess
import sys
from datetime import datetime

from flask import Flask, jsonify, request

import config
import state as app_state


app = Flask(__name__)


def read_heartbeat():
    if not os.path.exists(config.HEARTBEAT_FILE):
        return {"running": False, "mode": "UNKNOWN", "time": "", "open_positions": 0}
    try:
        with open(config.HEARTBEAT_FILE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return {"running": False, "mode": "UNKNOWN", "time": "", "open_positions": 0}
    timestamp = payload.get("time") if isinstance(payload, dict) else None
    if timestamp:
        try:
            seen = datetime.fromisoformat(timestamp)
            age = (datetime.now(config.IST) - seen).total_seconds()
            if age > 15:
                payload["running"] = False
        except (TypeError, ValueError):
            pass
    return payload


@app.route("/")
def index():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Updated Bot Dashboard</title>
<style>
:root {
  --bg:#080b12; --panel:rgba(18,23,34,.86); --panel2:rgba(24,30,44,.9);
  --line:rgba(148,163,184,.16); --text:#e8edf6; --muted:#8e9bb1;
  --green:#34d399; --red:#fb7185; --amber:#fbbf24; --blue:#60a5fa; --violet:#a78bfa;
}
* { box-sizing:border-box; }
body {
  margin:0; min-height:100vh; color:var(--text); background:var(--bg);
  font-family:Segoe UI,Inter,Arial,sans-serif; overflow-x:hidden;
}
body:before, body:after {
  content:''; position:fixed; width:520px; height:520px; border-radius:50%;
  filter:blur(110px); opacity:.18; z-index:-1; pointer-events:none;
}
body:before { background:var(--blue); top:-180px; left:-140px; }
body:after { background:var(--violet); right:-180px; bottom:-220px; }
.shell { width:min(1440px,94vw); margin:0 auto; padding:24px 0 40px; }
.topbar { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.brand { display:flex; align-items:center; gap:12px; }
.logo {
  width:42px; height:42px; border-radius:13px; display:grid; place-items:center;
  background:linear-gradient(135deg,var(--blue),var(--violet));
  box-shadow:0 8px 28px rgba(96,165,250,.28); font-weight:800; letter-spacing:-1px;
}
.brand h1 { font-size:20px; margin:0; letter-spacing:-.4px; }
.brand p { margin:2px 0 0; color:var(--muted); font-size:12px; }
.topright { display:flex; align-items:center; gap:12px; flex-wrap:wrap; justify-content:flex-end; }
.clock { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.status-pill {
  display:flex; align-items:center; gap:8px; padding:8px 14px; border-radius:999px;
  border:1px solid var(--line); background:rgba(15,20,30,.85); font-size:12px; font-weight:700;
  letter-spacing:.9px; text-transform:uppercase;
}
.dot { width:8px; height:8px; border-radius:50%; background:var(--muted); }
.status-pill.on .dot { background:var(--green); box-shadow:0 0 0 5px rgba(52,211,153,.14); animation:pulse 1.6s infinite; }
.status-pill.off .dot { background:var(--red); box-shadow:0 0 0 5px rgba(251,113,133,.12); }
@keyframes pulse { 50% { box-shadow:0 0 0 9px rgba(52,211,153,0); } }
.hero {
  margin-top:22px; padding:22px; border:1px solid var(--line); border-radius:20px;
  background:linear-gradient(120deg,rgba(30,41,59,.75),rgba(15,23,42,.65));
  display:flex; align-items:flex-end; justify-content:space-between; gap:18px; flex-wrap:wrap;
}
.hero h2 { margin:0 0 6px; font-size:26px; letter-spacing:-.8px; }
.hero p { margin:0; color:var(--muted); font-size:13px; }
.controls { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; }
.capital { display:flex; flex-direction:column; gap:5px; color:var(--muted); font-size:10px; letter-spacing:1px; text-transform:uppercase; }
.capital input { width:140px; color:var(--text); font-variant-numeric:tabular-nums; }
button {
  border:1px solid var(--line); border-radius:11px; padding:10px 15px; cursor:pointer;
  color:var(--text); background:rgba(30,41,59,.75); font-size:12px; font-weight:700;
  letter-spacing:.5px; transition:.18s ease; text-transform:uppercase;
}
button:hover { transform:translateY(-1px); border-color:rgba(148,163,184,.42); background:rgba(51,65,85,.8); }
button:active { transform:translateY(0); }
button.primary { background:linear-gradient(135deg,#2563eb,#4f46e5); border-color:transparent; }
button.live { background:linear-gradient(135deg,#be123c,#e11d48); border-color:transparent; }
button.danger { background:linear-gradient(135deg,#7f1d1d,#b91c1c); border-color:transparent; }
button.ghost { background:transparent; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; margin-top:18px; }
.card {
  border:1px solid var(--line); border-radius:18px; padding:16px; background:var(--panel);
  box-shadow:0 16px 40px rgba(0,0,0,.22); backdrop-filter:blur(12px); position:relative; overflow:hidden;
}
.card:after {
  content:''; position:absolute; inset:0 0 auto 0; height:1px;
  background:linear-gradient(90deg,transparent,rgba(148,163,184,.3),transparent);
}
.label { color:var(--muted); font-size:11px; letter-spacing:1.2px; text-transform:uppercase; }
.value { font-size:24px; font-weight:750; margin-top:8px; letter-spacing:-.6px; font-variant-numeric:tabular-nums; }
.sub { color:var(--muted); font-size:11px; margin-top:6px; min-height:14px; }
.pos { color:var(--green) !important; }
.neg { color:var(--red) !important; }
.warn { color:var(--amber) !important; }
.meter { height:5px; border-radius:99px; background:rgba(148,163,184,.14); margin-top:10px; overflow:hidden; }
.meter-fill { height:100%; width:0; border-radius:99px; transition:width .5s ease; background:var(--green); }
.meter-fill.warn { background:var(--amber); }
.meter-fill.danger { background:var(--red); }
.board { display:grid; grid-template-columns:minmax(250px,.7fr) minmax(430px,1.15fr) minmax(430px,1.15fr); gap:14px; margin-top:16px; align-items:start; }
#scanTable td:nth-child(6) { white-space:normal; min-width:280px; }
.boardhead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.boardhead h3 { margin:0; font-size:14px; letter-spacing:-.2px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; }
input, select {
  border:1px solid var(--line); background:rgba(15,20,30,.8); color:var(--text);
  border-radius:10px; padding:8px 10px; font-size:12px; outline:none;
}
input:focus, select:focus { border-color:rgba(96,165,250,.55); }
.scroll { overflow:auto; max-height:420px; border-radius:14px; border:1px solid var(--line); }
table { width:100%; border-collapse:collapse; font-size:12px; font-variant-numeric:tabular-nums; }
th, td { padding:10px 12px; text-align:left; white-space:nowrap; border-bottom:1px solid rgba(148,163,184,.1); }
th {
  position:sticky; top:0; z-index:1; background:rgba(17,24,39,.96); color:var(--muted);
  font-size:10px; letter-spacing:1px; text-transform:uppercase; cursor:pointer; user-select:none;
}
tbody tr:hover { background:rgba(59,130,246,.08); }
tbody tr:last-child td { border-bottom:0; }
.empty { padding:24px; text-align:center; color:var(--muted); font-size:12px; }
.footer { margin-top:22px; display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:11px; flex-wrap:wrap; }
.refreshline { height:2px; width:100%; background:rgba(148,163,184,.12); border-radius:99px; margin-top:8px; overflow:hidden; }
.refreshbar { height:100%; background:linear-gradient(90deg,var(--blue),var(--violet)); width:0; }
.toasts { position:fixed; right:20px; bottom:20px; display:flex; flex-direction:column; gap:8px; z-index:10; }
.toast {
  padding:11px 15px; border-radius:12px; border:1px solid var(--line);
  background:rgba(17,24,39,.95); box-shadow:0 12px 30px rgba(0,0,0,.35); font-size:12px;
  animation:slide .2s ease;
}
.toast.ok { border-color:rgba(52,211,153,.4); }
.toast.err { border-color:rgba(251,113,133,.45); }
@keyframes slide { from { transform:translateY(8px); opacity:0; } }
@media (max-width:1200px) {
  .board { grid-template-columns:1fr 1fr; }
  .board > .card:first-child { grid-column:1 / -1; }
}
@media (max-width:720px) {
  .shell { width:95vw; padding-top:14px; }
  .hero { padding:16px; }
  .hero h2 { font-size:21px; }
  .value { font-size:20px; }
  .board { grid-template-columns:1fr; }
  .board > .card:first-child { grid-column:auto; }
}
</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <div class="brand">
      <div class="logo">UB</div>
      <div><h1>Updated Bot</h1><p>Nifty 500 · 15-min scanner · local console</p></div>
    </div>
    <div class="topright">
      <div class="clock" id="clock">-</div>
      <div class="status-pill off" id="statusPill"><span class="dot"></span><span id="statusPillText">STOPPED</span></div>
    </div>
  </div>

  <div class="hero">
    <div><h2>Trading desk overview</h2><p>Paper by default. Live needs manual confirmation. No webhook, no ngrok.</p></div>
    <div class="controls">
      <label class="capital">Capital / trade<input id="capitalInput" type="number" min="1000" step="1000" value="%CAPITAL%" onchange="saveCapital()"></label>
      <button class="primary" onclick="startBot('paper')">Start Paper</button>
      <button class="live" onclick="startBot('live')">Start Live</button>
      <button class="danger" onclick="stopBot()">Stop</button>
      <button class="ghost" onclick="refresh(true)">Refresh</button>
    </div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Status</div><div class="value" id="status">-</div><div class="sub" id="heartbeat">-</div></div>
    <div class="card"><div class="label">Broker login</div><div class="value" id="loginStatus">-</div><div class="sub" id="loginTime">-</div><div class="sub" id="loginElapsed">-</div></div>
    <div class="card"><div class="label">Mode</div><div class="value" id="mode">-</div><div class="sub" id="date">-</div></div>
    <div class="card"><div class="label">Last scan</div><div class="value" id="lastscan">-</div><div class="sub" id="lastAction">-</div></div>
    <div class="card">
      <div class="label">Nifty gate</div><div class="value" id="nifty">-</div>
      <div class="sub" id="niftyNote">-</div><div class="meter"><div class="meter-fill" id="niftyMeter"></div></div>
    </div>
    <div class="card">
      <div class="label">Today net P&amp;L</div><div class="value" id="pnl">-</div><div class="sub" id="winrate">-</div>
    </div>
  </div>

  <div class="board">
    <div class="card">
      <div class="boardhead"><h3>Live open positions <span class="sub" id="positions">0</span></h3><div class="sub">SL +1.40% · TP −2.80% · capital <span id="capitalLabel">₹%CAPITAL%</span></div></div>
      <div class="scroll"><table id="openTable"><thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>SL</th><th>TP</th></tr></thead><tbody></tbody></table></div>
    </div>

    <div class="card">
      <div class="boardhead">
        <h3>Scan log <span class="sub" id="scanCount"></span></h3>
        <div class="filters">
          <input id="scanSearch" placeholder="Search stock / reason" oninput="renderTables()">
          <select id="scanAction" onchange="renderTables()">
            <option value="">All actions</option>
            <option value="TRADED">TRADED</option>
            <option value="SKIPPED">SKIPPED</option>
            <option value="NO_TRADE">NO_TRADE</option>
          </select>
        </div>
      </div>
      <div class="scroll"><table id="scanTable"><thead><tr>
        <th data-key="Time">Time</th><th data-key="Scan">Scan</th><th data-key="Matched">Matched stocks</th>
        <th data-key="Evaluated">Eval</th><th data-key="Action">Action</th><th>Why</th>
      </tr></thead><tbody></tbody></table></div>
    </div>

    <div class="card">
      <div class="boardhead">
        <h3>Closed trades <span class="sub" id="tradeCount"></span></h3>
        <div class="filters"><input id="tradeSearch" placeholder="Search trade" oninput="renderTables()"></div>
      </div>
      <div class="scroll"><table id="tradeTable"><thead><tr>
        <th data-key="Time">Time</th><th data-key="Symbol">Symbol</th><th data-key="Entry_Price">Entry</th>
        <th data-key="Exit_Price">Exit</th><th data-key="Exit_Reason">Reason</th><th data-key="Est_Net_PnL">Net</th>
      </tr></thead><tbody></tbody></table></div>
    </div>
  </div>

  <div class="footer">
    <span>Local only · 127.0.0.1:%PORT% · auto refresh 5s</span>
    <span>Updated <span id="updated">-</span></span>
  </div>
  <div class="refreshline"><div class="refreshbar" id="refreshbar"></div></div>
</div>
<div class="toasts" id="toasts"></div>

<script>
var appData = { status:{state:{}}, scans:[], trades:[] };
var sortState = { scan:{key:'Time',dir:-1}, trade:{key:'Time',dir:-1} };
var capitalLoaded = false;

function setText(id, value) {
  var el = document.getElementById(id);
  if (el) el.textContent = (value === null || value === undefined || value === '') ? '-' : value;
}
function num(value) {
  var n = Number(value);
  return isNaN(n) ? null : n;
}
function money(value) {
  var n = num(value);
  if (n === null) return '-';
  return (n >= 0 ? '+' : '-') + '₹' + Math.abs(n).toFixed(2);
}
function formatCapital(value) {
  var n = num(value);
  if (n === null) return '-';
  return '₹' + n.toLocaleString('en-IN',{maximumFractionDigits:2});
}
function formatStamp(value) {
  var d = new Date(value);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:false});
}
function updateLoginElapsed() {
  var login = appData.status.login || {};
  var last = login.last_login;
  if (!last) { setText('loginElapsed', ''); return; }
  var start = new Date(last).getTime();
  if (isNaN(start)) { setText('loginElapsed', '-'); return; }
  var secs = Math.max(0, Math.floor((Date.now() - start) / 1000));
  var days = Math.floor(secs / 86400); secs -= days * 86400;
  var hours = Math.floor(secs / 3600); secs -= hours * 3600;
  var mins = Math.floor(secs / 60); secs -= mins * 60;
  var parts = [];
  if (days) parts.push(days + 'd');
  if (hours) parts.push(hours + 'h');
  if (mins) parts.push(mins + 'm');
  parts.push(secs + 's');
  setText('loginElapsed', 'Elapsed ' + parts.join(' '));
}
function postCapital() {
  var value = document.getElementById('capitalInput').value;
  return fetch('/api/capital', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({capital:value})
  }).then(function(r) {
    if (!r.ok) throw new Error('invalid capital');
    return r.json();
  });
}
function saveCapital() {
  postCapital().then(function(data) {
    toast('Capital set to ' + formatCapital(data.capital), 'ok');
    refresh();
  }).catch(function(err) {
    toast(err.message, 'err');
  });
}
function toast(message, kind) {
  var el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.textContent = message;
  document.getElementById('toasts').appendChild(el);
  setTimeout(function() { el.remove(); }, 3600);
}
function sortRows(rows, key, dir) {
  return rows.slice().sort(function(a, b) {
    var av = a[key], bv = b[key];
    var an = num(av), bn = num(bv);
    if (an !== null && bn !== null) return (an - bn) * dir;
    return String(av || '').localeCompare(String(bv || '')) * dir;
  });
}
function applySort(kind, rows) {
  var st = sortState[kind];
  if (!st || !st.key) return rows;
  return sortRows(rows, st.key, st.dir);
}
function filteredScans() {
  var q = document.getElementById('scanSearch').value.toLowerCase();
  var action = document.getElementById('scanAction').value;
  return appData.scans.filter(function(row) {
    var hay = (row.Time || '') + ' ' + (row.Scan || '') + ' ' + (row.Matched || '') + ' ' +
      (row.Reason || '') + ' ' + (row.Details || '') + ' ' + (row.Reject_Summary || '');
    return (!action || row.Action === action) && hay.toLowerCase().indexOf(q) >= 0;
  });
}
function filteredTrades() {
  var q = document.getElementById('tradeSearch').value.toLowerCase();
  return appData.trades.filter(function(row) {
    var hay = (row.Time || '') + ' ' + (row.Symbol || '') + ' ' + (row.Exit_Reason || '');
    return hay.toLowerCase().indexOf(q) >= 0;
  });
}
function rowsToTable(id, rows, columns) {
  var body = document.querySelector('#' + id + ' tbody');
  body.innerHTML = '';
  if (!rows.length) {
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.colSpan = columns.length;
    td.className = 'empty';
    td.textContent = 'No records yet';
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }
  rows.forEach(function(row) {
    var tr = document.createElement('tr');
    columns.forEach(function(key) {
      var td = document.createElement('td');
      var value = row[key];
      if (key === 'Est_Net_PnL') {
        var pnl = num(value);
        td.textContent = money(value);
        if (pnl !== null) td.className = pnl >= 0 ? 'pos' : 'neg';
      } else if (key === 'Nifty_Pct') {
        var pct = num(value);
        td.textContent = pct === null ? '' : (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
        if (pct !== null && pct > 0.60) td.className = 'neg';
      } else if (key === 'Why') {
        var parts = [];
        if (row.Reason) parts.push(row.Reason);
        if (row.Details) parts.push(row.Details);
        if (row.Reject_Summary) parts.push(row.Reject_Summary);
        td.textContent = parts.join(' | ');
      } else if (key === 'Matched') {
        td.textContent = value ? value : 'none';
        if (!value) td.className = 'sub';
      } else {
        td.textContent = (value === null || value === undefined) ? '' : value;
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}
function renderTables() {
  var stateData = appData.status.state || {};
  var hb = appData.status.heartbeat || {};
  rowsToTable('openTable', stateData.open_positions_array || [], ['symbol','qty','entry_price','sl_price','tp_price']);
  rowsToTable('scanTable', applySort('scan', filteredScans()), ['Time','Scan','Matched','Evaluated','Action','Why']);
  rowsToTable('tradeTable', applySort('trade', filteredTrades()), ['Time','Symbol','Entry_Price','Exit_Price','Exit_Reason','Est_Net_PnL']);
  setText('positions', hb.open_positions || 0);
  setText('scanCount', appData.scans.length + ' scans');
  var traded = hb.traded_today !== undefined ? hb.traded_today : (stateData.traded_today || []).length;
  setText('tradeCount', appData.trades.length + ' closed · ' + traded + ' traded today');
}
function renderKpis() {
  var hb = appData.status.heartbeat || {};
  var stateData = appData.status.state || {};
  var running = !!hb.running;
  var pill = document.getElementById('statusPill');
  pill.className = 'status-pill ' + (running ? 'on' : 'off');
  setText('statusPillText', running ? 'RUNNING' : 'STOPPED');
  setText('status', running ? 'RUNNING' : 'STOPPED');
  document.getElementById('status').className = 'value ' + (running ? 'pos' : 'neg');
  setText('mode', hb.mode || '-');
  setText('heartbeat', hb.time || 'No heartbeat');
  var login = appData.status.login || {};
  var loginOk = login.status === 'success';
  setText('loginStatus', loginOk ? 'LOGIN OK' : (login.status === 'failed' ? 'LOGIN FAILED' : 'LOGIN UNKNOWN'));
  document.getElementById('loginStatus').className = 'value ' + (loginOk ? 'pos' : (login.status === 'failed' ? 'neg' : 'warn'));
  setText('loginTime', login.last_login ? ('At ' + formatStamp(login.last_login) + (login.duration_seconds !== null && login.duration_seconds !== undefined ? ' · took ' + login.duration_seconds + 's' : '')) : (login.message || 'No successful login yet'));
  updateLoginElapsed();
  setText('date', hb.date || stateData.date || '-');
  setText('lastscan', hb.last_scan || '-');
  var last = appData.scans.length ? appData.scans[appData.scans.length - 1] : {};
  setText('lastAction', last.Action ? last.Action + ' / ' + (last.Reason || '') : '-');
  var nifty = hb.nifty;
  if (nifty) {
    var ltp = num(nifty.ltp), pct = num(nifty.percent);
    setText('nifty', (ltp === null ? '-' : ltp.toLocaleString('en-IN',{minimumFractionDigits:2})) + ' / ' + (pct === null ? '-' : (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'));
    var meter = document.getElementById('niftyMeter');
    var pctAbs = pct === null ? 0 : Math.min(Math.abs(pct) / 0.60 * 100, 100);
    meter.style.width = pctAbs + '%';
    meter.className = 'meter-fill' + (pct !== null && pct > 0.60 ? ' danger' : pct !== null && pct > 0.30 ? ' warn' : '');
    setText('niftyNote', pct !== null && pct > 0.60 ? 'Gate blocked (> +0.60%)' : pct !== null && pct > 0.30 ? 'Approaching gate threshold' : 'Gate clear');
  } else {
    setText('nifty', '-');
    setText('niftyNote', 'Waiting for first scan');
    document.getElementById('niftyMeter').style.width = '0%';
  }
  var net = 0, wins = 0, losses = 0;
  appData.trades.forEach(function(row) {
    var v = num(row.Est_Net_PnL);
    if (v !== null) { net += v; if (v > 0) wins++; else if (v < 0) losses++; }
  });
  setText('pnl', money(net));
  document.getElementById('pnl').className = 'value ' + (net >= 0 ? 'pos' : 'neg');
  setText('winrate', wins + 'W / ' + losses + 'L · ' + (appData.trades.length ? Math.round(wins / appData.trades.length * 100) + '% win rate' : 'no trades'));
}
function refresh(manual) {
  Promise.all([
    fetch('/api/status').then(function(r) { return r.json(); }),
    fetch('/api/scans').then(function(r) { return r.json(); }),
    fetch('/api/trades').then(function(r) { return r.json(); })
  ]).then(function(results) {
    appData.status = results[0];
    appData.scans = results[1] || [];
    appData.trades = results[2] || [];
    if (!capitalLoaded && results[0].capital) {
      document.getElementById('capitalInput').value = results[0].capital;
      capitalLoaded = true;
    }
    setText('capitalLabel', formatCapital(results[0].capital));
    renderKpis();
    renderTables();
    setText('updated', new Date().toLocaleTimeString('en-IN',{hour12:false}));
    if (manual) toast('Dashboard refreshed', 'ok');
  }).catch(function(err) {
    if (manual) toast('Refresh failed: ' + err.message, 'err');
  });
}
function callApi(url, options, message) {
  fetch(url, options).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function() {
    toast(message, 'ok');
    refresh();
  }).catch(function(err) {
    toast('Request failed: ' + err.message, 'err');
  });
}
function startBot(mode) {
  if (mode === 'live' && !confirm('Start LIVE real-money trading? Confirm only if you are ready.')) return;
  postCapital().then(function(data) {
    callApi('/api/start', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode:mode})
    }, mode.toUpperCase() + ' bot started with ' + formatCapital(data.capital));
  }).catch(function(err) {
    toast(err.message, 'err');
  });
}
function stopBot() {
  callApi('/api/stop', {method:'POST'}, 'Stop requested');
}
function tickClock() {
  setText('clock', new Date().toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:false}));
  updateLoginElapsed();
}
document.querySelectorAll('th[data-key]').forEach(function(th) {
  th.addEventListener('click', function() {
    var table = th.closest('table').id;
    var kind = table === 'scanTable' ? 'scan' : 'trade';
    var key = th.getAttribute('data-key');
    var st = sortState[kind];
    st.dir = (st.key === key) ? -st.dir : -1;
    st.key = key;
    renderTables();
  });
});
tickClock();
setInterval(tickClock, 1000);
refresh();
setInterval(function() { refresh(); }, 5000);
setInterval(function() {
  var remain = 5000 - (Date.now() % 5000);
  document.getElementById('refreshbar').style.width = (100 - remain / 50) + '%';
}, 100);
</script>
</body>
</html>""".replace("%PORT%", str(config.DASHBOARD_PORT)).replace("%CAPITAL%", ("%.2f" % config.CAPITAL_PER_TRADE).rstrip("0").rstrip("."))


@app.route("/api/status")
def api_status():
    heartbeat = read_heartbeat()
    bot_state = app_state.load_state()
    open_positions = bot_state.get("open_positions", {})
    return jsonify({
        "heartbeat": heartbeat,
        "capital": app_state.read_capital(),
        "login": app_state.read_login(),
        "state": {
            "date": bot_state.get("date"),
            "traded_today": bot_state.get("traded_today", []),
            "completed_scans": bot_state.get("completed_scans", []),
            "open_positions": open_positions,
            "open_positions_array": list(open_positions.values()),
        },
    })


@app.route("/api/trades")
def api_trades():
    return jsonify(app_state.read_csv_rows(config.trade_csv_path(), 100))


@app.route("/api/scans")
def api_scans():
    return jsonify(app_state.read_csv_rows(config.scan_log_path(), 100))


@app.route("/api/capital", methods=["POST"])
def api_capital():
    payload = request.get_json(silent=True) or {}
    try:
        value = app_state.write_capital(payload.get("capital"))
    except (TypeError, ValueError):
        return jsonify({"capital": app_state.read_capital(), "error": "invalid capital"}), 400
    return jsonify({"capital": value})


@app.route("/api/start", methods=["POST"])
def api_start():
    mode = "paper"
    payload = request.get_json(silent=True) or {}
    if str(payload.get("mode", "")).lower() == "live":
        mode = "live"
    app_state.clear_command()
    flags = ["--live"] if mode == "live" else ["--paper"]
    kwargs = {"cwd": config.BASE_DIR}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen(
        [sys.executable, os.path.join(config.BASE_DIR, "shoonya_scanner_bot.py")] + flags,
        **kwargs
    )
    return jsonify({"started": True, "mode": mode})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    app_state.write_command("stop")
    return jsonify({"stop_requested": True})


if __name__ == "__main__":
    config.ensure_dirs()
    app_state.write_pid(config.DASHBOARD_PID_FILE)
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False, threaded=True)
