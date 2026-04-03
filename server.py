"""
2D ketch-up — Single-file Python Server
FastAPI + WebSocket, 60fps authoritative loop
Infinite chunk world · Camera viewport · OOB respawn
Run:  python server.py
"""
import asyncio, json, math, random, time, uuid
from collections import deque
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

# ─── Embedded client ──────────────────────────────────────────────────────────
_JS = r"""
/* =========================================================
   2D ketch-up — Client (infinite world, camera viewport)
   WebSocket → server  |  Canvas 2D render @ 60fps (rAF)
   ========================================================= */

// ── Audio Engine ───────────────────────────────────────────
const Audio = (() => {
  let ctx = null, master = null;
  let _bgOscs = [], _mode = null, _arpTid = null, _arpStep = 0;

  function _init() {
    if (ctx) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain(); master.gain.value = 0.52;
    master.connect(ctx.destination);
  }

  function _stopBg() {
    clearTimeout(_arpTid); _arpTid = null;
    _bgOscs.forEach(o => { try { o.stop(ctx.currentTime + 0.4); } catch {} });
    _bgOscs = []; _mode = null;
  }

  function _startDrone() {
    // Low-pass filtered ambient drone
    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass'; flt.frequency.value = 680; flt.Q.value = 1.1;
    flt.connect(master);
    const dg = ctx.createGain(); dg.gain.value = 0.11; dg.connect(flt);
    const sg = ctx.createGain(); sg.gain.value = 0.020; sg.connect(master);

    // Bass pair (detuned for warmth)
    const o1 = ctx.createOscillator(); o1.type = 'sine'; o1.frequency.value = 55;
    const o2 = ctx.createOscillator(); o2.type = 'sine'; o2.frequency.value = 55.45;
    const o3 = ctx.createOscillator(); o3.type = 'sine'; o3.frequency.value = 27.5;
    const g3 = ctx.createGain(); g3.gain.value = 0.42;
    o3.connect(g3); g3.connect(dg); o1.connect(dg); o2.connect(dg);

    // High shimmer
    const s1 = ctx.createOscillator(); s1.type = 'sine'; s1.frequency.value = 220;
    const s2 = ctx.createOscillator(); s2.type = 'sine'; s2.frequency.value = 330;
    s1.connect(sg); s2.connect(sg);

    // LFO → filter cutoff (slow sweep)
    const lf1 = ctx.createOscillator(); lf1.type = 'sine'; lf1.frequency.value = 0.065;
    const lg1 = ctx.createGain(); lg1.gain.value = 260;
    lf1.connect(lg1); lg1.connect(flt.frequency);

    // LFO → shimmer pitch (slow wobble)
    const lf2 = ctx.createOscillator(); lf2.type = 'sine'; lf2.frequency.value = 0.12;
    const lg2 = ctx.createGain(); lg2.gain.value = 13;
    lf2.connect(lg2); lg2.connect(s1.frequency);

    // Breathing gain LFO
    const lf3 = ctx.createOscillator(); lf3.type = 'sine'; lf3.frequency.value = 0.037;
    const lg3 = ctx.createGain(); lg3.gain.value = 0.035;
    lf3.connect(lg3); lg3.connect(dg.gain);

    [o1,o2,o3,s1,s2,lf1,lf2,lf3].forEach(o => { o.start(); _bgOscs.push(o); });
  }

  function _runArp() {
    if (_mode !== 'game') return;
    const ARP  = [440, 523.25, 659.25, 830.61]; // Am arpeggio
    const BASS = [55, 55, 69.3, 55];
    const i = _arpStep % 4;

    const oa = ctx.createOscillator(); const ga = ctx.createGain();
    oa.type = 'sine'; oa.frequency.value = ARP[i];
    ga.gain.setValueAtTime(0.025, ctx.currentTime);
    ga.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.26);
    oa.connect(ga); ga.connect(master); oa.start(); oa.stop(ctx.currentTime + 0.28);

    if (_arpStep % 2 === 0) {
      const ob = ctx.createOscillator(); const gb = ctx.createGain();
      ob.type = 'sine'; ob.frequency.value = BASS[i];
      gb.gain.setValueAtTime(0.13, ctx.currentTime);
      gb.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.20);
      ob.connect(gb); gb.connect(master); ob.start(); ob.stop(ctx.currentTime + 0.22);
    }
    _arpStep++;
    _arpTid = setTimeout(_runArp, 310);
  }

  // ── Public ─────────────────────────────────────────────
  function startLobby() {
    if (_mode === 'lobby') return;
    _init(); _stopBg(); _mode = 'lobby'; _startDrone();
  }
  function startGame() {
    if (_mode === 'game') return;
    _init(); _stopBg(); _mode = 'game'; _startDrone(); _runArp();
  }
  function stopAll() { if (ctx) _stopBg(); }

  // ── Sound effects ─────────────────────────────────────
  function shoot() {
    if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sawtooth';
    o.frequency.setValueAtTime(920, ctx.currentTime);
    o.frequency.exponentialRampToValueAtTime(110, ctx.currentTime + 0.07);
    g.gain.setValueAtTime(0.10, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.09);
    o.connect(g); g.connect(master); o.start(); o.stop(ctx.currentTime + 0.10);
  }
  function bounce() {
    if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(1380, ctx.currentTime);
    o.frequency.exponentialRampToValueAtTime(690, ctx.currentTime + 0.055);
    g.gain.setValueAtTime(0.05, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.07);
    o.connect(g); g.connect(master); o.start(); o.stop(ctx.currentTime + 0.08);
  }
  function hit() {
    if (!ctx) return;
    const len = Math.floor(ctx.sampleRate * 0.06);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d   = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    const src = ctx.createBufferSource(); src.buffer = buf;
    const flt = ctx.createBiquadFilter(); flt.type = 'bandpass';
    flt.frequency.value = 340; flt.Q.value = 1.4;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.20, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.07);
    src.connect(flt); flt.connect(g); g.connect(master);
    src.start(); src.stop(ctx.currentTime + 0.08);
  }
  function death() {
    if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(440, ctx.currentTime);
    o.frequency.exponentialRampToValueAtTime(38, ctx.currentTime + 0.85);
    g.gain.setValueAtTime(0.24, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.95);
    o.connect(g); g.connect(master); o.start(); o.stop(ctx.currentTime + 1.0);
    // Noise burst layered on top
    const len2 = Math.floor(ctx.sampleRate * 0.14);
    const buf2 = ctx.createBuffer(1, len2, ctx.sampleRate);
    const d2   = buf2.getChannelData(0);
    for (let i = 0; i < len2; i++) d2[i] = Math.random() * 2 - 1;
    const src2 = ctx.createBufferSource(); src2.buffer = buf2;
    const g2 = ctx.createGain();
    g2.gain.setValueAtTime(0.13, ctx.currentTime);
    g2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
    src2.connect(g2); g2.connect(master);
    src2.start(); src2.stop(ctx.currentTime + 0.2);
  }
  function win() {
    if (!ctx) return;
    [261.63, 329.63, 392, 523.25].forEach((f, i) => {
      setTimeout(() => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = 'sine'; o.frequency.value = f;
        g.gain.setValueAtTime(0.17, ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.42);
        o.connect(g); g.connect(master); o.start(); o.stop(ctx.currentTime + 0.46);
      }, i * 115);
    });
  }

  // ── Mute toggle ───────────────────────────────────────────
  let _muted = false;
  function toggleMute() {
    if (!ctx) return false;
    _muted = !_muted;
    master.gain.value = _muted ? 0 : 0.52;
    return _muted;
  }

  return { startLobby, startGame, stopAll, shoot, bounce, hit, death, win, toggleMute };
})();

// ── Constants (mirrored from server) ───────────────────────
const ZONE_WARNING_JS  = 3.0;   // must match Python ZONE_WARNING
const SCAN_INTERVAL_JS = 50.0;  // must match Python SCAN_INTERVAL
const SCAN_WARN_SECS   = 5.0;   // show warning when next_in ≤ this

// ── Power-up definitions ───────────────────────────────────
const POWERUP_INFO = {
  wall_pass:    { icon: '🧱', name: 'WALL PASS',  color: '#22ccff' },
  invisibility: { icon: '👻', name: 'INVISIBLE',  color: '#aa44ff' },
  speed:        { icon: '⚡', name: 'SPEED',       color: '#ffaa00' },
  super_bullet: { icon: '💥', name: 'S·CANNON',   color: '#ff2060' },
};

// ── State ─────────────────────────────────────────────────
let ws, myId, mySlot;
let mouseWorldX = 0, mouseWorldY = 0;
let gameOver = false;   // set true when game_over received
let worldObstacles = [];    // accumulated across all chunks
let spawnPoints    = [];
let gameW = 1280, gameH = 720, basePlayerR = 20;
let camX  = 0,    camY  = 0;
let gameState = null;
let inGame    = false;

// Input — WASD
const keys = { w:false, a:false, s:false, d:false };
let shooting = false;

// DOM refs
const lobby     = document.getElementById('lobby');
const gameWrap  = document.getElementById('game-wrap');
const statusMsg = document.getElementById('status-msg');
const canvas    = document.getElementById('canvas');
const ctx       = canvas.getContext('2d');
const overlay   = document.getElementById('center-overlay');
const killfeed  = document.getElementById('killfeed');
const hud       = document.getElementById('hud');

// ── Particles ──────────────────────────────────────────────
let particles = [];
function spawnParticles(x, y, color, count = 6) {
  for (let i = 0; i < count; i++) {
    const a = Math.random() * Math.PI * 2;
    const s = 60 + Math.random() * 140;
    particles.push({ x, y, vx: Math.cos(a)*s, vy: Math.sin(a)*s,
      color, life: 0.25 + Math.random()*0.2, maxLife: 0.45,
      r: 2 + Math.random()*3 });
  }
}

// ── Dynamic HUD ────────────────────────────────────────────
const hudCards = {};
function ensureHudCard(p) {
  if (hudCards[p.slot]) return;
  const card    = document.createElement('div');
  card.className = 'pcard'; card.id = `pcard-${p.slot}`;
  const nameEl   = document.createElement('div'); nameEl.className = 'pcard-name';
  const row      = document.createElement('div'); row.className = 'pcard-row';
  const track    = document.createElement('div'); track.className = 'hp-track';
  const bar      = document.createElement('div'); bar.className = 'hp-bar';
  bar.style.width = '100%'; bar.style.background = p.color;
  track.appendChild(bar);
  const scoreEl  = document.createElement('div'); scoreEl.className = 'pcard-score';
  scoreEl.textContent = '0';
  row.appendChild(track); row.appendChild(scoreEl);
  const livesEl  = document.createElement('div'); livesEl.className = 'pcard-lives';
  card.appendChild(nameEl); card.appendChild(row); card.appendChild(livesEl);
  hud.appendChild(card);
  hudCards[p.slot] = { nameEl, hpBarEl: bar, scoreEl, livesEl };
}
function updateHUD(players) {
  for (const p of players) {
    ensureHudCard(p);
    const c = hudCards[p.slot];
    c.nameEl.textContent  = p.name + (p.id === myId ? ' \u25C6' : '');
    c.nameEl.style.color  = p.color;
    c.hpBarEl.style.width = (p.hp / p.maxHp * 100).toFixed(1) + '%';
    c.scoreEl.textContent = `${p.score}`;
    // Lives pips
    const total = p.maxLives ?? 4;
    c.livesEl.innerHTML = Array.from({ length: total }, (_, i) =>
      `<span class="life-pip" style="color:${i < p.lives ? p.color : 'rgba(255,255,255,.12)'}">●</span>`
    ).join('');
  }
}

// ── Kill-feed ──────────────────────────────────────────────
let prevScores = {};
let prevHp = {}, prevAlive = {};
let prevZones  = {};   // id → zone, for collapse particle FX

// ── Ping ───────────────────────────────────────────────────
let currentPing = 0;
function checkKillFeed(players) {
  for (const p of players) {
    const prev = prevScores[p.id] ?? p.score;
    if (p.score > prev) {
      const victim = players.find(x => x.id !== p.id && !x.alive);
      addKillFeed(p.name, victim ? victim.name : '???', p.color,
                  victim ? victim.color : '#888');
    }
    prevScores[p.id] = p.score;
  }
}
function addKillFeed(kName, vName, kColor, vColor) {
  const el = document.createElement('div');
  el.className = 'kf-entry'; el.style.borderColor = kColor;
  el.innerHTML =
    `<span style="color:${kColor}">${kName}</span>` +
    ` <span style="color:#777">\u26A1</span>` +
    ` <span style="color:${vColor}">${vName}</span>`;
  killfeed.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Inventory HUD ──────────────────────────────────────────
function updateInventory(players) {
  const me  = players.find(p => p.id === myId);
  const bar = document.getElementById('inventory-bar');
  if (!bar) return;
  bar.innerHTML = '';
  if (!me) return;

  // Active effects row
  const effs = Object.entries(me.effects || {});
  if (effs.length > 0 || me.super_aiming) {
    const row = document.createElement('div');
    row.className = 'inv-eff-row';
    effs.forEach(([k, t]) => {
      const info = POWERUP_INFO[k]; if (!info) return;
      const tag = document.createElement('div');
      tag.className = 'eff-tag';
      tag.style.color       = info.color;
      tag.style.borderColor = info.color + '44';
      tag.innerHTML = `${info.icon} <span>${info.name}</span> <b>${Math.ceil(t)}s</b>`;
      row.appendChild(tag);
    });
    if (me.super_aiming) {
      const tag = document.createElement('div');
      tag.className = 'eff-tag';
      tag.style.color = '#ff2060'; tag.style.borderColor = '#ff206055';
      tag.innerHTML = '💥 <span>AIM MODE</span> <b>CLICK / SPACE TO FIRE</b>';
      row.appendChild(tag);
    }
    bar.appendChild(row);
  }

  // Inventory slots row
  if (me.inventory.length > 0) {
    const row = document.createElement('div');
    row.className = 'inv-slots-row';
    me.inventory.forEach((ptype, i) => {
      const info = POWERUP_INFO[ptype] || { icon: '?', name: '???', color: '#aaa' };
      const slot = document.createElement('div');
      slot.className = 'inv-slot';
      slot.style.setProperty('--c', info.color);
      slot.title = `[${i+1}] ${info.name}`;
      slot.innerHTML =
        `<span class="inv-icon">${info.icon}</span>` +
        `<span class="inv-name">${info.name}</span>` +
        `<span class="inv-key">[${i+1}]</span>`;
      slot.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN)
          ws.send(JSON.stringify({ type: 'use_powerup', slot: i }));
      });
      row.appendChild(slot);
    });
    bar.appendChild(row);
  }
}

// ── Canvas resize ──────────────────────────────────────────
function resizeCanvas() {
  const maxW  = window.innerWidth  - 20;
  const maxH  = window.innerHeight - 90;
  const scale = Math.min(maxW / gameW, maxH / gameH, 1);
  canvas.width  = gameW; canvas.height = gameH;
  canvas.style.width  = (gameW * scale) + 'px';
  canvas.style.height = (gameH * scale) + 'px';
}
window.addEventListener('resize', resizeCanvas);

// ── Input ──────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  const k = e.key.toLowerCase();
  if (['w','a','s','d'].includes(k)) { keys[k] = true; e.preventDefault(); }
  if (e.code === 'Space') { if (!shooting && inGame) Audio.shoot(); shooting = true; e.preventDefault(); }
  // 1–4 to use powerup slots
  if (inGame && e.key >= '1' && e.key <= '4') {
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ type: 'use_powerup', slot: parseInt(e.key) - 1 }));
  }
});
document.addEventListener('keyup', e => {
  const k = e.key.toLowerCase();
  if (['w','a','s','d'].includes(k)) keys[k] = false;
  if (e.code === 'Space') shooting = false;
});
canvas.addEventListener('mousedown',   e => { if (e.button===0) { if (!shooting && inGame) Audio.shoot(); shooting = true; } });
canvas.addEventListener('mouseup',     e => { if (e.button===0) shooting = false; });
canvas.addEventListener('contextmenu', e => e.preventDefault());

// Mouse position in world-space (for super-bullet aiming)
canvas.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  const sx = gameW / rect.width, sy = gameH / rect.height;
  mouseWorldX = camX + (e.clientX - rect.left) * sx;
  mouseWorldY = camY + (e.clientY - rect.top)  * sy;
});

// ── Send input @ 60fps ─────────────────────────────────────
setInterval(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN || !inGame || !gameState) return;
  const me = gameState.players?.find(p => p.id === myId);
  const superAim = me?.super_aiming ?? false;
  const aimAngle = superAim && me
    ? Math.atan2(mouseWorldY - me.y, mouseWorldX - me.x)
    : null;
  ws.send(JSON.stringify({
    type:  'input',
    up:    !superAim && keys.w,
    down:  !superAim && keys.s,
    left:  !superAim && keys.a,
    right: !superAim && keys.d,
    shoot: shooting,
    ping:  currentPing,
    aim_angle: aimAngle,
  }));
}, 1000 / 60);

// ── Ping heartbeat @ 1/sec ─────────────────────────────────
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({ type: 'ping', t: Date.now() }));
}, 1000);

// ── Render ─────────────────────────────────────────────────
const BOUNCE_TINTS = [
  '#ffffff','#ffee55','#ffcc00','#ff9900','#ff6600',
  '#ff3300','#ff0000','#ff0055','#ff00aa','#cc00ff','#8800ff'
];
const BOUNCE_SIZES = [5,5,6,6,7,7,8,8,9,10,12];
const BOUNCE_GLOW  = [12,14,16,18,20,22,26,30,34,38,46];

let lastRaf = 0;

function renderFrame(now) {
  requestAnimationFrame(renderFrame);
  const dt = Math.min((now - lastRaf) / 1000, 0.05);
  lastRaf  = now;

  if (!inGame || !gameState) { ctx.clearRect(0,0,gameW,gameH); return; }

  // Advance particles
  particles = particles.filter(p => {
    p.x += p.vx*dt; p.y += p.vy*dt; p.life -= dt; return p.life > 0;
  });

  const { players, bullets } = gameState;

  // ── Background (screen space) ─────────────────────────────
  ctx.fillStyle = '#060608';
  ctx.fillRect(0, 0, gameW, gameH);

  // ── World-space rendering (translated by camera) ──────────
  ctx.save();
  ctx.translate(-camX, -camY);

  // Scrolling grid
  ctx.strokeStyle = '#111111'; ctx.lineWidth = 1;
  const gStep = 60;
  const gx0 = Math.floor(camX / gStep) * gStep;
  const gy0 = Math.floor(camY / gStep) * gStep;
  for (let x = gx0; x <= camX + gameW + gStep; x += gStep) {
    ctx.beginPath(); ctx.moveTo(x, camY); ctx.lineTo(x, camY+gameH); ctx.stroke();
  }
  for (let y = gy0; y <= camY + gameH + gStep; y += gStep) {
    ctx.beginPath(); ctx.moveTo(camX, y); ctx.lineTo(camX+gameW, y); ctx.stroke();
  }

  // Obstacles (world-space coords already)
  for (const obs of worldObstacles) {
    // Cull off-screen obstacles
    if (obs.x > camX+gameW+4 || obs.x+obs.w < camX-4 ||
        obs.y > camY+gameH+4 || obs.y+obs.h < camY-4) continue;
    ctx.fillStyle = '#111118';
    ctx.fillRect(obs.x, obs.y, obs.w, obs.h);
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(obs.x, obs.y, obs.w, 3);
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(obs.x, obs.y+obs.h-3, obs.w, 3);
    ctx.strokeStyle = '#0044cc'; ctx.lineWidth = 1.5;
    ctx.strokeRect(obs.x, obs.y, obs.w, obs.h);
  }

  // ── Collapse zones ─────────────────────────────────────────
  for (const zone of (gameState.zones || [])) {
    const t = zone.timer;                   // 3 → 0
    const frac = t / ZONE_WARNING_JS;       // 1 → 0  (0 = about to collapse)
    // Pulse rate: slow at start, rapid near collapse
    const hz  = 1.5 + (1 - frac) * 7.5;
    const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 1000 * Math.PI * 2 * hz);
    const danger = 1 - frac;               // 0→1

    ctx.save();
    // Diagonal stripes fill
    ctx.beginPath(); ctx.rect(zone.x, zone.y, zone.w, zone.h); ctx.clip();
    ctx.strokeStyle = `rgba(255, 40, 40, ${(0.12 + 0.22 * danger) * pulse})`;
    ctx.lineWidth = 12;
    for (let d = -zone.h; d < zone.w + zone.h; d += 24) {
      ctx.beginPath();
      ctx.moveTo(zone.x + d, zone.y);
      ctx.lineTo(zone.x + d + zone.h, zone.y + zone.h);
      ctx.stroke();
    }

    // Semi-transparent red fill
    ctx.fillStyle = `rgba(220, 20, 20, ${(0.06 + 0.28 * danger) * pulse})`;
    ctx.fillRect(zone.x, zone.y, zone.w, zone.h);
    ctx.restore();

    // Border glow
    ctx.save();
    ctx.shadowBlur = 18 * pulse; ctx.shadowColor = '#ff1010';
    ctx.strokeStyle = `rgba(255, 50, 50, ${(0.65 + 0.35 * danger) * pulse})`;
    ctx.lineWidth = 2 + danger * 2;
    ctx.strokeRect(zone.x, zone.y, zone.w, zone.h);
    ctx.restore();

    // Countdown number
    const fontSize = 18 + danger * 14;
    ctx.save();
    ctx.font = `800 ${Math.round(fontSize)}px Nunito`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.shadowBlur = 12 * pulse; ctx.shadowColor = '#ff0000';
    ctx.fillStyle = `rgba(255, ${Math.round(200 - 160 * danger)}, ${Math.round(200 - 160 * danger)}, ${0.8 + 0.2 * pulse})`;
    ctx.fillText(Math.ceil(t) + 's', zone.x + zone.w / 2, zone.y + zone.h / 2);
    ctx.restore();
  }

  // ── Reward boxes ───────────────────────────────────────────
  const _rT = performance.now() / 1000;
  for (const box of (gameState.boxes || [])) {
    const pulse  = 0.6 + 0.4 * Math.sin(_rT * 2.8 + box.x * 0.01);
    const floatY = Math.sin(_rT * 1.6 + box.y * 0.01) * 4;
    const bx = box.x, by = box.y + floatY;
    const sz = 22;

    ctx.save();
    ctx.translate(bx, by);
    ctx.rotate(_rT * 0.9);
    ctx.shadowBlur = 28 * pulse; ctx.shadowColor = '#1133ee';
    // Outer frame
    ctx.strokeStyle = `rgba(50, 110, 255, ${0.9 * pulse})`;
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-sz, -sz, sz * 2, sz * 2);
    // Dark fill
    ctx.fillStyle = 'rgba(2, 5, 38, 0.94)';
    ctx.fillRect(-sz + 1, -sz + 1, sz * 2 - 2, sz * 2 - 2);
    // Inner border
    ctx.strokeStyle = `rgba(100, 160, 255, ${0.4 * pulse})`;
    ctx.lineWidth = 1;
    ctx.strokeRect(-sz + 5, -sz + 5, sz * 2 - 10, sz * 2 - 10);
    // Scan line
    const sl = -sz + 4 + (sz * 2 - 8) * ((_rT * 0.55) % 1.0);
    ctx.strokeStyle = `rgba(80, 150, 255, ${0.3 * pulse})`;
    ctx.beginPath(); ctx.moveTo(-sz + 2, sl); ctx.lineTo(sz - 2, sl); ctx.stroke();
    ctx.restore();

    // Icon (non-rotated)
    ctx.save();
    ctx.translate(bx, by);
    ctx.shadowBlur = 10; ctx.shadowColor = '#2255ff';
    ctx.font = `bold 17px Nunito`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const _icons = { wall_pass:'🧱', invisibility:'👻', speed:'⚡', super_bullet:'💥' };
    ctx.fillText(_icons[box.type] || '?', 0, 0);
    ctx.restore();

    // Life bar
    const lifeFrac = Math.max(0, box.life / 30);
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(bx - sz, by + sz + 5, sz * 2, 3);
    ctx.fillStyle = `rgba(60, 120, 255, ${0.75 * pulse})`;
    ctx.fillRect(bx - sz, by + sz + 5, sz * 2 * lifeFrac, 3);
  }

  // Bullets
  for (const b of bullets) {
    // Super bullet: special large render
    if (b.is_super) {
      const sp = 0.75 + 0.25 * Math.sin(performance.now() / 120);
      ctx.save();
      ctx.shadowBlur = 52 * sp; ctx.shadowColor = '#ff2060';
      ctx.beginPath(); ctx.arc(b.x, b.y, 14, 0, Math.PI * 2);
      ctx.fillStyle = '#ff2060'; ctx.fill();
      ctx.shadowBlur = 0;
      ctx.beginPath(); ctx.arc(b.x, b.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff'; ctx.fill();
      ctx.restore();
      continue;
    }
    const bn   = Math.min(b.bounces ?? 0, 10);
    const tint = BOUNCE_TINTS[bn];
    const size = BOUNCE_SIZES[bn];
    ctx.save();
    ctx.shadowBlur = BOUNCE_GLOW[bn]; ctx.shadowColor = tint;
    ctx.beginPath(); ctx.arc(b.x, b.y, size+1, 0, Math.PI*2);
    ctx.fillStyle = tint; ctx.fill();
    ctx.beginPath(); ctx.arc(b.x, b.y, size-1, 0, Math.PI*2);
    ctx.fillStyle = b.color; ctx.fill();
    if (bn > 0) {
      for (let i = 0; i < bn; i++) {
        ctx.beginPath();
        ctx.arc(b.x-(bn-1)*4+i*8, b.y-size-5, 2, 0, Math.PI*2);
        ctx.fillStyle = tint; ctx.fill();
      }
    }
    ctx.restore();
  }

  // Particles
  for (const p of particles) {
    const a = p.life / p.maxLife;
    ctx.save();
    ctx.globalAlpha = a; ctx.shadowBlur = 8; ctx.shadowColor = p.color;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r*a, 0, Math.PI*2);
    ctx.fillStyle = p.color; ctx.fill();
    ctx.restore();
  }

  // Players
  let myPlayer = null;
  for (const p of players) {
    if (p.id === myId) myPlayer = p;
    const pr = p.r ?? basePlayerR;

    // Invisible players: skip if enemy, dim if self
    if (p.invisible && p.id !== myId) continue;

    if (!p.alive) {
      // Ghost at spawn
      const sp = spawnPoints[p.slot] || { x: gameW/2, y: gameH/2 };
      ctx.save(); ctx.globalAlpha = 0.35;
      ctx.strokeStyle = p.color; ctx.lineWidth = 2;
      ctx.setLineDash([6,6]);
      ctx.beginPath(); ctx.arc(sp.x, sp.y, pr+6, 0, Math.PI*2); ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.7; ctx.fillStyle = p.color;
      ctx.font = `bold ${Math.max(14,pr)}px Nunito`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(Math.max(0, Math.ceil(p.respawnMs/1000)), sp.x, sp.y);
      ctx.restore();
      continue;
    }

    // Effect auras (drawn before player)
    const _effs = p.effects || {};
    const _aT = performance.now() / 1000;
    if ('wall_pass' in _effs) {
      const wp = (_aT * 1.4) % 1.0;
      ctx.save();
      ctx.strokeStyle = `rgba(0, 210, 255, ${0.55 * (1 - wp)})`;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, pr + 7 + wp * 18, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    }
    if ('speed' in _effs) {
      const sp2 = 0.5 + 0.4 * Math.sin(_aT * 7 + p.x * 0.01);
      ctx.save();
      ctx.shadowBlur = 22; ctx.shadowColor = '#ffaa00';
      ctx.strokeStyle = `rgba(255, 165, 20, ${sp2})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(p.x, p.y, pr + 8, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    if (p.invisible) ctx.globalAlpha = 0.28;  // self: ghost-dim
    ctx.translate(p.x, p.y);
    ctx.shadowBlur = 24; ctx.shadowColor = p.color;

    ctx.beginPath(); ctx.arc(0, 0, pr, 0, Math.PI*2);
    ctx.fillStyle = p.color; ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.lineWidth = 2; ctx.stroke();

    if (p.id === myId) {
      ctx.beginPath(); ctx.arc(0, 0, pr+4, 0, Math.PI*2);
      ctx.strokeStyle = 'rgba(255,255,255,0.25)';
      ctx.lineWidth = 1; ctx.setLineDash([4,4]); ctx.stroke(); ctx.setLineDash([]);
    }

    ctx.rotate(p.angle); ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.fillRect(pr-4, -4, pr+4, 8);
    ctx.fillStyle = p.color;
    ctx.fillRect(pr-2, -3, pr+2, 6);

    ctx.beginPath(); ctx.arc(0, 0, 4, 0, Math.PI*2);
    ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fill();
    ctx.restore();

    // HP bar + name (world space, no rotation)
    const bw = pr*2.8, bh = 6;
    const bx = p.x - bw/2, by = p.y - pr - 14;
    const frac = p.hp / p.maxHp;
    ctx.fillStyle = 'rgba(0,0,0,0.7)'; ctx.fillRect(bx-1,by-1,bw+2,bh+2);
    ctx.fillStyle = '#1a1a1a';          ctx.fillRect(bx,by,bw,bh);
    ctx.fillStyle = p.color;
    ctx.fillRect(bx, by, bw*frac, bh);
    ctx.fillStyle = p.color;
    ctx.font = `${Math.max(10,pr*0.6)}px Nunito`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.fillText(p.name+(p.id===myId?' \u25C6':''), p.x, p.y-pr-18);
  }

  // Super-bullet aim line (world-space, only for local player)
  const _me = players.find(p => p.id === myId);
  if (_me && _me.super_aiming && _me.alive) {
    const _aimAng = Math.atan2(mouseWorldY - _me.y, mouseWorldX - _me.x);
    const _lineLen = 2200;
    const _ex = _me.x + Math.cos(_aimAng) * _lineLen;
    const _ey = _me.y + Math.sin(_aimAng) * _lineLen;
    const _ap = 0.55 + 0.35 * Math.sin(performance.now() / 160);
    ctx.save();
    ctx.setLineDash([14, 9]);
    ctx.strokeStyle = `rgba(255, 30, 80, ${_ap})`;
    ctx.lineWidth = 2.2;
    ctx.shadowBlur = 16; ctx.shadowColor = '#ff1050';
    ctx.beginPath(); ctx.moveTo(_me.x, _me.y); ctx.lineTo(_ex, _ey); ctx.stroke();
    ctx.setLineDash([]);
    // Crosshair dot at mouse
    ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.arc(mouseWorldX, mouseWorldY, 7, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(255, 30, 80, ${_ap * 0.8})`;
    ctx.lineWidth = 2; ctx.stroke();
    ctx.restore();
  }

  ctx.restore();  // end world-space transform

  // ── Screen-space overlays ─────────────────────────────────

  // "Waiting" overlay
  if (players.length < 2) {
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(0,0,gameW,gameH);
    ctx.fillStyle = '#aaaaaa'; ctx.font = 'bold 26px Nunito';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Waiting for opponent...', gameW/2, gameH/2-18);
    ctx.font = '14px Nunito'; ctx.fillStyle = '#666666';
    ctx.fillText(`Players: ${players.length} / 2+`, gameW/2, gameH/2+18);
    ctx.restore();
  }

  // OOB warning edge flash
  if (myPlayer && myPlayer.alive) {
    const px = myPlayer.x - camX, py = myPlayer.y - camY;
    const edgeDist = Math.min(px, py, gameW-px, gameH-py);
    if (edgeDist < 120) {
      const alpha = (1 - edgeDist/120) * 0.45;
      ctx.save();
      const grad = ctx.createRadialGradient(gameW/2,gameH/2,gameH*0.3,gameW/2,gameH/2,gameH*0.8);
      grad.addColorStop(0, 'rgba(255,60,60,0)');
      grad.addColorStop(1, `rgba(255,20,20,${alpha})`);
      ctx.fillStyle = grad; ctx.fillRect(0,0,gameW,gameH);
      ctx.restore();
    }
  }

  // ── Green scan line (screen-space) ─────────────────────────
  const scan = gameState.scan;
  if (scan) {
    const now_ms = performance.now();

    if (scan.active) {
      const sx = scan.frac * gameW;   // screen-x of line

      // Scanned area tint (already-passed region)
      ctx.save();
      ctx.fillStyle = 'rgba(0, 255, 100, 0.055)';
      ctx.fillRect(0, 0, sx, gameH);
      ctx.restore();

      // Beam glow to the left of the line
      ctx.save();
      const grad = ctx.createLinearGradient(Math.max(0, sx - 120), 0, sx, 0);
      grad.addColorStop(0, 'rgba(0,255,100,0)');
      grad.addColorStop(1, 'rgba(0,255,100,0.18)');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.max(0, sx - 120), 0, Math.min(120, sx), gameH);
      ctx.restore();

      // Main green vertical line
      ctx.save();
      ctx.shadowBlur  = 28;
      ctx.shadowColor = '#00ff66';
      ctx.strokeStyle = 'rgba(0, 255, 100, 0.92)';
      ctx.lineWidth   = 2.5;
      ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, gameH); ctx.stroke();
      // Bright core
      ctx.shadowBlur  = 0;
      ctx.strokeStyle = 'rgba(200, 255, 230, 0.85)';
      ctx.lineWidth   = 1;
      ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, gameH); ctx.stroke();
      ctx.restore();

      // Tick marks along line
      ctx.save();
      ctx.strokeStyle = 'rgba(0, 255, 100, 0.55)';
      ctx.lineWidth   = 1;
      for (let ty = 0; ty < gameH; ty += 36) {
        const tickLen = (ty % 108 === 0) ? 12 : 6;
        ctx.beginPath();
        ctx.moveTo(sx - tickLen, ty);
        ctx.lineTo(sx + tickLen, ty);
        ctx.stroke();
      }
      ctx.restore();

      // "▶ SCANNING" label
      ctx.save();
      const pulse = 0.7 + 0.3 * Math.sin(now_ms * 0.008);
      ctx.font      = `800 15px Nunito`;
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      ctx.shadowBlur = 10; ctx.shadowColor = '#00ff66';
      ctx.fillStyle  = `rgba(0, 255, 120, ${pulse})`;
      const labelX = Math.min(sx + 8, gameW - 110);
      ctx.fillText('▶ SCANNING', labelX, 12);
      ctx.restore();
    }

    // Pre-scan countdown warning (shown when scan is coming soon)
    if (!scan.active && scan.next_in <= SCAN_WARN_SECS && scan.next_in > 0) {
      const urgency = 1 - (scan.next_in / SCAN_WARN_SECS);  // 0→1
      const hz      = 1.2 + urgency * 5;
      const blink   = 0.5 + 0.5 * Math.sin(performance.now() / 1000 * Math.PI * 2 * hz);
      ctx.save();
      ctx.font      = `800 17px Nunito`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.shadowBlur = 14 * blink; ctx.shadowColor = '#00ff88';
      ctx.fillStyle  = `rgba(60, 255, 140, ${(0.7 + 0.3 * urgency) * blink})`;
      ctx.fillText(`⚠ SCAN IN ${Math.ceil(scan.next_in)}s — STAND STILL`, gameW / 2, 14);
      ctx.restore();
    }
  }

  // Respawn overlay
  if (myPlayer && !myPlayer.alive) {
    overlay.style.display = 'block';
    overlay.style.color   = myPlayer.color;
    overlay.textContent   = `Respawning in ${Math.max(0,Math.ceil(myPlayer.respawnMs/1000))}...`;
  } else {
    overlay.style.display = 'none';
  }

  checkKillFeed(players);
}

// ── WebSocket ──────────────────────────────────────────────
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => { statusMsg.textContent = 'Connected \u2014 joining...'; };

  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    switch (msg.type) {

      case 'connected':
        myId = msg.pid; break;

      case 'waiting':
        statusMsg.innerHTML =
          msg.msg + `<br><small style="color:#555">Players online: ${msg.playerCount}</small>`;
        break;

      case 'init':
        myId  = msg.myId; mySlot = msg.mySlot;
        gameW = msg.gameW; gameH = msg.gameH;
        basePlayerR = msg.playerR;
        worldObstacles = msg.obstacles || [];
        spawnPoints    = msg.spawnPoints || [];
        camX = msg.camX || 0; camY = msg.camY || 0;
        inGame = true;
        hud.innerHTML = '';
        Object.keys(hudCards).forEach(k => delete hudCards[k]);
        Object.keys(prevScores).forEach(k => delete prevScores[k]);
        Object.keys(prevHp).forEach(k => delete prevHp[k]);
        Object.keys(prevAlive).forEach(k => delete prevAlive[k]);
        lobby.style.display    = 'none';
        gameWrap.style.display = 'flex';
        resizeCanvas();
        Audio.startGame();
        const pd = document.getElementById('ping-display');
        if (pd) pd.style.display = 'block';
        const mb = document.getElementById('mute-btn');
        if (mb) mb.style.display = 'block';
        const ib = document.getElementById('inventory-bar');
        if (ib) ib.style.display = 'flex';
        break;

      case 'state': {
        const prev = gameState;
        gameState  = msg;
        camX = msg.camX ?? camX;
        camY = msg.camY ?? camY;
        // Accumulate new chunk obstacles
        if (msg.newObs?.length) worldObstacles.push(...msg.newObs);
        if (prev) {
          const curIds = new Set(msg.bullets.map(b => b.id));
          for (const b of prev.bullets)
            if (!curIds.has(b.id)) spawnParticles(b.x, b.y, b.color, 5);
        }
        updateHUD(msg.players);
        updateInventory(msg.players);
        // ── Collapse zone particle FX ───────────────────────
        const curZIds = new Set((msg.zones || []).map(z => z.id));
        for (const [id, z] of Object.entries(prevZones)) {
          if (!curZIds.has(id))
            spawnParticles(z.x + z.w/2, z.y + z.h/2, '#ff3030', 24);
        }
        prevZones = {};
        for (const z of (msg.zones || [])) prevZones[z.id] = z;
        // ── Sound effects ──────────────────────────────────
        for (const p of msg.players) {
          const wasAlive = prevAlive[p.id] ?? true;
          const prevH    = prevHp[p.id]    ?? p.hp;
          if (p.alive  && prevH > p.hp)  Audio.hit();
          if (wasAlive && !p.alive)       Audio.death();
          prevHp[p.id]    = p.hp;
          prevAlive[p.id] = p.alive;
        }
        if (prev) {
          const pb = {};
          for (const b of prev.bullets) pb[b.id] = b.bounces ?? 0;
          for (const b of msg.bullets)
            if (b.id in pb && (b.bounces ?? 0) > pb[b.id]) Audio.bounce();
        }
        break;
      }

      case 'player_left':
        addKillFeed('Player','disconnected','#888','#555'); break;

      case 'full':
        statusMsg.textContent = msg.msg; break;

      case 'pong': {
        currentPing = Math.round(Date.now() - msg.t);
        const pd = document.getElementById('ping-display');
        if (pd) {
          pd.textContent = `${currentPing} ms`;
          pd.style.color = currentPing < 50
            ? 'rgba(0,220,100,.55)'
            : currentPing < 120
            ? 'rgba(255,210,0,.55)'
            : 'rgba(255,70,70,.6)';
        }
        break;
      }

      case 'game_over': {
        gameOver = true;
        Audio.stopAll();
        Audio.win();
        const ov = document.getElementById('center-overlay');
        ov.style.display = 'block';
        ov.style.color   = msg.winnerColor || '#ffffff';
        ov.innerHTML =
          `<div style="font-size:2rem;letter-spacing:3px">${msg.winnerName || 'Player'}</div>` +
          `<div style="font-size:.95rem;margin-top:10px;opacity:.65;letter-spacing:2px;font-weight:400">WINS \u00b7 Restarting in 3s...</div>`;
        setTimeout(() => location.reload(), 3000);
        break;
      }
    }
  };

  ws.onclose = () => {
    if (gameOver) return;   // normal restart, already handled
    if (inGame) { alert('Connection lost. Reloading...'); location.reload(); }
    else { statusMsg.textContent = 'Disconnected. Reconnecting...'; setTimeout(connect, 2000); }
  };
  ws.onerror = () => { statusMsg.textContent = 'Connection error. Retrying...'; };
}

// ── Human verification ─────────────────────────────────────
(function () {
  const verifyScreen = document.getElementById('verify');
  const verifyBtn    = document.getElementById('verify-btn');
  const verifyCheck  = document.getElementById('verify-check');
  const verifyLabel  = document.getElementById('verify-label');

  // Ripple on button click, then proceed
  // e.isTrusted = false for programmatic/bot clicks — reject them
  verifyBtn.addEventListener('click', (e) => {
    if (!e.isTrusted) return;   // block automated/headless clicks
    if (verifyBtn.dataset.done) return;
    verifyBtn.dataset.done = '1';

    // Animate check → swap text
    verifyCheck.classList.add('checked');
    verifyLabel.textContent = 'Verified \u2014 entering...';
    verifyBtn.style.pointerEvents = 'none';

    Audio.startLobby();
    setTimeout(() => {
      verifyScreen.style.opacity = '0';
      setTimeout(() => {
        verifyScreen.style.display = 'none';
        document.getElementById('lobby').style.display = 'flex';
        connect();
      }, 380);
    }, 520);
  });
})();

// ── Mute button ────────────────────────────────────────────
(function () {
  const btn = document.getElementById('mute-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const muted = Audio.toggleMute();
    btn.textContent = muted ? '🔇' : '🔊';
    btn.title = muted ? 'Unmute' : 'Mute';
  });
})();

// ── Boot ───────────────────────────────────────────────────
requestAnimationFrame(renderFrame);
"""

