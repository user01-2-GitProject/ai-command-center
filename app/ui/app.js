"use strict";
/* AI Command Center dashboard UI — isometric sector edition.
 * Fetches /api/sessions and renders the approved ACC-05 first screen as
 * an isometric ops room on canvas. All provider-supplied strings are
 * inserted via textContent (DOM) or fillText (canvas) — never innerHTML —
 * so untrusted telemetry renders inert. */

const $ = (s) => document.querySelector(s);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

const fmtN = (n) => (n === null || n === undefined ? "—" : n.toLocaleString("en-US"));
const relAge = (s) => (s === null || s === undefined ? "—" : s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`);
function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return relAge(s);
}

let payload = null;
let selectedId = null;
let pollTimer = null;
let motionOn = true;

const root = document.documentElement;
const canvas = $("#sector");
const ctx = canvas.getContext("2d");
const emptyState = $("#emptyState");
const demoBanner = $("#demoBanner");
const connError = $("#connError");
const modeBadge = $("#modeBadge");

/* ================= data ================= */
async function refresh() {
  try {
    const res = await fetch("/api/sessions", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    payload = await res.json();
    connError.hidden = true;
    render();
  } catch (e) {
    connError.hidden = false;
  }
  schedule();
}

function schedule() {
  if (pollTimer) clearInterval(pollTimer);
  const secs = (payload && payload.poll_interval_sec) || 15;
  pollTimer = setInterval(refresh, secs * 1000);
}

function allSessions() {
  const out = [];
  if (!payload) return out;
  const provs = [...payload.providers].sort((a, b) => a.provider.localeCompare(b.provider));
  provs.forEach((p) => (p.sessions || []).forEach((s) => out.push(s)));
  return out;
}

function occLabel(s) {
  if (s.percent_used !== null && s.percent_used !== undefined) return s.percent_used + "%";
  return "n/a";
}

/* ================= robot-room viewport ================= */
/* Design frame 680x420, cover-scaled to the viewport. The far wall pins to
   the top of the visible rect and the floor bleeds to every edge, so the
   room always fills the frame like a window — no floating platform. */
const DW = 680, DH = 420, CAMX = 340, CAMY = 250;
const TILE_W = 64, TILE_H = 32;
const OX = 340, OY = 120;
const SPR_SCALE = 4;

/* 12x14 pixel robot. o=outline b=body d=dark f=face e=eye l=light .=none */
const ROBOT = [
  ".....ll.....",
  ".....oo.....",
  "...oooooo...",
  "..oobbbboo..",
  "..obbbbbo...",
  "..obbbbbbo..",
  "..obffffbo..",
  "..obeffebo..",
  "..obbbbbbo..",
  "...obbbbo...",
  "..obbbbbbo..",
  ".obobbbobo..",
  ".obobdbobo..",
  "...obbbbo...",
  "...oo..oo...",
];

function palFor(provider) {
  const base = { o: "#0b0b26", f: "#d7ecff", e: "#40ffff" };
  const P = {
    "Hermes": { b: "#3fc1ff", d: "#1a6fa5", l: "#ffdc78" },
    "Claude Code": { b: "#ff9f43", d: "#b56a1e", l: "#78ffcc" },
    "Codex": { b: "#c99aff", d: "#7a4fc9", l: "#ff9696" },
  };
  return Object.assign(base, P[provider] || { b: "#9aa4c0", d: "#5a6480", l: "#e0e6ff" });
}

function makeRobot(pal) {
  const c = document.createElement("canvas");
  c.width = 12 * SPR_SCALE; c.height = 15 * SPR_SCALE;
  const g = c.getContext("2d");
  g.imageSmoothingEnabled = false;
  ROBOT.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      const col = pal[ch];
      if (!col) return;
      g.fillStyle = col;
      g.fillRect(x * SPR_SCALE, y * SPR_SCALE, SPR_SCALE, SPR_SCALE);
    });
  });
  return c;
}

function dimCanvas(src) {
  const c = document.createElement("canvas");
  c.width = src.width; c.height = src.height;
  const g = c.getContext("2d");
  g.filter = "grayscale(85%) brightness(62%)";
  g.drawImage(src, 0, 0);
  return c;
}

let sprites = {}; /* provider -> {normal, dim} */
function ensureSprites() {
  const provs = new Set(allSessions().map((s) => s.provider));
  provs.forEach((p) => {
    if (!sprites[p]) {
      const normal = makeRobot(palFor(p));
      sprites[p] = { normal, dim: dimCanvas(normal) };
    }
  });
}

/* room-coordinate slots for sessions */
const SLOTS = [[1,2],[7,2],[1,7],[7,7],[4,2],[4,7]]; /* max-spread layout */
let anchors = []; /* {sid, x, y} feet positions for hit-testing */

/* ---------- room surfaces ---------- */
/* The room is painted through a camera view onto any canvas.
   Desktop/tablet: one wide window on the whole room.
   Mobile: one follow-cam window per agent; the camera eases to its robot. */
const room = { el: $("#viewport"), canvas, ctx, w: 0, h: 0, v: null };

/* iggy: the operator. 16-bit isometric sprite, walks the room.
   carpet monsters can't fly. */
const iggyIso = new Image();
iggyIso.src = "/ui/assets/iggy-iso.png";
function iggyPos(t) {
  const hx = 4.5, hy = 4.5; /* home: middle of the room */
  let wx = 0, wy = 0;
  if (motionOn) {
    wx = Math.sin(t * 0.27 + 2.1) * 60;
    wy = Math.sin(t * 0.19 + 0.6) * 26;
  }
  const [cx, cy] = iso(hx, hy);
  return { x: cx + wx, y: cy + wy };
}

/* camera: frame (fx, fy) in a w x h box; zoom 1 fits the whole design frame */
function computeView(w, h, fx, fy, zoom) {
  let s = (w / h < DW / DH) ? w / DW : Math.max(w / DW, h / DH);
  s *= (zoom || 1);
  const visH = h / s;
  let cy = fy;
  if (cy - visH / 2 > 70) cy = 70 + visH / 2;         /* never crop the labels */
  if (cy + visH / 2 < fy + 14) cy = fy + 14 - visH / 2; /* never crop the feet */
  const tx = w / 2 - fx * s, ty = h / 2 - cy * s;
  return { s, tx, ty, w, h,
    dx0: -tx / s, dx1: (w - tx) / s, dy0: -ty / s, dy1: (h - ty) / s };
}
function applyView(g, v) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  g.setTransform(dpr * v.s, 0, 0, dpr * v.s, dpr * v.tx, dpr * v.ty);
}
function sizeCanvas(c, w, h) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  c.width = Math.max(1, Math.round(w * dpr));
  c.height = Math.max(1, Math.round(h * dpr));
}

function iso(x, y) {
  return [OX + (x - y) * TILE_W / 2, OY + (x + y) * TILE_H / 2];
}

function diamond(g, cx, cy, w, h, fill, stroke) {
  g.beginPath();
  g.moveTo(cx, cy - h / 2); g.lineTo(cx + w / 2, cy);
  g.lineTo(cx, cy + h / 2); g.lineTo(cx - w / 2, cy);
  g.closePath();
  if (fill) { g.fillStyle = fill; g.fill(); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = 2; g.stroke(); }
}

function drawPaths(g) {
  const paths = [
    { pts: [[1,7],[3,6],[4,4],[4,3]], c: "#40dcff" },
    { pts: [[7,1],[6,2],[6,4],[5,5]], c: "#ffaa3c" },
    { pts: [[2,2],[4,2],[6,3]], c: "#ffe678" },
  ];
  g.lineJoin = "round"; g.lineCap = "round";
  paths.forEach(({ pts, c }) => {
    g.beginPath();
    pts.forEach(([x, y], i) => {
      const [sx, sy] = iso(x, y);
      i ? g.lineTo(sx, sy) : g.moveTo(sx, sy);
    });
    g.globalAlpha = 0.25; g.strokeStyle = c; g.lineWidth = 9; g.stroke();
    g.globalAlpha = 1; g.lineWidth = 3; g.stroke();
  });
}

function drawRack(g, cx, cy, t, phase) {
  const w = 34, h = 62;
  g.fillStyle = "#14183c";
  g.fillRect(cx - w/2, cy - h, w, h);
  g.strokeStyle = "#3c4eb4"; g.lineWidth = 2;
  g.strokeRect(cx - w/2, cy - h, w, h);
  for (let s = 0; s < 5; s++) {
    const ly = cy - h + 8 + s * 10;
    g.fillStyle = "#1e2450";
    g.fillRect(cx - w/2 + 5, ly, w - 10, 5);
    const blink = motionOn ? (Math.floor(t * 2 + phase + s * 0.7) % 2 === 0) : (s % 2 === 0);
    g.fillStyle = blink ? "#50ff8c" : "#ffdc5a";
    if (s === 3) g.fillStyle = "#ff5a5a";
    g.fillRect(cx - 3, ly, 5, 5);
  }
}

/* far wall pinned to the top of the visible rect, racks along its base */
function drawFarWall(g, v, t) {
  const { dx0, dx1, dy0 } = v;
  const WH = 72;
  g.fillStyle = "#101440";
  g.fillRect(dx0 - 8, dy0 - 8, (dx1 - dx0) + 16, WH + 8);
  g.strokeStyle = "#080a28"; g.lineWidth = 2;
  const start = Math.floor((dx0 - 8) / 120) * 120;
  for (let sx = start; sx <= dx1 + 8; sx += 120) {
    g.beginPath(); g.moveTo(sx, dy0 - 8); g.lineTo(sx, dy0 + WH); g.stroke();
  }
  g.fillStyle = "#465ac8";
  g.fillRect(dx0 - 8, dy0 + WH - 2, (dx1 - dx0) + 16, 3);
  const rstart = Math.floor(dx0 / 170) * 170;
  let k = 0;
  for (let wx = rstart; wx <= dx1; wx += 170, k++) {
    drawRack(g, wx + 85, dy0 + WH + 8, t, k * 1.3);
  }
}

/* dark near-wall tops at the bottom corners: looking past them */
function drawForeground(g, v) {
  const { dx0, dx1, dy1 } = v;
  const H = 46, WED = 170;
  g.fillStyle = "rgba(7,7,24,0.9)";
  g.beginPath();
  g.moveTo(dx0 - 8, dy1 + 8); g.lineTo(dx0 + WED, dy1 + 8);
  g.lineTo(dx0 + WED - 70, dy1 - H); g.lineTo(dx0 - 8, dy1 - H);
  g.closePath(); g.fill();
  g.beginPath();
  g.moveTo(dx1 + 8, dy1 + 8); g.lineTo(dx1 - WED, dy1 + 8);
  g.lineTo(dx1 - WED + 70, dy1 - H); g.lineTo(dx1 + 8, dy1 - H);
  g.closePath(); g.fill();
  g.strokeStyle = "#2c3f88"; g.lineWidth = 2;
  g.beginPath(); g.moveTo(dx0 - 8, dy1 - H); g.lineTo(dx0 + WED - 70, dy1 - H); g.stroke();
  g.beginPath(); g.moveTo(dx1 + 8, dy1 - H); g.lineTo(dx1 - WED + 70, dy1 - H); g.stroke();
}

function drawVignette(g, v) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const grad = g.createRadialGradient(
    v.w / 2, v.h / 2, Math.min(v.w, v.h) * 0.42,
    v.w / 2, v.h / 2, Math.max(v.w, v.h) * 0.72);
  grad.addColorStop(0, "rgba(3,3,16,0)");
  grad.addColorStop(1, "rgba(3,3,16,0.45)");
  g.fillStyle = grad;
  g.fillRect(0, 0, v.w, v.h);
}

function sessionTile(i) {
  return SLOTS[i % SLOTS.length];
}

/* per-frame room layout: design coords of each session's tile center.
   Robots wander gently near home while motion is on. */
function layout(t) {
  return allSessions().map((s, i) => {
    const [hx, hy] = sessionTile(i);
    const [cx, cy] = iso(hx, hy);
    let wx = 0, wy = 0;
    if (motionOn) {
      wx = Math.sin(t * 0.32 + i * 2.4) * 34;
      wy = Math.sin(t * 0.23 + i * 1.7) * 16;
    }
    return { s, i, x: cx + wx, y: cy + wy };
  });
}

/* paint the room; returns click anchors (design coords) */
function drawRoom(g, v, t, L, opts) {
  opts = opts || {};
  applyView(g, v);
  g.imageSmoothingEnabled = false;
  const { dx0, dx1, dy0, dy1 } = v;

  /* floor: full bleed, culled where the far wall sits */
  const wallBase = dy0 + 72;
  for (let x = -8; x <= 18; x++) {
    for (let y = -8; y <= 18; y++) {
      const [cx, cy] = iso(x, y);
      if (cy < wallBase - TILE_H / 2) continue;
      if (cx < dx0 - TILE_W || cx > dx1 + TILE_W) continue;
      if (cy < dy0 - TILE_H || cy > dy1 + TILE_H) continue;
      diamond(g, cx, cy, TILE_W, TILE_H,
        ((x + y) % 2 === 0) ? "#3248a8" : "#3a54be", "#1c286e");
    }
  }

  drawPaths(g);
  drawFarWall(g, v, t);

  if (opts.errProvider) {
    /* provider-error window: centered alarm badge, no fake session */
    const p = opts.errProvider;
    const cx = (dx0 + dx1) / 2, cy = (dy0 + dy1) / 2;
    const pl = motionOn && Math.sin(t * 5) > 0 ? 2 : 0;
    g.fillStyle = "#ff5a5a";
    g.beginPath();
    g.moveTo(cx, cy - 26 - pl); g.lineTo(cx + 22, cy);
    g.lineTo(cx, cy + 26 + pl); g.lineTo(cx - 22, cy);
    g.closePath(); g.fill();
    g.fillStyle = "#7a1010";
    g.font = "bold 20px 'Courier New', monospace";
    g.textAlign = "center";
    g.fillText("!", cx, cy + 7);
    g.fillStyle = "#ffb0b0";
    g.font = '8px "Press Start 2P", monospace';
    g.fillText((p.error || "error").slice(0, 30), cx, cy + 44);
    drawForeground(g, v);
    drawVignette(g, v);
    return [];
  }

  const anchorsOut = [];
  const order = [...L].sort((a, b) => {
    const ka = sessionTile(a.i), kb = sessionTile(b.i);
    return (ka[0] + ka[1]) - (kb[0] + kb[1]);
  });

  g.textAlign = "center";
  order.forEach((e) => {
    const { s, i } = e;
    const stale = s.freshness === "stale";
    const err = s.activity === "error" || !!s.error;
    const spr = sprites[s.provider][stale || err ? "dim" : "normal"];
    const rw = spr.width, rh = spr.height;
    const bob = (motionOn && s.activity === "working") ? Math.sin(t * 3 + i * 1.7) * 3 : 0;
    const fx = e.x, fy = e.y + 6; /* feet */

    g.fillStyle = "rgba(0,0,0,0.35)";
    g.beginPath(); g.ellipse(fx, fy + 2, 22, 8, 0, 0, Math.PI * 2); g.fill();

    if (s.session_id === selectedId) {
      const a = motionOn ? 0.55 + 0.45 * Math.sin(t * 4) : 0.9;
      g.globalAlpha = a;
      diamond(g, fx, fy - 6, TILE_W + 10, TILE_H + 10, null, "#41e6ff");
      g.globalAlpha = 1;
    }

    g.drawImage(spr, Math.round(fx - rw / 2), Math.round(fy - rh + bob));

    if (stale || err) {
      g.font = '14px "Press Start 2P", monospace';
      g.fillStyle = "#ff5a5a";
      g.fillText("?", fx, fy - rh - 12 + bob);
    } else if (s.activity === "working") {
      g.fillStyle = "#50ff8c";
      const r = motionOn ? 4 + Math.sin(t * 5 + i) * 1.5 : 4;
      g.beginPath(); g.arc(fx + 20, fy - rh + bob, r, 0, Math.PI * 2); g.fill();
    }

    g.font = '8px "Press Start 2P", monospace';
    g.fillStyle = stale ? "#8a8aa5" : "#b4dcff";
    const label = s.session_id.length > 12 ? s.session_id.slice(0, 11) + "\u2026" : s.session_id;
    g.fillText(label, fx, fy - rh - 26 + bob);

    anchorsOut.push({ sid: s.session_id, x: fx, y: fy - rh / 2 });
  });

  /* iggy the operator: grounded isometric sprite, gentle bob */
  if (iggyIso.complete && iggyIso.naturalWidth) {
    const ip = iggyPos(t);
    const bob = motionOn ? Math.sin(t * 2 + 1) * 2 : 0;
    const fx = ip.x, fy = ip.y + 6; /* feet */
    const dw = 50, dh = 75;
    g.fillStyle = "rgba(0,0,0,0.35)";
    g.beginPath(); g.ellipse(fx, fy + 2, 18, 7, 0, 0, Math.PI * 2); g.fill();
    g.save();
    g.imageSmoothingEnabled = true;
    g.drawImage(iggyIso, Math.round(fx - dw / 2), Math.round(fy - dh + bob), dw, dh);
    g.restore();
    g.font = '8px "Press Start 2P", monospace';
    g.fillStyle = "#ffe678";
    g.fillText("IGGY", fx, fy - dh - 10 + bob);
  }

  if (opts.room) {
    /* provider-level errors: honest badges, not fake sessions */
    const errProvs = ((payload && payload.providers) || []).filter((p) => !p.ok);
    errProvs.forEach((p, k) => {
      const [sx, sy] = SLOTS[(SLOTS.length - 1 - k + SLOTS.length * 4) % SLOTS.length];
      const [cx, cy] = iso(sx, sy);
      diamond(g, cx, cy, 40, 40, "rgba(176,40,40,0.25)", "#ff5a5a");
      g.font = '16px "Press Start 2P", monospace';
      g.fillStyle = "#ff5a5a";
      g.fillText("!", cx, cy + 6);
      g.font = '8px "Press Start 2P", monospace';
      g.fillStyle = "#ff9a9a";
      g.fillText(p.provider.slice(0, 12), cx, cy + 28);
    });
  }

  drawForeground(g, v);
  drawVignette(g, v);
  return anchorsOut;
}

/* ---------- agent windows (mobile follow-cams) ---------- */
const tilesEl = $("#agentTiles");
const TILE_ZOOM = 1.35;
let tiles = []; /* {key, s, err, el, canvas, ctx, dot, nm, focus:{x,y}, w, h} */

function tileHome(i) {
  const [tx, ty] = sessionTile(i);
  const [cx, cy] = iso(tx, ty);
  return { x: cx, y: cy + 6 };
}

function syncTiles() {
  const sessions = allSessions();
  const want = sessions.map((s, i) => ({ key: "s:" + s.session_id, s, i }))
    .concat((payload.providers || []).filter((p) => !p.ok)
      .map((p) => ({ key: "e:" + p.provider, err: p })));
  const wantKeys = new Set(want.map((w) => w.key));
  tiles = tiles.filter((tl) => {
    if (!wantKeys.has(tl.key)) { tl.el.remove(); return false; }
    return true;
  });
  const have = new Set(tiles.map((t) => t.key));
  want.forEach((w) => {
    if (have.has(w.key)) return;
    const d = document.createElement("div");
    d.className = "agent-tile";
    d.tabIndex = 0;
    const c = document.createElement("canvas");
    const tag = document.createElement("div");
    tag.className = "tile-tag";
    tag.setAttribute("aria-hidden", "true");
    const dot = document.createElement("span");
    dot.className = "tile-dot";
    const nm = document.createElement("span");
    tag.appendChild(dot); tag.appendChild(nm);
    d.appendChild(c); d.appendChild(tag);
    tilesEl.appendChild(d);
    const tl = { key: w.key, s: w.s || null, err: w.err || null, el: d,
      canvas: c, ctx: c.getContext("2d"), dot, nm,
      focus: w.s ? tileHome(w.i) : { x: CAMX, y: CAMY }, w: 0, h: 0 };
    if (tl.s) {
      d.setAttribute("role", "button");
      d.setAttribute("aria-label", "Agent window: " + tl.s.session_id + ". Activate to open details.");
      d.addEventListener("click", () => select(tl.s.session_id));
      d.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(tl.s.session_id); }
      });
    } else {
      d.setAttribute("aria-label", "Provider error: " + tl.err.provider);
    }
    tiles.push(tl);
  });
  want.forEach((w) => tilesEl.appendChild(tiles.find((t) => t.key === w.key).el));
}

function fitTiles() {
  tiles.forEach((tl) => {
    const r = tl.el.getBoundingClientRect();
    tl.w = Math.max(1, Math.round(r.width));
    tl.h = Math.max(1, Math.round(r.height));
    sizeCanvas(tl.canvas, tl.w, tl.h);
  });
}

function updateTileTags() {
  tiles.forEach((tl) => {
    if (tl.s) {
      const s = allSessions().find((x) => x.session_id === tl.s.session_id) || tl.s;
      const err = s.activity === "error" || !!s.error;
      const stale = s.freshness === "stale";
      tl.nm.textContent = (s.session_id.length > 12 ? s.session_id.slice(0, 11) + "\u2026" : s.session_id).toUpperCase();
      tl.dot.style.background = err ? "#ff5a5a" : stale ? "#ffb347"
        : s.activity === "working" ? "#39ff6a" : "#8ba3c4";
      const sel = s.session_id === selectedId;
      tl.el.classList.toggle("sel", sel);
      tl.el.setAttribute("aria-selected", sel ? "true" : "false");
    } else if (tl.err) {
      tl.nm.textContent = tl.err.provider.toUpperCase() + " \u2014 ERROR";
      tl.dot.style.background = "#ff5a5a";
    }
  });
}

/* ---------- paint ---------- */
function fitRoom() {
  const r = room.el.getBoundingClientRect();
  room.w = Math.max(1, Math.round(r.width));
  room.h = Math.max(1, Math.round(r.height));
  sizeCanvas(room.canvas, room.w, room.h);
  room.v = computeView(room.w, room.h, CAMX, CAMY, 1);
}

function drawAll(t) {
  const L = layout(t);
  if (room.el.offsetParent !== null && room.v) {
    anchors = drawRoom(room.ctx, room.v, t, L, { room: true });
  }
  if (tilesEl.offsetParent !== null) {
    tiles.forEach((tl) => {
      if (tl.s) {
        const e = L.find((en) => en.s.session_id === tl.s.session_id);
        if (e) { /* ease the camera toward the wandering robot */
          tl.focus.x += (e.x - tl.focus.x) * 0.08;
          tl.focus.y += ((e.y + 6) - tl.focus.y) * 0.08;
        }
      }
      const v = computeView(tl.w, tl.h, tl.focus.x, tl.focus.y, TILE_ZOOM);
      drawRoom(tl.ctx, v, t, L, tl.err ? { errProvider: tl.err } : {});
    });
  }
}

/* animation */
let rafId = null;
const t0 = performance.now();
function loop(now) {
  if (root.dataset.view !== "sector") { rafId = null; return; }
  drawAll((now - t0) / 1000);
  rafId = motionOn ? requestAnimationFrame(loop) : null;
}
function kickRender() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  if (motionOn && root.dataset.view === "sector") {
    rafId = requestAnimationFrame(loop);
  } else {
    drawAll(0);
  }
}

/* picking + keyboard (desktop room canvas) */
room.canvas.addEventListener("click", (ev) => {
  if (!room.v) return;
  const r = room.canvas.getBoundingClientRect();
  const x = (ev.clientX - r.left - room.v.tx) / room.v.s;
  const y = (ev.clientY - r.top - room.v.ty) / room.v.s;
  let best = null, bd = 52;
  anchors.forEach((a) => {
    const d = Math.hypot(a.x - x, a.y - y);
    if (d < bd) { bd = d; best = a; }
  });
  if (best) select(best.sid);
});

room.canvas.addEventListener("keydown", (ev) => {
  const ids = anchors.map((a) => a.sid);
  if (!ids.length) return;
  let i = ids.indexOf(selectedId);
  if (["ArrowRight", "ArrowDown"].includes(ev.key)) { ev.preventDefault(); i = (i + 1) % ids.length; select(ids[i]); }
  else if (["ArrowLeft", "ArrowUp"].includes(ev.key)) { ev.preventDefault(); i = (i - 1 + ids.length) % ids.length; select(ids[i]); }
  else if (ev.key === "Enter") { ev.preventDefault(); if (selectedId) select(selectedId); }
});

/* ================= panels ================= */
function renderActivity() {
  const actBody = $("#activityBody");
  actBody.replaceChildren();
  const feed = [];
  allSessions().forEach((s) =>
    (s.tools || []).forEach((t) =>
      feed.push({ sid: s.session_id, tool: t.tool, outcome: t.outcome, note: t.note, at: t.at })));
  feed.sort((a, b) => (b.at || "").localeCompare(a.at || ""));
  if (!feed.length) {
    actBody.appendChild(el("div", "note", "No tool activity reported."));
    return;
  }
  feed.forEach((e) => {
    const d = el("div", "act");
    d.appendChild(el("span", "tool", e.tool));
    d.appendChild(el("span", e.outcome === "ok" ? "out-ok" : "out-err",
      (e.outcome || "?").toUpperCase()));
    d.appendChild(el("span", "sess", e.sid));
    if (e.note) d.appendChild(el("span", "note", e.note));
    d.appendChild(el("span", "age", relTime(e.at)));
    actBody.appendChild(d);
  });
}

function renderList() {
  const listBody = $("#listBody");
  listBody.replaceChildren();
  allSessions().forEach((s) => {
    const stTxt = s.error ? "ERROR" : s.freshness === "stale" ? "STALE" : "OK";
    const tr = el("tr");
    tr.tabIndex = 0;
    tr.setAttribute("aria-selected", s.session_id === selectedId ? "true" : "false");
    const cells = [
      [s.session_id, true], [s.provider, false], [s.model, false],
      [s.activity, false], [fmtN(s.context_used), false, "num"],
      [fmtN(s.context_limit), false, "num"], [occLabel(s), false, "num"],
      [s.source, false], [relAge(s.age_sec), false],
    ];
    cells.forEach(([text, strong, cls]) => {
      const td = el("td", cls || null);
      td.appendChild(strong ? el("strong", null, text) : document.createTextNode(text));
      tr.appendChild(td);
    });
    let state = stTxt;
    if (s.error) state += " — " + s.error;
    else if (s.unavailable_reason && s.percent_used === null) state += " — " + s.unavailable_reason;
    tr.appendChild(el("td", null, state));
    tr.addEventListener("click", () => select(s.session_id));
    tr.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); select(s.session_id); }
    });
    listBody.appendChild(tr);
  });
}

function renderLoad() {
  const body = $("#loadBody");
  body.replaceChildren();
  allSessions().forEach((s) => {
    const row = el("div", "load-row");
    const nm = el("span", "nm", s.session_id);
    nm.title = `${s.provider} · ${fmtN(s.context_used)} / ${fmtN(s.context_limit)} tokens`;
    row.appendChild(nm);
    const bar = el("div", "load-bar");
    const fill = el("div", "load-fill" +
      (s.percent_used === null ? " unknown" : s.percent_used > 85 ? " warn" : ""));
    if (s.percent_used !== null) fill.style.width = Math.min(100, s.percent_used) + "%";
    else fill.style.width = "100%";
    fill.setAttribute("role", "img");
    fill.setAttribute("aria-label", `context occupancy ${occLabel(s)}`);
    bar.appendChild(fill);
    row.appendChild(bar);
    row.appendChild(el("span", "pc", occLabel(s)));
    body.appendChild(row);
  });
}

function renderProviders() {
  const body = $("#provBody");
  body.replaceChildren();
  [...payload.providers]
    .sort((a, b) => a.provider.localeCompare(b.provider))
    .forEach((p) => {
      const row = el("div", "prov-row");
      row.appendChild(el("span", "nm", p.provider.toUpperCase()));
      const worst = !p.ok ? "err"
        : (p.sessions || []).some((s) => s.freshness === "stale") ? "stale" : "ok";
      row.appendChild(el("span", "pill " + worst,
        { ok: "HEALTHY", stale: "STALE DATA", err: "PROVIDER ERROR" }[worst]));
      const n = (p.sessions || []).length;
      row.appendChild(el("span", "cnt", `${n} session${n === 1 ? "" : "s"}` +
        (p.ok ? "" : ` — ${p.error || "error"}`)));
      body.appendChild(row);
    });
}

function select(sid) {
  selectedId = sid;
  const s = allSessions().find((x) => x.session_id === sid);
  const win = $("#detailWin");
  document.querySelectorAll("#listBody tr").forEach((n) =>
    n.setAttribute("aria-selected", "false"));
  if (!s) { win.hidden = true; kickRender(); return; }
  win.hidden = false;
  $("#detailTitle").textContent = "SESSION — " + s.session_id.toUpperCase().slice(0, 18);
  const dl = $("#detailDl");
  dl.replaceChildren();
  const rows = [
    ["Provider", s.provider], ["Model", s.model], ["Activity", s.activity],
    ["Context used", fmtN(s.context_used)], ["Context limit", fmtN(s.context_limit)],
    ["Occupancy", occLabel(s)], ["Measurement source", s.source],
    ["Observed at", s.observed_at || "—"],
    ["Freshness", s.freshness + (s.freshness === "stale" ? ` (older than ${payload.stale_after_sec}s)` : "")],
  ];
  if (s.unavailable_reason) rows.push(["Unavailable reason", s.unavailable_reason]);
  if (s.error) rows.push(["Error", s.error]);
  rows.forEach(([k, v]) => {
    dl.appendChild(el("dt", null, k));
    dl.appendChild(el("dd", null, v));
  });
  document.querySelectorAll("#listBody tr").forEach((n) => {
    const strong = n.querySelector("strong");
    if (strong && strong.textContent === sid) n.setAttribute("aria-selected", "true");
  });
  updateTileTags();
  kickRender();
  win.scrollIntoView({ block: "nearest" });
}

$("#detailX").addEventListener("click", () => {
  $("#detailWin").hidden = true;
  selectedId = null;
  kickRender();
});

/* ================= render root ================= */
function render() {
  const demo = payload.mode === "demo";
  demoBanner.hidden = !demo;
  modeBadge.textContent = demo ? "DEMO" : "LIVE";
  modeBadge.classList.toggle("demo", demo);

  const hasProviders = payload.providers.length > 0;
  emptyState.hidden = hasProviders;
  $("#boardView").style.display = hasProviders ? "" : "none";
  $("#listView").style.display = hasProviders ? "" : "none";
  if (!hasProviders) {
    $("#detailWin").hidden = true; selectedId = null;
    tiles = []; tilesEl.replaceChildren();
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    return;
  }

  ensureSprites();
  fitRoom();
  syncTiles();
  fitTiles();
  const nSessions = allSessions().length;
  $("#vpCount").textContent = nSessions + (nSessions === 1 ? " SESSION" : " SESSIONS");
  canvas.setAttribute("aria-label",
    "Robot room viewport: " + nSessions + (nSessions === 1 ? " session" : " sessions") + ". " +
    allSessions().map((s) => s.session_id + " " + s.activity).join(", ") +
    ". Arrow keys move between sessions, Enter opens details.");
  updateTileTags();
  kickRender();
  renderActivity();
  renderList();
  renderLoad();
  renderProviders();
  if (selectedId && !allSessions().some((s) => s.session_id === selectedId)) {
    $("#detailWin").hidden = true; selectedId = null;
  }
}

/* ================= controls ================= */
function setView(v) {
  root.dataset.view = v;
  $("#viewBtn").textContent = "VIEW: " + v.toUpperCase();
  kickRender();
}
$("#viewBtn").addEventListener("click", () =>
  setView(root.dataset.view === "list" ? "sector" : "list"));

function setMotion(on) {
  motionOn = on;
  root.dataset.motion = on ? "on" : "off";
  $("#motionBtn").textContent = "MOTION: " + (on ? "ON" : "OFF");
  kickRender();
}
$("#motionBtn").addEventListener("click", () => setMotion(!motionOn));
if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setMotion(false);

function tick() {
  $("#clock").textContent = "updated " + new Date().toLocaleTimeString("en-US", { hour12: false });
}
tick();
setInterval(tick, 1000);
$("#refreshBtn").addEventListener("click", refresh);

document.addEventListener("keydown", (ev) => {
  if (ev.target.matches("input, textarea") || ev.target === canvas) return;
  const k = ev.key.toLowerCase();
  if (k === "1") setView("sector");
  else if (k === "2") setView("list");
  else if (k === "r") refresh();
  else if (k === "escape" && !$("#detailWin").hidden) $("#detailX").click();
});

/* viewport sizing */
fitRoom();
new ResizeObserver(() => { fitRoom(); fitTiles(); kickRender(); }).observe(room.el);
new ResizeObserver(() => { fitTiles(); kickRender(); }).observe(tilesEl);

setView("sector");
refresh();