_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nomad's Game · 游牧者的游戏</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ─── Reset ─────────────────────────────────────────────────────────────── */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

/* ─── Body + ambient orbs ─────────────────────────────────────────────── */
body {
  background: #000000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  overflow: hidden;
  font-family: 'Nunito', ui-rounded, -apple-system, BlinkMacSystemFont, sans-serif;
  color: #ffffff;
  user-select: none;
}

/* Ambient background glow orbs */
body::before {
  content: '';
  position: fixed;
  width: 700px; height: 700px;
  background: radial-gradient(circle, rgba(0,100,255,.13) 0%, transparent 65%);
  top: -260px; left: -220px;
  pointer-events: none;
  z-index: 0;
}
body::after {
  content: '';
  position: fixed;
  width: 560px; height: 560px;
  background: radial-gradient(circle, rgba(0,60,200,.10) 0%, transparent 65%);
  bottom: -180px; right: -160px;
  pointer-events: none;
  z-index: 0;
}

/* ─── Lobby card ─────────────────────────────────────────────────────── */
#lobby {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
  padding: 52px 64px 44px;
  background: rgba(0, 8, 24, 0.82);
  backdrop-filter: blur(36px) saturate(180%);
  -webkit-backdrop-filter: blur(36px) saturate(180%);
  border: 1px solid rgba(0, 118, 255, 0.22);
  border-radius: 28px;
  box-shadow:
    0 0 0 1px rgba(0, 118, 255, 0.08),
    0 24px 72px rgba(0, 0, 0, 0.85),
    0 0 100px rgba(0, 90, 255, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

/* Thin top-edge highlight */
#lobby::before {
  content: '';
  position: absolute;
  top: 0; left: 10%; right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,140,255,.45), transparent);
  border-radius: 1px;
}

#lobby h1 {
  font-size: 2.1rem;
  font-weight: 700;
  letter-spacing: 5px;
  text-transform: uppercase;
  background: linear-gradient(135deg, #ffffff 0%, #4da8ff 55%, #0060df 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 0 18px rgba(0,120,255,.35));
}

#status-msg {
  font-size: 1rem;
  font-weight: 400;
  letter-spacing: .5px;
  color: rgba(255,255,255,.6);
  min-height: 1.4em;
  text-align: center;
}

/* ─── Pulse ring ──────────────────────────────────────────────────────── */
.pulse-ring {
  position: relative;
  width: 60px; height: 60px;
}
.pulse-ring::before,
.pulse-ring::after,
.pulse-ring > span {
  content: '';
  display: block;
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  border: 1.5px solid rgba(10,132,255,.75);
  border-radius: 50%;
}
.pulse-ring::before { width:60px; height:60px; box-shadow:0 0 18px rgba(0,120,255,.25); }
.pulse-ring::after  {
  width:60px; height:60px;
  border-color: rgba(10,132,255,.3);
  animation: ripple 1.8s ease-out infinite;
}
.pulse-ring > span {
  width:60px; height:60px;
  border-color: rgba(10,132,255,.15);
  animation: ripple 1.8s ease-out infinite .45s;
}
@keyframes ripple {
  0%   { width:60px;  height:60px;  opacity:1; }
  100% { width:120px; height:120px; opacity:0; }
}

/* ─── Dot loader ──────────────────────────────────────────────────────── */
.dot-loader { display:flex; gap:9px; align-items:center; }
.dot-loader span {
  width: 7px; height: 7px;
  background: rgba(10,132,255,.85);
  border-radius: 50%;
  box-shadow: 0 0 10px rgba(10,132,255,.5);
  animation: dotBounce 1.1s ease-in-out infinite;
}
.dot-loader span:nth-child(2) { animation-delay:.18s; }
.dot-loader span:nth-child(3) { animation-delay:.36s; }
@keyframes dotBounce {
  0%, 80%, 100% { transform:scale(0); opacity:.3; }
  40%           { transform:scale(1); opacity:1; }
}

/* ─── Controls hint ───────────────────────────────────────────────────── */
.controls-hint {
  font-size: .72rem;
  font-weight: 400;
  color: rgba(255,255,255,.4);
  letter-spacing: .4px;
  line-height: 1.9;
  text-align: center;
}

/* ─── Game wrapper ────────────────────────────────────────────────────── */
#game-wrap {
  position: relative;
  z-index: 1;
  display: none;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

/* ─── HUD player cards ────────────────────────────────────────────────── */
#hud {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 7px;
  width: 100%;
  padding: 2px 6px;
}
.pcard {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 148px;
  flex: 1 1 148px;
  max-width: 210px;
  padding: 8px 13px;
  background: rgba(0, 8, 24, 0.80);
  backdrop-filter: blur(24px) saturate(160%);
  -webkit-backdrop-filter: blur(24px) saturate(160%);
  border: 1px solid rgba(0, 100, 255, 0.20);
  border-radius: 14px;
  box-shadow:
    0 4px 20px rgba(0,0,0,.6),
    inset 0 1px 0 rgba(255,255,255,.06);
}
.pcard-name {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .8px;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #ffffff;
}
.pcard-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.hp-track {
  flex: 1;
  height: 5px;
  background: rgba(255,255,255,.12);
  border-radius: 99px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.08);
}
.hp-bar {
  height: 100%;
  border-radius: 99px;
  transition: width .1s linear;
  box-shadow: 0 0 8px rgba(10,132,255,.55);
}
.pcard-score {
  font-size: 10px;
  font-weight: 600;
  color: rgba(255,255,255,.5);
  white-space: nowrap;
  letter-spacing: .4px;
}
.pcard-lives {
  display: flex;
  gap: 4px;
  margin-top: 1px;
}
.life-pip {
  font-size: 9px;
  line-height: 1;
  transition: color .25s;
}

/* ─── Canvas ──────────────────────────────────────────────────────────── */
canvas {
  display: block;
  image-rendering: pixelated;
  border: 1px solid rgba(0, 100, 255, 0.22);
  border-radius: 14px;
  box-shadow:
    0 0 0 1px rgba(0, 100, 255, 0.06),
    0 0 60px rgba(0, 80, 220, 0.10),
    0 28px 80px rgba(0, 0, 0, 0.65),
    inset 0 0 0 1px rgba(255,255,255,.025);
}

/* ─── Bottom hint ─────────────────────────────────────────────────────── */
#ctrl-hint {
  font-size: 10.5px;
  font-weight: 400;
  color: rgba(255,255,255,.32);
  letter-spacing: .5px;
  text-align: center;
}

/* ─── Kill feed ───────────────────────────────────────────────────────── */
#killfeed {
  position: fixed;
  top: 16px; right: 16px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  pointer-events: none;
  z-index: 20;
}
.kf-entry {
  background: rgba(0, 8, 24, 0.90);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  border: 1px solid rgba(0, 100, 255, 0.22);
  border-left: 2.5px solid #0066ff;
  padding: 5px 12px;
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: .3px;
  border-radius: 9px;
  color: #ffffff;
  box-shadow: 0 4px 20px rgba(0,0,0,.6);
  animation: kfIn .22s cubic-bezier(.34,1.26,.64,1) both;
}
@keyframes kfIn {
  from { opacity:0; transform:translateX(18px) scale(.95); }
}

/* ─── Human verify screen ────────────────────────────────────────────── */
#verify {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000000;
  transition: opacity .38s ease;
}
#verify::before {
  content: '';
  position: absolute;
  width: 700px; height: 700px;
  background: radial-gradient(circle, rgba(0,100,255,.13) 0%, transparent 65%);
  top: -260px; left: -220px;
  pointer-events: none;
}
#verify::after {
  content: '';
  position: absolute;
  width: 560px; height: 560px;
  background: radial-gradient(circle, rgba(0,60,200,.10) 0%, transparent 65%);
  bottom: -180px; right: -160px;
  pointer-events: none;
}
#verify-card {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  padding: 52px 72px 48px;
  background: rgba(0, 8, 24, 0.88);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid rgba(0, 118, 255, 0.22);
  border-radius: 28px;
  box-shadow:
    0 0 0 1px rgba(0, 118, 255, 0.10),
    0 24px 72px rgba(0, 0, 0, 0.90),
    0 0 120px rgba(0, 90, 255, 0.10),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
#verify-card::before {
  content: '';
  position: absolute;
  top: 0; left: 10%; right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,140,255,.5), transparent);
}
#verify-card h1 {
  font-size: 2.1rem;
  font-weight: 700;
  letter-spacing: 5px;
  text-transform: uppercase;
  background: linear-gradient(135deg, #ffffff 0%, #4da8ff 55%, #0060df 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 0 18px rgba(0,120,255,.35));
}
#verify-card p {
  font-size: .9rem;
  font-weight: 400;
  color: rgba(255,255,255,.55);
  letter-spacing: .5px;
  text-align: center;
  line-height: 1.7;
}
#verify-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 15px 36px;
  background: rgba(0, 100, 255, 0.10);
  border: 1px solid rgba(0, 130, 255, 0.32);
  border-radius: 14px;
  cursor: pointer;
  font-family: inherit;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: .5px;
  color: #ffffff;
  transition: background .18s, border-color .18s, box-shadow .18s, transform .12s;
  user-select: none;
  box-shadow: 0 0 0 0 rgba(0,120,255,0);
}
#verify-btn:hover {
  background: rgba(0, 110, 255, 0.18);
  border-color: rgba(0, 150, 255, 0.55);
  box-shadow: 0 0 28px rgba(0,100,255,.18);
  transform: translateY(-1px);
}
#verify-btn:active { transform: translateY(0px); }

/* Custom checkbox */
#verify-check {
  width: 22px; height: 22px;
  border: 2px solid rgba(0, 130, 255, 0.55);
  border-radius: 6px;
  background: rgba(0, 80, 200, 0.08);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background .22s, border-color .22s;
  position: relative;
  overflow: hidden;
}
#verify-check::after {
  content: '';
  width: 12px; height: 7px;
  border-left: 2.5px solid #fff;
  border-bottom: 2.5px solid #fff;
  transform: rotate(-45deg) scale(0);
  transition: transform .2s cubic-bezier(.34,1.56,.64,1) .08s;
}
#verify-check.checked {
  background: rgba(0, 110, 255, 0.55);
  border-color: rgba(10, 132, 255, .9);
}
#verify-check.checked::after {
  transform: rotate(-45deg) scale(1);
}

/* ─── Inventory bar ───────────────────────────────────────────────────── */
#inventory-bar {
  position: fixed;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: none;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  z-index: 20;
  pointer-events: auto;
}
.inv-eff-row {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  justify-content: center;
}
.eff-tag {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: rgba(0, 4, 22, 0.90);
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
  border: 1px solid rgba(100, 100, 255, 0.22);
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .4px;
  box-shadow: 0 3px 14px rgba(0,0,0,.55);
  white-space: nowrap;
  animation: kfIn .2s cubic-bezier(.34,1.26,.64,1) both;
}
.eff-tag span { opacity: .7; font-weight: 600; }
.eff-tag b    { font-weight: 800; }
.inv-slots-row {
  display: flex;
  gap: 7px;
}
.inv-slot {
  width: 58px;
  height: 64px;
  background: rgba(0, 6, 26, 0.88);
  backdrop-filter: blur(22px) saturate(160%);
  -webkit-backdrop-filter: blur(22px) saturate(160%);
  border: 1.5px solid var(--c, rgba(0, 100, 255, 0.3));
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  cursor: pointer;
  box-shadow:
    0 0 0 1px rgba(0,0,0,.3),
    0 5px 20px rgba(0,0,0,.6);
  transition: transform .12s, box-shadow .14s;
}
.inv-slot:hover {
  transform: translateY(-4px);
  box-shadow:
    0 0 18px color-mix(in srgb, var(--c, #0066ff) 55%, transparent),
    0 5px 20px rgba(0,0,0,.6);
}
.inv-slot:active { transform: translateY(0); }
.inv-icon { font-size: 22px; line-height: 1; }
.inv-name {
  font-size: 7px;
  font-weight: 800;
  letter-spacing: .5px;
  color: var(--c, #aaa);
  text-align: center;
  text-transform: uppercase;
}
.inv-key {
  font-size: 8.5px;
  font-weight: 600;
  color: rgba(255,255,255,.3);
  letter-spacing: .3px;
}

/* ─── Mute button ─────────────────────────────────────────────────────── */
#mute-btn {
  position: fixed;
  bottom: 12px; left: 14px;
  width: 36px; height: 36px;
  display: none;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  background: rgba(0, 8, 24, 0.78);
  backdrop-filter: blur(18px) saturate(160%);
  -webkit-backdrop-filter: blur(18px) saturate(160%);
  border: 1px solid rgba(0, 100, 255, 0.22);
  border-radius: 10px;
  color: #ffffff;
  cursor: pointer;
  z-index: 20;
  box-shadow: 0 4px 18px rgba(0,0,0,.55);
  transition: background .15s, border-color .15s, transform .1s;
  padding: 0;
  line-height: 1;
}
#mute-btn:hover {
  background: rgba(0, 60, 180, 0.28);
  border-color: rgba(0, 140, 255, 0.42);
  transform: scale(1.08);
}
#mute-btn:active { transform: scale(0.96); }

/* ─── Ping display ────────────────────────────────────────────────────── */
#ping-display {
  position: fixed;
  bottom: 10px; right: 14px;
  font-size: 10px;
  font-weight: 600;
  color: rgba(0,220,100,.55);
  letter-spacing: .6px;
  pointer-events: none;
  z-index: 20;
  font-family: 'Nunito', ui-rounded, monospace;
  display: none;
}

/* ─── Center overlay (respawn / killed) ───────────────────────────────── */
#center-overlay {
  position: fixed;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  padding: 18px 40px;
  background: rgba(0, 4, 16, 0.94);
  backdrop-filter: blur(28px) saturate(160%);
  -webkit-backdrop-filter: blur(28px) saturate(160%);
  border: 1px solid rgba(0, 100, 255, 0.25);
  border-radius: 18px;
  box-shadow:
    0 0 0 1px rgba(0,100,255,.10),
    0 20px 60px rgba(0,0,0,.8),
    inset 0 1px 0 rgba(255,255,255,.08);
  pointer-events: none;
  display: none;
}
</style>
</head>
<body>

<!-- Human verify -->
<div id="verify">
  <div id="verify-card">
    <h1>Nomad's Game</h1>
    <p>Real-time multiplayer &middot; 2&ndash;8 players<br>Confirm you are human to continue</p>
    <button id="verify-btn">
      <div id="verify-check"></div>
      <span id="verify-label">I&rsquo;m Human &nbsp;&rarr;</span>
    </button>
  </div>
</div>

<!-- Lobby -->
<div id="lobby" style="display:none">
  <h1>Nomad's Game</h1>
  <div class="pulse-ring"><span></span></div>
  <div class="dot-loader"><span></span><span></span><span></span></div>
  <div id="status-msg">Connecting to server...</div>
  <div class="controls-hint">
    WASD &mdash; Move &amp; Aim &nbsp;|&nbsp; Space / LMB &mdash; Shoot<br>
    2&ndash;8 players &middot; Bullets bounce 10&times; &middot; Random map every match
  </div>
</div>

<!-- Game -->
<div id="game-wrap">
  <div id="hud"><!-- filled dynamically by game.js --></div>
  <canvas id="canvas"></canvas>
  <div id="ctrl-hint">WASD Move &amp; Aim &middot; Space / LMB Shoot &middot; Bullets bounce 10&times;</div>
</div>

<!-- Kill feed & overlay -->
<div id="inventory-bar" style="display:none"></div>
<div id="killfeed"></div>
<div id="center-overlay"></div>
<div id="ping-display"></div>
<button id="mute-btn" title="Mute">🔊</button>

<script>
""" + _JS + """
</script>
</body>
</html>
"""

# ─── Constants ────────────────────────────────────────────────────────────────
TICK_RATE      = 60
PLAYER_SPEED   = 360
BULLET_SPEED   = 550
BULLET_R       = 5
BULLET_DAMAGE  = 18
FIRE_COOLDOWN  = 0.25
PLAYER_MAX_HP  = 100
PLAYER_LIVES   = 4       # lives per player per match
RESPAWN_TIME   = 3.0
MAX_BOUNCES    = 10
MAX_PLAYERS    = 8

# ─── Power-up system ──────────────────────────────────────────────────────────
POWERUP_TYPES  = ['wall_pass', 'invisibility', 'speed', 'super_bullet']
BOX_SIZE       = 26      # collision radius of reward box
BOX_LIFETIME   = 30.0    # seconds until box despawns
BOX_INTERVAL   = 300.0   # seconds between box spawns after trigger (5 min)
SPEED_MULT     = 1.85    # player speed multiplier during speed boost
WALL_PASS_DUR  = 60.0    # wall-pass duration (seconds)
INVIS_DUR      = 30.0    # invisibility duration (seconds)
SPEED_DUR      = 30.0    # speed boost duration (seconds)

# ─── Collapse zones ───────────────────────────────────────────────────────────
ZONE_WARNING    = 3.0     # red flash warning duration (seconds)
ZONE_START_DELAY = 15.0   # seconds after match start before first zone
ZONE_MIN_INT    = 10.0    # min seconds between zones
ZONE_MAX_INT    = 22.0    # max seconds between zones
ZONE_MIN_W, ZONE_MAX_W = 90,  220
ZONE_MIN_H, ZONE_MAX_H = 70,  160

# Green scan line
SCAN_INTERVAL    = 50.0   # seconds between scans
SCAN_DURATION    = 5.0    # seconds for line to cross viewport
SCAN_FIRST_DELAY = 30.0   # seconds after match start before first scan
SCAN_TOL         = 80     # pixels tolerance around line for player detection

# Infinite-world chunk system
CHUNK_W          = 1280   # pixels per chunk (= viewport width)
CHUNK_H          = 720    # pixels per chunk (= viewport height)
VIEWPORT_W       = 1280
VIEWPORT_H       = 720
CHUNK_LOAD_DIST  = 260    # px from chunk edge → generate neighbour
OOB_MARGIN       = 170    # px outside viewport → all respawn

PLAYER_COLORS = [
    "#4fc3f7","#ff9800","#66bb6a","#ffa726",
    "#ab47bc","#26c6da","#ff7043","#ec407a",
]
PLAYER_NAMES = [f"Player {i+1}" for i in range(MAX_PLAYERS)]

# ─── Scaling ──────────────────────────────────────────────────────────────────
def room_params(n: int):
    n = max(2, min(n, MAX_PLAYERS))
    r = max(13, 20 - (n - 2) * 2)
    return int(r)          # only player_r matters; viewport is fixed

def get_spawn_points(n: int, w: int, h: int) -> list:
    margin = 90
    cx, cy = w / 2, h / 2
    rx, ry = w / 2 - margin, h / 2 - margin
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x = int(cx + rx * math.cos(a))
        y = int(cy + ry * math.sin(a))
        face = math.atan2(cy - y, cx - x)
        pts.append({"x": x, "y": y, "angle": face})
    return pts

# ─── Helpers ──────────────────────────────────────────────────────────────────
def circle_rect(cx, cy, cr, rx, ry, rw, rh) -> bool:
    nx = max(rx, min(cx, rx + rw))
    ny = max(ry, min(cy, ry + rh))
    dx, dy = cx - nx, cy - ny
    return dx*dx + dy*dy < cr*cr

def circle_circle(x1, y1, r1, x2, y2, r2) -> bool:
    dx, dy = x1 - x2, y1 - y2
    return dx*dx + dy*dy < (r1+r2)**2

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ─── Chunk terrain generation ─────────────────────────────────────────────────
_MAP_CELL = 16

def _gen_chunk_obs(wx: int, wy: int) -> dict:
    """One random obstacle in world-space within chunk at (wx, wy)."""
    edge = 10
    cw, ch = CHUNK_W, CHUNK_H
    kind = random.randint(0, 5)
    if kind == 0:   # small block
        w, h = random.randint(26, 72), random.randint(26, 72)
        x = random.randint(wx+edge, wx+cw-w-edge)
        y = random.randint(wy+edge, wy+ch-h-edge)
    elif kind == 1: # long horizontal wall
        w = random.randint(95, min(270, cw//4))
        h = random.randint(16, 38)
        x = random.randint(wx+edge, wx+cw-w-edge)
        y = random.randint(wy+edge, wy+ch-h-edge)
    elif kind == 2: # long vertical wall
        w = random.randint(16, 38)
        h = random.randint(95, min(230, ch//3))
        x = random.randint(wx+edge, wx+cw-w-edge)
        y = random.randint(wy+edge, wy+ch-h-edge)
    elif kind == 3: # medium block
        w, h = random.randint(60, 130), random.randint(48, 95)
        x = random.randint(wx+edge, wx+cw-w-edge)
        y = random.randint(wy+edge, wy+ch-h-edge)
    elif kind == 4: # top/bottom edge ledge
        w = random.randint(75, min(240, cw//3))
        h = random.randint(22, 55)
        x = random.randint(wx+edge, wx+cw-w-edge)
        y = wy if random.random() < .5 else wy+ch-h
    else:           # left/right edge ledge
        w = random.randint(22, 55)
        h = random.randint(75, min(185, ch//3))
        x = wx if random.random() < .5 else wx+cw-w
        y = random.randint(wy+edge, wy+ch-h-edge)
    return {"x": x, "y": y, "w": w, "h": h}


def _chunk_connected(obstacles: list, wx: int, wy: int, player_r: int) -> bool:
    """BFS: verify the 4 edge mid-points of the chunk are mutually reachable."""
    cell   = _MAP_CELL
    gw, gh = CHUNK_W // cell, CHUNK_H // cell
    margin = player_r + 4

    g = [[False]*gh for _ in range(gw)]
    for gx in range(gw):
        for gy in range(gh):
            wcx = wx + gx*cell + cell//2
            wcy = wy + gy*cell + cell//2
            if (wcx < wx+margin or wcx > wx+CHUNK_W-margin or
                    wcy < wy+margin or wcy > wy+CHUNK_H-margin):
                g[gx][gy] = True
                continue
            for obs in obstacles:
                if (wcx-margin < obs["x"]+obs["w"] and wcx+margin > obs["x"] and
                        wcy-margin < obs["y"]+obs["h"] and wcy+margin > obs["y"]):
                    g[gx][gy] = True
                    break

    # Entry points must be INSIDE the margin zone (not at raw edge rows/cols).
    # margin=24px / cell=16px → first safe grid index is 2 (center=wy+40 > wy+24).
    entries = [(gw//2, 2), (gw//2, gh-3), (2, gh//2), (gw-3, gh//2)]
    valid   = [(ex, ey) for ex, ey in entries if not g[ex][ey]]
    if len(valid) < 2:
        return False

    start, targets = valid[0], set(valid[1:])
    visited = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        targets.discard((x, y))
        if not targets:
            return True
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if dx == dy == 0: continue
                nx, ny = x+dx, y+dy
                if 0<=nx<gw and 0<=ny<gh and (nx,ny) not in visited and not g[nx][ny]:
                    visited.add((nx,ny)); q.append((nx,ny))
    return False


def _fallback_chunk(wx: int, wy: int) -> list:
    """Pre-built dense maze guaranteed to be traversable, offset to chunk origin."""
    templates = [
        # horizontal walls
        (0.12, 0.10, 0.18, 0.05), (0.38, 0.10, 0.24, 0.05), (0.65, 0.08, 0.22, 0.05),
        (0.05, 0.28, 0.20, 0.05), (0.32, 0.26, 0.16, 0.05), (0.55, 0.27, 0.20, 0.05),
        (0.78, 0.25, 0.17, 0.05), (0.10, 0.45, 0.22, 0.05), (0.38, 0.44, 0.24, 0.05),
        (0.68, 0.45, 0.20, 0.05), (0.12, 0.62, 0.20, 0.05), (0.40, 0.63, 0.20, 0.05),
        (0.67, 0.62, 0.21, 0.05), (0.05, 0.80, 0.18, 0.05), (0.35, 0.79, 0.30, 0.05),
        (0.72, 0.80, 0.22, 0.05),
        # vertical walls
        (0.28, 0.05, 0.04, 0.18), (0.50, 0.08, 0.04, 0.16), (0.72, 0.05, 0.04, 0.20),
        (0.18, 0.33, 0.04, 0.15), (0.44, 0.32, 0.04, 0.14), (0.62, 0.31, 0.04, 0.16),
        (0.85, 0.30, 0.04, 0.18), (0.28, 0.50, 0.04, 0.16), (0.52, 0.50, 0.04, 0.14),
        (0.74, 0.50, 0.04, 0.18), (0.20, 0.68, 0.04, 0.15), (0.46, 0.68, 0.04, 0.16),
    ]
    return [{"x": int(wx + fx*CHUNK_W), "y": int(wy + fy*CHUNK_H),
             "w": max(20, int(fw*CHUNK_W)), "h": max(16, int(fh*CHUNK_H))}
            for fx, fy, fw, fh in templates]


def gen_chunk(wx: int, wy: int, player_r: int) -> list:
    """Incremental generation: add obstacles one-by-one keeping chunk connected.
    Falls back to a pre-built maze if fewer than 8 obstacles are produced."""
    target = random.randint(22, 30)
    obs_list, misses = [], 0
    while len(obs_list) < target and misses < 900:
        obs = _gen_chunk_obs(wx, wy)
        if _chunk_connected(obs_list + [obs], wx, wy, player_r):
            obs_list.append(obs)
        else:
            misses += 1
    return obs_list if len(obs_list) >= 8 else _fallback_chunk(wx, wy)


# ─── Bullet bounce helper ─────────────────────────────────────────────────────
def _bounce_bullet_obs(b, obs) -> bool:
    rx, ry, rw, rh = obs["x"], obs["y"], obs["w"], obs["h"]
    if not circle_rect(b.x, b.y, BULLET_R, rx, ry, rw, rh):
        return False
    ov_l = (b.x+BULLET_R)-rx;  ov_r = (rx+rw)-(b.x-BULLET_R)
    ov_t = (b.y+BULLET_R)-ry;  ov_b = (ry+rh)-(b.y-BULLET_R)
    m = min(ov_l, ov_r, ov_t, ov_b)
    if   m==ov_l: b.vx=-abs(b.vx); b.x=rx-BULLET_R
    elif m==ov_r: b.vx= abs(b.vx); b.x=rx+rw+BULLET_R
    elif m==ov_t: b.vy=-abs(b.vy); b.y=ry-BULLET_R
    else:         b.vy= abs(b.vy); b.y=ry+rh+BULLET_R
    return True

# ─── Entities ─────────────────────────────────────────────────────────────────
class Bullet:
    __slots__ = ("id","owner_id","x","y","vx","vy","color","bounces","life","is_super")
    def __init__(self, owner_id, x, y, angle, color, is_super=False):
        self.id       = str(uuid.uuid4())[:8]
        self.owner_id = owner_id
        self.x, self.y = x, y
        self.vx = math.cos(angle) * BULLET_SPEED
        self.vy = math.sin(angle) * BULLET_SPEED
        self.color    = color
        self.bounces  = 0
        self.is_super = is_super
        self.life     = 15.0 if is_super else 12.0
    def to_dict(self):
        return {"id":self.id,"x":self.x,"y":self.y,
                "color":self.color,"bounces":self.bounces,"is_super":self.is_super}


class RewardBox:
    __slots__ = ('id', 'x', 'y', 'ptype', 'life')
    def __init__(self, x, y, ptype):
        self.id    = str(uuid.uuid4())[:8]
        self.x     = float(x)
        self.y     = float(y)
        self.ptype = ptype
        self.life  = BOX_LIFETIME
    def to_dict(self):
        return {'id': self.id, 'x': self.x, 'y': self.y,
                'type': self.ptype, 'life': round(self.life, 2)}

class CollapseZone:
    __slots__ = ('id', 'x', 'y', 'w', 'h', 'timer')
    def __init__(self, x, y, w, h):
        self.id    = str(uuid.uuid4())[:8]
        self.x, self.y = float(x), float(y)
        self.w, self.h = float(w), float(h)
        self.timer = ZONE_WARNING   # counts down to 0 → collapse
    def to_dict(self):
        return {'id': self.id, 'x': self.x, 'y': self.y,
                'w': self.w, 'h': self.h, 'timer': round(self.timer, 2)}


class Player:
    def __init__(self, pid, slot, spawn, player_r):
        self.id       = pid
        self.slot     = slot
        self.color    = PLAYER_COLORS[slot % len(PLAYER_COLORS)]
        self.name     = PLAYER_NAMES[slot % len(PLAYER_NAMES)]
        self.spawn    = spawn
        self.player_r = player_r
        self.x, self.y = float(spawn["x"]), float(spawn["y"])
        self.angle    = spawn.get("angle", 0.0)
        self.hp       = PLAYER_MAX_HP
        self.lives    = PLAYER_LIVES
        self.score    = 0
        self.alive    = True
        self.respawn_timer = 0.0
        self.fire_timer    = 0.0
        self.inp_up = self.inp_down = self.inp_left = self.inp_right = False
        self.inp_shoot  = False
        self._has_input = False   # True once any input received
        self.ping_ms    = 0.0
        self._pos_hist  = deque(maxlen=128)  # (time, x, y) lag-comp history
        # Power-up state
        self.inventory: List[str]   = []   # queued power-ups (max 4)
        self.effects:   Dict[str, float] = {}  # {ptype: remaining_secs}
        self.super_aiming = False
        self.aim_angle    = 0.0

    def respawn(self):
        self.x, self.y = float(self.spawn["x"]), float(self.spawn["y"])
        self.hp = PLAYER_MAX_HP; self.alive = True; self.respawn_timer = 0.0

    def to_dict(self):
        return {
            "id":self.id,"slot":self.slot,"name":self.name,"color":self.color,
            "x":self.x,"y":self.y,"angle":self.angle,
            "hp":self.hp,"maxHp":PLAYER_MAX_HP,"score":self.score,
            "lives":self.lives,"maxLives":PLAYER_LIVES,
            "alive":self.alive,"respawnMs":int(self.respawn_timer*1000),
            "r":self.player_r,
            "inventory":  list(self.inventory),
            "effects":    {k: round(v, 2) for k, v in self.effects.items()},
            "super_aiming": self.super_aiming,
            "invisible":  'invisibility' in self.effects,
        }

# ─── Game Room ────────────────────────────────────────────────────────────────
class Room:
    def __init__(self, rid: str):
        self.id          = rid
        self.players:  Dict[str, Player]    = {}
        self.sockets:  Dict[str, WebSocket] = {}
        self.bullets:  List[Bullet]         = []
        self.running      = False
        self._loop_task   = None
        self._initialized = False
        self._next_slot   = 0
        # Match state
        self._match_over  = False
        self._winner_id   = None
        self._game_over   = False   # set after game_over broadcast
        # Infinite world
        self.chunks: Dict[tuple, list] = {}
        self._new_obs: List[dict]      = []   # queued to send in next state
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.player_r = 20
        self.spawns: List[dict] = []
        # Power-up boxes
        self.boxes: List[RewardBox] = []
        self._box_triggered = False
        self._next_box_at   = 0.0   # monotonic time for next spawn
        # Collapse zones
        self.zones: List[CollapseZone] = []
        self._next_zone_at  = 0.0   # set in _initialize_map
        # Green scan line
        self._scan_active   = False
        self._scan_frac     = 0.0   # 0→1 across viewport
        self._scan_elapsed  = 0.0
        self._scanned_pids: set = set()
        self._next_scan_at  = 0.0   # set in _initialize_map

    # ── Chunk management ──────────────────────────────────────────────────────
    @property
    def _all_obs(self):
        return [o for chunk in self.chunks.values() for o in chunk]

    def _load_chunk(self, cx: int, cy: int):
        if (cx, cy) in self.chunks:
            return
        wx, wy = cx * CHUNK_W, cy * CHUNK_H
        new = gen_chunk(wx, wy, self.player_r)
        self.chunks[(cx, cy)] = new
        self._new_obs.extend(new)

    def _check_chunks(self):
        """Load adjacent chunks when any player approaches a chunk boundary."""
        for p in self.players.values():
            if not p.alive:
                continue
            cx = int(math.floor(p.x / CHUNK_W))
            cy = int(math.floor(p.y / CHUNK_H))
            lx = p.x - cx * CHUNK_W
            ly = p.y - cy * CHUNK_H
            to_gen = {(cx, cy)}
            if lx < CHUNK_LOAD_DIST:             to_gen.add((cx-1, cy))
            if lx > CHUNK_W - CHUNK_LOAD_DIST:   to_gen.add((cx+1, cy))
            if ly < CHUNK_LOAD_DIST:             to_gen.add((cx, cy-1))
            if ly > CHUNK_H - CHUNK_LOAD_DIST:   to_gen.add((cx, cy+1))
            for ncx, ncy in to_gen:
                self._load_chunk(ncx, ncy)

    # ── Camera ────────────────────────────────────────────────────────────────
    def _update_camera(self):
        alive = [p for p in self.players.values() if p.alive] or \
                list(self.players.values())
        if not alive:
            return
        avg_x = sum(p.x for p in alive) / len(alive)
        avg_y = sum(p.y for p in alive) / len(alive)
        self.cam_x = avg_x - VIEWPORT_W / 2
        self.cam_y = avg_y - VIEWPORT_H / 2

    # ── Out-of-bounds respawn ─────────────────────────────────────────────────
    def _check_oob(self):
        for p in self.players.values():
            if not p.alive:
                continue
            if (p.x < self.cam_x - OOB_MARGIN or
                    p.x > self.cam_x + VIEWPORT_W + OOB_MARGIN or
                    p.y < self.cam_y - OOB_MARGIN or
                    p.y > self.cam_y + VIEWPORT_H + OOB_MARGIN):
                self._respawn_all_in_viewport()
                return

    def _respawn_all_in_viewport(self):
        all_obs = self._all_obs
        pr      = self.player_r
        margin  = pr + 70
        for p in self.players.values():
            placed = False
            for _ in range(150):
                rx = self.cam_x + random.uniform(margin, VIEWPORT_W - margin)
                ry = self.cam_y + random.uniform(margin, VIEWPORT_H - margin)
                if all(not circle_rect(rx, ry, pr*2,
                        o["x"], o["y"], o["w"], o["h"]) for o in all_obs):
                    p.x, p.y = rx, ry
                    p.hp = PLAYER_MAX_HP; p.alive = True; p.respawn_timer = 0.0
                    placed = True; break
            if not placed:
                p.x = self.cam_x + VIEWPORT_W / 2
                p.y = self.cam_y + VIEWPORT_H / 2
                p.hp = PLAYER_MAX_HP; p.alive = True; p.respawn_timer = 0.0

    # ── Lag compensation ──────────────────────────────────────────────────────
    @staticmethod
    def _rewind_pos(player, lag_secs: float):
        """Return (x, y) of player at approximately lag_secs in the past."""
        if lag_secs < 0.010 or not player._pos_hist:
            return player.x, player.y
        target_t = time.monotonic() - lag_secs
        for t, x, y in reversed(player._pos_hist):
            if t <= target_t:
                return x, y
        return player.x, player.y

    # ── Power-up box management ───────────────────────────────────────────────
    def _spawn_box(self):
        """Spawn one random power-up box at a reachable position in the viewport."""
        all_obs  = self._all_obs
        margin   = self.player_r + BOX_SIZE + 50
        ptype    = random.choice(POWERUP_TYPES)
        for _ in range(200):
            rx = self.cam_x + random.uniform(margin, VIEWPORT_W - margin)
            ry = self.cam_y + random.uniform(margin, VIEWPORT_H - margin)
            if all(not circle_rect(rx, ry, BOX_SIZE + self.player_r,
                                   o["x"], o["y"], o["w"], o["h"]) for o in all_obs):
                self.boxes.append(RewardBox(rx, ry, ptype))
                return
        # fallback: centre of viewport
        self.boxes.append(RewardBox(
            self.cam_x + VIEWPORT_W / 2, self.cam_y + VIEWPORT_H / 2, ptype))

    def _spawn_zone(self, now: float):
        """Spawn a random collapse zone within the current viewport."""
        w = random.uniform(ZONE_MIN_W, ZONE_MAX_W)
        h = random.uniform(ZONE_MIN_H, ZONE_MAX_H)
        margin = 60
        x = self.cam_x + random.uniform(margin, VIEWPORT_W - w - margin)
        y = self.cam_y + random.uniform(margin, VIEWPORT_H - h - margin)
        self.zones.append(CollapseZone(x, y, w, h))
        self._next_zone_at = now + random.uniform(ZONE_MIN_INT, ZONE_MAX_INT)

    def use_powerup(self, pid: str, slot: int):
        """Activate a power-up from a player's inventory."""
        p = self.players.get(pid)
        if not p or slot < 0 or slot >= len(p.inventory):
            return
        ptype = p.inventory.pop(slot)
        if ptype == 'super_bullet':
            p.super_aiming = True
        elif ptype == 'wall_pass':
            p.effects['wall_pass']    = WALL_PASS_DUR
        elif ptype == 'invisibility':
            p.effects['invisibility'] = INVIS_DUR
        elif ptype == 'speed':
            p.effects['speed']        = SPEED_DUR

    # ── Map init (called when 2nd player joins) ───────────────────────────────
    def _initialize_map(self):
        n = len(self.players)
        self.player_r = room_params(n)
        # Generate origin chunk
        self._load_chunk(0, 0)
        # Spawn points in origin chunk world-coords
        self.spawns = get_spawn_points(MAX_PLAYERS, CHUNK_W, CHUNK_H)
        for p in self.players.values():
            sp = self.spawns[p.slot]
            p.spawn = sp; p.player_r = self.player_r
            p.x, p.y = float(sp["x"]), float(sp["y"])
            p.angle  = sp.get("angle", 0.0)
        self._update_camera()
        self._next_zone_at = time.monotonic() + ZONE_START_DELAY
        self._next_scan_at = time.monotonic() + SCAN_FIRST_DELAY
        self._initialized = True

    # ── Player management ─────────────────────────────────────────────────────
    def add_player(self, ws: WebSocket, pid: str) -> dict:
        if len(self.players) >= MAX_PLAYERS:
            return {"status": "full"}
        slot  = self._next_slot; self._next_slot += 1
        sp    = self.spawns[slot] if self.spawns and slot < len(self.spawns) \
                else {"x": CHUNK_W//2, "y": CHUNK_H//2, "angle": 0.0}
        self.players[pid] = Player(pid, slot, sp, self.player_r)
        self.sockets[pid] = ws
        newly_init = False
        if not self._initialized and len(self.players) >= 2:
            self._initialize_map(); newly_init = True
        return {"status": "ok", "newly_init": newly_init}

    def remove_player(self, pid: str):
        self.players.pop(pid, None); self.sockets.pop(pid, None)

    def apply_input(self, pid: str, data: dict):
        p = self.players.get(pid)
        if not p: return
        p._has_input = True
        p.ping_ms   = float(data.get("ping", 0))
        p.inp_up    = bool(data.get("up"))
        p.inp_down  = bool(data.get("down"))
        p.inp_left  = bool(data.get("left"))
        p.inp_right = bool(data.get("right"))
        p.inp_shoot = bool(data.get("shoot"))
        if data.get("aim_angle") is not None:
            p.aim_angle = float(data["aim_angle"])

    def init_data(self, pid: str) -> dict:
        return {
            "type": "init", "myId": pid,
            "mySlot": self.players[pid].slot,
            "gameW": VIEWPORT_W, "gameH": VIEWPORT_H,
            "playerR": self.player_r,
            "obstacles": self._all_obs,
            "spawnPoints": self.spawns,
            "playerCount": len(self.players),
            "camX": self.cam_x, "camY": self.cam_y,
        }

    # ── Physics tick ──────────────────────────────────────────────────────────
    def update(self, dt: float):
        player_list = list(self.players.values())
        pr  = self.player_r
        obs = self._all_obs  # snapshot for this tick
        _now = time.monotonic()

        # ── Power-up box: trigger & spawn ─────────────────────────────────────
        if not self._box_triggered and not self._match_over:
            for p in player_list:
                if p.alive and p.hp <= PLAYER_MAX_HP * 0.5:
                    self._box_triggered = True
                    self._next_box_at   = _now
                    break
        if self._box_triggered and not self._match_over and _now >= self._next_box_at:
            self._spawn_box()
            self._next_box_at = _now + BOX_INTERVAL

        # ── Players ───────────────────────────────────────────────────────────
        for p in player_list:
            # Tick active effects
            expired = [k for k, v in p.effects.items() if v - dt <= 0]
            for k in expired: del p.effects[k]
            for k in list(p.effects): p.effects[k] -= dt

            if not p.alive:
                if p.lives > 0:
                    p.respawn_timer -= dt
                    if p.respawn_timer <= 0:
                        p.respawn()
                continue

            # Super-aiming: freeze movement, fire super bullet on shoot
            if p.super_aiming:
                p.fire_timer = max(0.0, p.fire_timer - dt)
                if p.inp_shoot and p.fire_timer == 0:
                    p.fire_timer  = FIRE_COOLDOWN
                    p.super_aiming = False
                    bx = p.x + math.cos(p.aim_angle) * (pr + BULLET_R + 3)
                    by = p.y + math.sin(p.aim_angle) * (pr + BULLET_R + 3)
                    self.bullets.append(
                        Bullet(p.id, bx, by, p.aim_angle, '#ff2060', is_super=True))
                continue  # skip normal movement while aiming

            spd = PLAYER_SPEED * (SPEED_MULT if 'speed' in p.effects else 1.0)
            vx = vy = 0.0
            if p.inp_up:    vy -= spd
            if p.inp_down:  vy += spd
            if p.inp_left:  vx -= spd
            if p.inp_right: vx += spd
            if vx and vy:
                vx *= 0.7071; vy *= 0.7071

            p.x += vx * dt; p.y += vy * dt
            if vx or vy:
                p.angle = math.atan2(vy, vx)

            # Obstacle push-out (skipped when wall_pass active)
            if 'wall_pass' not in p.effects:
                for o in obs:
                    if circle_rect(p.x, p.y, pr, o["x"], o["y"], o["w"], o["h"]):
                        nx = clamp(p.x, o["x"], o["x"]+o["w"])
                        ny = clamp(p.y, o["y"], o["y"]+o["h"])
                        dx, dy = p.x-nx, p.y-ny
                        d = math.sqrt(dx*dx+dy*dy) or 0.001
                        p.x = nx + (dx/d)*pr; p.y = ny + (dy/d)*pr

            p.fire_timer = max(0.0, p.fire_timer - dt)
            if p.inp_shoot and p.fire_timer == 0:
                p.fire_timer = FIRE_COOLDOWN
                bx = p.x + math.cos(p.angle)*(pr+BULLET_R+3)
                by = p.y + math.sin(p.angle)*(pr+BULLET_R+3)
                self.bullets.append(Bullet(p.id, bx, by, p.angle, p.color))

        # ── Speed contact kill ─────────────────────────────────────────────────
        for p in player_list:
            if not p.alive or 'speed' not in p.effects: continue
            for enemy in player_list:
                if enemy.id == p.id or not enemy.alive: continue
                if circle_circle(p.x, p.y, pr, enemy.x, enemy.y, pr):
                    enemy.hp = 0; enemy.alive = False; enemy.super_aiming = False
                    enemy.lives -= 1
                    enemy.respawn_timer = RESPAWN_TIME if enemy.lives > 0 else 9999.0
                    p.score += 1
                    if not self._match_over:
                        survivors = [x for x in self.players.values() if x.lives > 0]
                        if len(survivors) <= 1:
                            self._match_over = True
                            self._winner_id  = survivors[0].id if survivors else p.id

        # Record positions for lag compensation
        _t_now = time.monotonic()
        for p in player_list:
            if p.alive:
                p._pos_hist.append((_t_now, p.x, p.y))

        # ── Box collection ─────────────────────────────────────────────────────
        kept = []
        for box in self.boxes:
            box.life -= dt
            if box.life <= 0: continue
            taken = False
            for p in player_list:
                if not p.alive or len(p.inventory) >= 4: continue
                if circle_circle(p.x, p.y, pr, box.x, box.y, BOX_SIZE):
                    p.inventory.append(box.ptype); taken = True; break
            if not taken: kept.append(box)
        self.boxes = kept

        # ── Collapse zones ─────────────────────────────────────────────────────
        if not self._match_over and _now >= self._next_zone_at:
            self._spawn_zone(_now)

        alive_zones = []
        for zone in self.zones:
            zone.timer -= dt
            if zone.timer <= 0:
                # Collapse: players inside lose a life
                for p in player_list:
                    if not p.alive: continue
                    if (zone.x <= p.x <= zone.x + zone.w and
                            zone.y <= p.y <= zone.y + zone.h):
                        p.hp = 0; p.alive = False; p.super_aiming = False
                        p.lives -= 1
                        p.respawn_timer = RESPAWN_TIME if p.lives > 0 else 9999.0
                        if not self._match_over:
                            survivors = [x for x in self.players.values() if x.lives > 0]
                            if len(survivors) <= 1:
                                self._match_over = True
                                self._winner_id  = survivors[0].id if survivors else None
                # zone removed (not appended)
            else:
                alive_zones.append(zone)
        self.zones = alive_zones

        # ── Green scan line ────────────────────────────────────────────────────
        if not self._match_over:
            if not self._scan_active and _now >= self._next_scan_at:
                self._scan_active  = True
                self._scan_elapsed = 0.0
                self._scan_frac    = 0.0
                self._scanned_pids = set()

            if self._scan_active:
                self._scan_elapsed += dt
                self._scan_frac = min(self._scan_elapsed / SCAN_DURATION, 1.0)
                scan_world_x = self.cam_x + self._scan_frac * VIEWPORT_W

                for p in player_list:
                    if not p.alive: continue
                    if p.id in self._scanned_pids: continue
                    if abs(p.x - scan_world_x) < SCAN_TOL:
                        self._scanned_pids.add(p.id)
                        moving  = p.inp_up or p.inp_down or p.inp_left or p.inp_right
                        shooting_now = p.inp_shoot
                        if moving or shooting_now:
                            p.hp = 0; p.alive = False; p.super_aiming = False
                            p.lives -= 1
                            p.respawn_timer = RESPAWN_TIME if p.lives > 0 else 9999.0
                            if not self._match_over:
                                survivors = [x for x in self.players.values() if x.lives > 0]
                                if len(survivors) <= 1:
                                    self._match_over = True
                                    self._winner_id  = survivors[0].id if survivors else None

                if self._scan_frac >= 1.0:
                    self._scan_active  = False
                    self._scan_frac    = 0.0
                    self._next_scan_at = _now + SCAN_INTERVAL

        # ── Bullets ───────────────────────────────────────────────────────────
        vl = self.cam_x;          vr = self.cam_x + VIEWPORT_W
        vt = self.cam_y;          vb = self.cam_y + VIEWPORT_H

        alive_b = []
        for b in self.bullets:
            b.x += b.vx*dt; b.y += b.vy*dt; b.life -= dt
            if b.life <= 0: continue

            if not b.is_super:
                # Normal bullet: viewport bounce + obstacle bounce
                if b.x < vl+BULLET_R:   b.x=vl+BULLET_R;  b.vx= abs(b.vx); b.bounces+=1
                elif b.x > vr-BULLET_R: b.x=vr-BULLET_R;  b.vx=-abs(b.vx); b.bounces+=1
                if b.y < vt+BULLET_R:   b.y=vt+BULLET_R;  b.vy= abs(b.vy); b.bounces+=1
                elif b.y > vb-BULLET_R: b.y=vb-BULLET_R;  b.vy=-abs(b.vy); b.bounces+=1
                if b.bounces > MAX_BOUNCES: continue
                dead = False
                for o in obs:
                    if _bounce_bullet_obs(b, o):
                        b.bounces += 1
                        if b.bounces > MAX_BOUNCES: dead = True
                        break
                if dead: continue
            else:
                # Super bullet: passes through everything, despawn if off-screen
                if (b.x < vl-600 or b.x > vr+600 or
                        b.y < vt-600 or b.y > vb+600):
                    continue

            # Player hit (lag-compensated; bounced bullets can hit own shooter)
            hit = False
            for p in player_list:
                if not p.alive: continue
                if p.id == b.owner_id and b.bounces == 0 and not b.is_super: continue
                sh  = self.players.get(b.owner_id)
                lag = min((sh.ping_ms / 2000.0) if sh else 0.0, 0.15)
                hx, hy = Room._rewind_pos(p, lag)
                if circle_circle(b.x, b.y, BULLET_R, hx, hy, pr):
                    p.hp = 0 if b.is_super else max(0, p.hp - BULLET_DAMAGE)
                    if p.hp <= 0:
                        p.hp = 0; p.alive = False; p.super_aiming = False
                        p.lives -= 1
                        p.respawn_timer = RESPAWN_TIME if p.lives > 0 else 9999.0
                        s = self.players.get(b.owner_id)
                        if s: s.score += 1
                        if not self._match_over:
                            survivors = [x for x in self.players.values() if x.lives > 0]
                            if len(survivors) <= 1:
                                self._match_over = True
                                self._winner_id  = survivors[0].id if survivors \
                                                   else (s.id if s else b.owner_id)
                    hit = True; break
            if not hit:
                alive_b.append(b)

        self.bullets = alive_b

        # ── Post-tick world management ─────────────────────────────────────────
        self._update_camera()
        self._check_chunks()
        self._check_oob()

    def get_state(self) -> dict:
        state = {
            "type":    "state",
            "players": [p.to_dict() for p in self.players.values()],
            "bullets": [b.to_dict() for b in self.bullets],
            "boxes":   [b.to_dict() for b in self.boxes],
            "zones":   [z.to_dict() for z in self.zones],
            "scan":    {
                "active":  self._scan_active,
                "frac":    round(self._scan_frac, 4),
                "next_in": round(max(0.0, self._next_scan_at - time.monotonic()), 1),
            },
            "camX":    self.cam_x,
            "camY":    self.cam_y,
        }
        if self._new_obs:
            state["newObs"] = self._new_obs
            self._new_obs = []
        return state

    # ── Game loop ─────────────────────────────────────────────────────────────
    async def _broadcast(self, msg: str):
        dead = []
        for pid, ws in list(self.sockets.items()):
            try: await ws.send_text(msg)
            except: dead.append(pid)
        for pid in dead: self.remove_player(pid)

    async def run_loop(self):
        self.running = True
        dt = 1.0 / TICK_RATE
        while self.running and self.sockets:
            t0 = time.monotonic()
            self.update(dt)
            await self._broadcast(json.dumps(self.get_state()))

            if self._match_over:
                await asyncio.sleep(0.8)   # let clients see the kill frame
                winner = self.players.get(self._winner_id)
                await self._broadcast(json.dumps({
                    "type":        "game_over",
                    "winnerName":  winner.name  if winner else "Player",
                    "winnerColor": winner.color if winner else "#ffffff",
                }))
                self._game_over = True
                break

            s = dt - (time.monotonic() - t0)
            if s > 0: await asyncio.sleep(s)
        self.running = False

    def start(self):
        if not self.running:
            self._loop_task = asyncio.create_task(self.run_loop())

    def stop(self):
        self.running = False
        if self._loop_task: self._loop_task.cancel()


# ─── Matchmaking ──────────────────────────────────────────────────────────────
class Matchmaker:
    def __init__(self):
        self._room: Optional[Room] = None
        self._lock = asyncio.Lock()

    def _active_room(self) -> Room:
        if (self._room is None
                or (not self._room.running and len(self._room.players) == 0)
                or self._room._game_over):
            self._room = Room(str(uuid.uuid4())[:8])
        return self._room

    async def join(self, ws: WebSocket, pid: str):
        async with self._lock:
            room = self._active_room()

            # Don't let anyone join a match already in progress
            if room._initialized and room.running:
                await ws.send_text(json.dumps({
                    "type": "waiting",
                    "msg":  "A match is in progress. Please wait...",
                    "playerCount": 0,
                }))
                return

            result = room.add_player(ws, pid)

            if result["status"] == "full":
                await ws.send_text(json.dumps(
                    {"type":"full","msg":"Server full (max 8 players)."}))
                return

            if result["newly_init"]:
                for pid_x, ws_x in list(room.sockets.items()):
                    try: await ws_x.send_text(json.dumps(room.init_data(pid_x)))
                    except: pass
                room.start()
            elif room._initialized:
                await ws.send_text(json.dumps(room.init_data(pid)))
            else:
                await ws.send_text(json.dumps({
                    "type":"waiting","msg":"Waiting for opponent...",
                    "playerCount": len(room.players),
                }))

    async def leave(self, pid: str):
        async with self._lock:
            room = self._room
            if not room or pid not in room.players: return
            room.remove_player(pid)
            n = len(room.players)
            if n == 0:
                room.stop(); self._room = None
            else:
                msg = json.dumps({"type":"player_left",
                                  "msg":"A player disconnected.","playerCount":n})
                for ws_x in list(room.sockets.values()):
                    try: await ws_x.send_text(msg)
                    except: pass

    def get_room(self, pid: str) -> Optional[Room]:
        if self._room and pid in self._room.players:
            return self._room
        return None


# ─── FastAPI ──────────────────────────────────────────────────────────────────
app        = FastAPI(title="2D ketch-up")
matchmaker = Matchmaker()

@app.get("/")
async def index():
    return HTMLResponse(_HTML)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    pid = str(uuid.uuid4())[:12]
    await ws.send_text(json.dumps({"type":"connected","pid":pid}))
    await matchmaker.join(ws, pid)
    try:
        while True:
            data = json.loads(await ws.receive_text())
            if data.get("type") == "input":
                room = matchmaker.get_room(pid)
                if room: room.apply_input(pid, data)
            elif data.get("type") == "use_powerup":
                room = matchmaker.get_room(pid)
                if room: room.use_powerup(pid, int(data.get("slot", 0)))
            elif data.get("type") == "ping":
                await ws.send_text(json.dumps({"type":"pong","t":data.get("t",0)}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await matchmaker.leave(pid)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
