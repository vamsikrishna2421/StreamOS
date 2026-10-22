"use strict";
// StreamOS web client. Works with a TV remote (arrow keys + Enter + Back)
// and with touch. No build step, no framework — just the platform.

const API = {
  async get(p) { const r = await fetch(p); if (!r.ok) throw await err(r); return r.json(); },
  async post(p, body) {
    const r = await fetch(p, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw await err(r); return r.json();
  },
  async del(p) { const r = await fetch(p, { method: "DELETE" }); if (!r.ok) throw await err(r); return r.json(); },
};
async function err(r) { try { const j = await r.json(); return new Error(j.detail || r.statusText); } catch { return new Error(r.statusText); } }

const ROUTES = [
  { id: "home", label: "Home", ic: "⌂" },
  { id: "live", label: "Live TV", ic: "📡" },
  { id: "movies", label: "Movies", ic: "🎬" },
  { id: "series", label: "Series", ic: "📺" },
  { id: "favorites", label: "Favorites", ic: "★" },
  { id: "continue", label: "Continue Watching", ic: "⏯" },
  { id: "devices", label: "Connected Devices", ic: "🖧" },
  { id: "shared", label: "Shared Viewing", ic: "👥" },
  { id: "independent", label: "Independent Viewing", ic: "⤬" },
  { id: "sources", label: "Streaming Sources", ic: "🗄" },
  { id: "settings", label: "Settings", ic: "⚙" },
  { id: "diagnostics", label: "Diagnostics", ic: "📊" },
];

const state = {
  route: "home",
  device: null,            // {id,name,platform}
  favorites: new Set(JSON.parse(localStorage.getItem("favorites") || "[]")),
  playSession: null,       // {id, source_id}
  heartbeat: null,
  diagTimer: null,
};

// --- device identity -----------------------------------------------------
async function ensureDevice() {
  const saved = localStorage.getItem("device");
  if (saved) { state.device = JSON.parse(saved); return; }
  // self-register this browser as a device via the real pairing flow
  const { code } = await API.post("/api/pair/start", { name: deviceName(), platform: "web" });
  const dev = await API.post("/api/pair/complete", { code, name: deviceName(), platform: "web" });
  state.device = dev;
  localStorage.setItem("device", JSON.stringify(dev));
}
function deviceName() {
  const ua = navigator.userAgent;
  const kind = /TV|SmartTV|AFT|BRAVIA/i.test(ua) ? "TV" :
               /iPhone|Android.*Mobile/i.test(ua) ? "Phone" : "Browser";
  return `${kind} (${location.hostname})`;
}

// --- nav -----------------------------------------------------------------
function buildNav() {
  const nav = document.getElementById("sidebar");
  ROUTES.forEach(r => {
    const b = document.createElement("button");
    b.className = "nav-item focusable" + (r.id === state.route ? " active" : "");
    b.dataset.route = r.id;
    b.innerHTML = `<span class="ic">${r.ic}</span><span>${r.label}</span>`;
    b.onclick = () => go(r.id);
    nav.appendChild(b);
  });
}
function go(route) {
  state.route = route;
  document.querySelectorAll(".nav-item").forEach(n =>
    n.classList.toggle("active", n.dataset.route === route));
  render();
}

// --- rendering helpers ---------------------------------------------------
const main = () => document.getElementById("main");
function page(title, sub) {
  main().innerHTML = `<h1 class="page">${title}</h1>` +
    (sub ? `<p class="sub">${sub}</p>` : "");
}
function card({ title, desc, icon, live, progress, onActivate }) {
  const c = document.createElement("button");
  c.className = "card focusable";
  c.innerHTML =
    `<div class="thumb">${live ? '<span class="live-dot">LIVE</span>' : ""}${icon || "🎞"}</div>` +
    `<div class="meta"><div class="t">${title}</div><div class="d">${desc || ""}</div></div>` +
    (progress != null ? `<div class="progress"><i style="width:${Math.round(progress * 100)}%"></i></div>` : "");
  c.onclick = onActivate;
  return c;
}
function grid(cards) {
  const g = document.createElement("div"); g.className = "grid";
  cards.forEach(c => g.appendChild(c));
  return g;
}
function emptyMsg(t) { const d = document.createElement("div"); d.className = "empty"; d.textContent = t; return d; }

// --- screens -------------------------------------------------------------
const screens = {
  async home() {
    page("Home", `Signed in as ${state.device?.name || "this device"}`);
    const sources = await API.get("/api/sources?enabled_only=true");
    const hist = await API.get("/api/history");
    if (hist.length) {
      main().insertAdjacentHTML("beforeend", `<div class="section-title">Continue Watching</div>`);
      main().appendChild(grid(hist.slice(0, 6).map(h => card({
        title: h.source_name || h.source_id,
        desc: h.duration_s ? `${Math.round(h.position_s)}s / ${Math.round(h.duration_s)}s` : "",
        progress: h.duration_s ? h.position_s / h.duration_s : 0,
        icon: "⏯",
        onActivate: () => playSource(h.source_id, h.source_name),
      }))));
    }
    main().insertAdjacentHTML("beforeend", `<div class="section-title">Channels & Content</div>`);
    if (!sources.length) { main().appendChild(emptyMsg("No sources yet. Add one under Streaming Sources.")); return; }
    main().appendChild(grid(sources.map(s => card({
      title: s.name, desc: s.kind.toUpperCase(), live: s.kind === "live",
      icon: s.kind === "live" ? "📡" : "🎬",
      onActivate: () => playSource(s.id, s.name),
    }))));
  },

  async live() { await listByKind("Live TV", "Channels you can tune to", "live"); },
  async movies() { await listByKind("Movies", "On-demand films", "vod", "movie"); },
  async series() { await listByKind("Series", "Episodic content", "vod", "series"); },

  async favorites() {
    page("Favorites", "Your starred channels and content");
    const sources = await API.get("/api/sources");
    const favs = sources.filter(s => state.favorites.has(s.id));
    if (!favs.length) { main().appendChild(emptyMsg("No favorites yet. Press ★ on any item.")); return; }
    main().appendChild(grid(favs.map(s => card({
      title: s.name, desc: s.kind.toUpperCase(), live: s.kind === "live",
      onActivate: () => playSource(s.id, s.name),
    }))));
  },

  async continue() {
    page("Continue Watching", "Pick up where any device left off");
    const hist = await API.get("/api/history");
    if (!hist.length) { main().appendChild(emptyMsg("Nothing in progress.")); return; }
    main().appendChild(grid(hist.map(h => card({
      title: h.source_name || h.source_id,
      desc: h.duration_s ? `${Math.round(h.position_s)}s / ${Math.round(h.duration_s)}s` : `${Math.round(h.position_s)}s`,
      progress: h.duration_s ? h.position_s / h.duration_s : 0, icon: "⏯",
      onActivate: () => playSource(h.source_id, h.source_name),
    }))));
  },

  async devices() {
    page("Connected Devices", "Household devices paired with this hub");
    const wrap = document.createElement("div");
    wrap.innerHTML = `<div class="row" style="margin-bottom:20px">
      <button class="btn focusable" id="pairBtn">Pair a new device</button>
      <span class="sub" id="pairCode" style="margin:0"></span></div>`;
    main().appendChild(wrap);
    wrap.querySelector("#pairBtn").onclick = async () => {
      const { code, ttl_s } = await API.post("/api/pair/start", { name: "New device", platform: "web" });
      wrap.querySelector("#pairCode").textContent =
        `Enter ${code} on the new device within ${Math.round(ttl_s / 60)} min`;
    };
    const devs = await API.get("/api/devices");
    const t = document.createElement("table");
    t.innerHTML = `<tr><th>Name</th><th>Platform</th><th>Paired</th><th></th></tr>`;
    devs.forEach(d => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${d.name}</td><td>${d.platform || "-"}</td>
        <td>${fmtAgo(d.paired_at)}</td>
        <td><button class="btn danger focusable" data-id="${d.id}">Remove</button></td>`;
      tr.querySelector("button").onclick = async (e) => {
        await API.del(`/api/devices/${e.target.dataset.id}`); render();
      };
      t.appendChild(tr);
    });
    main().appendChild(t);
  },

  async shared() { await sessionsView("Shared Viewing", "shared", "Multiple devices on one upstream stream"); },
  async independent() { await sessionsView("Independent Viewing", "independent", "Each device on its own source"); },

  async sources() {
    page("Streaming Sources", "Authorized upstream streams this hub may relay");
    const form = document.createElement("div");
    form.className = "row"; form.style.cssText = "margin-bottom:22px;align-items:flex-end;gap:14px";
    form.innerHTML = `
      <label class="field">Name<input id="s-name" class="focusable" placeholder="Channel 1"></label>
      <label class="field">Kind<select id="s-kind" class="focusable"><option value="live">live</option><option value="vod">vod</option></select></label>
      <label class="field" style="flex:1;min-width:260px">Upstream URL<input id="s-url" class="focusable" placeholder="http://origin/ch1/index.m3u8"></label>
      <label class="field">Max sessions<input id="s-max" class="focusable" type="number" value="1" min="1" style="width:90px"></label>
      <label class="field">Shareable<select id="s-share" class="focusable"><option value="1">yes</option><option value="0">no</option></select></label>
      <button class="btn focusable" id="s-add">Add source</button>`;
    main().appendChild(form);
    form.querySelector("#s-add").onclick = async () => {
      const body = {
        name: val("#s-name"), kind: val("#s-kind"), upstream_url: val("#s-url"),
        max_sessions: parseInt(val("#s-max") || "1", 10), shareable: val("#s-share") === "1",
      };
      if (!body.name || !body.upstream_url) { toast("Name and URL required"); return; }
      try { await API.post("/api/sources", body); toast("Source added"); render(); }
      catch (e) { toast(e.message); }
    };
    const sources = await API.get("/api/sources");
    const t = document.createElement("table");
    t.innerHTML = `<tr><th>Name</th><th>Kind</th><th>Max</th><th>Shareable</th><th>Enabled</th><th></th></tr>`;
    sources.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${s.name}</td><td>${s.kind}</td><td>${s.max_sessions}</td>
        <td>${s.shareable ? "yes" : "no"}</td>
        <td><span class="pill ${s.enabled ? "good" : "bad"}">${s.enabled ? "on" : "off"}</span></td>
        <td class="row"><button class="btn ghost focusable" data-play="${s.id}" data-name="${s.name}">Play</button>
        <button class="btn danger focusable" data-del="${s.id}">Delete</button></td>`;
      tr.querySelector("[data-play]").onclick = (e) => playSource(e.target.dataset.play, e.target.dataset.name);
      tr.querySelector("[data-del]").onclick = async (e) => { await API.del(`/api/sources/${e.target.dataset.del}`); render(); };
      t.appendChild(tr);
    });
    main().appendChild(t);
  },

  async settings() {
    page("Settings", "Hub and playback preferences");
    const health = await API.get("/api/health");
    const m = await API.get("/api/metrics");
    const div = document.createElement("div");
    div.innerHTML = `
      <div class="section-title">Appearance</div>
      <div class="row"><button class="btn ghost focusable" id="themeBtn">Toggle light / dark</button></div>
      <div class="section-title">Hub</div>
      <table>
        <tr><td>Version</td><td>${health.version}</td></tr>
        <tr><td>Active upstream sessions</td><td>${m.upstream_sessions}</td></tr>
        <tr><td>Active viewers</td><td>${m.viewing_sessions}</td></tr>
        <tr><td>This device</td><td>${state.device?.name} · ${state.device?.id}</td></tr>
      </table>`;
    main().appendChild(div);
    div.querySelector("#themeBtn").onclick = () => {
      const el = document.documentElement;
      el.dataset.theme = el.dataset.theme === "light" ? "dark" : "light";
      localStorage.setItem("theme", el.dataset.theme);
    };
  },

  async diagnostics() {
    page("Diagnostics", "Live hub health — refreshes every 2s");
    const host = document.createElement("div"); main().appendChild(host);
    const paint = async () => {
      let m; try { m = await API.get("/api/metrics"); } catch { return; }
      const c = m.metrics.counters;
      const mb = n => (n / 1e6).toFixed(1) + " MB";
      host.innerHTML = `
        <div class="metrics">
          ${metric(m.upstream_sessions, "Upstream sessions")}
          ${metric(m.viewing_sessions, "Local viewers")}
          ${metric((m.metrics.cache_hit_ratio * 100).toFixed(0) + "%", "Cache hit ratio")}
          ${metric(c.upstream_segment_fetches, "Upstream segment fetches")}
          ${metric(c.downstream_segment_serves, "Downstream serves")}
          ${metric(mb(c.upstream_bytes), "Ingress")}
          ${metric(mb(c.downstream_bytes), "Egress")}
          ${metric((m.metrics.ttfs_avg_s ?? "-"), "Avg time-to-first-seg (s)")}
          ${metric(c.errors, "Errors")}
          ${metric((m.host.cpu_percent ?? "-") + "%", "Host CPU")}
          ${metric((m.host.mem_percent ?? "-") + "%", "Host RAM")}
          ${metric(m.metrics.uptime_s + "s", "Uptime")}
        </div>
        <div class="section-title">Upstream session detail</div>
        <table><tr><th>Source</th><th>Subscribers</th><th>Age</th><th>Idle</th></tr>
        ${m.upstream_detail.map(s => `<tr><td>${s.source_id}</td><td>${s.subscribers}</td><td>${s.age_s}s</td><td>${s.idle_s}s</td></tr>`).join("") || `<tr><td colspan=4 class="sub">none active</td></tr>`}
        </table>
        <div class="row" style="margin-top:18px"><button class="btn ghost focusable" id="resetM">Reset counters</button></div>`;
      const rb = host.querySelector("#resetM");
      if (rb) rb.onclick = async () => { await API.post("/api/metrics/reset"); paint(); };
    };
    await paint();
    clearInterval(state.diagTimer);
    state.diagTimer = setInterval(paint, 2000);
  },
};

function metric(v, k) { return `<div class="metric"><div class="v">${v}</div><div class="k">${k}</div></div>`; }

async function listByKind(title, sub, kind, group) {
  page(title, sub);
  const sources = (await API.get("/api/sources")).filter(s =>
    s.kind === kind && (!group || (s.group_name || "").toLowerCase() === group));
  if (!sources.length) {
    // fall back: for movies/series with no group, show all vod
    const alt = (await API.get("/api/sources")).filter(s => s.kind === kind);
    if (!alt.length) { main().appendChild(emptyMsg(`No ${kind} sources yet.`)); return; }
    main().appendChild(grid(alt.map(s => sourceCard(s)))); return;
  }
  main().appendChild(grid(sources.map(s => sourceCard(s))));
}
function sourceCard(s) {
  const c = card({
    title: s.name, desc: s.kind.toUpperCase(), live: s.kind === "live",
    icon: s.kind === "live" ? "📡" : "🎬",
    onActivate: () => playSource(s.id, s.name),
  });
  return c;
}

async function sessionsView(title, mode, sub) {
  page(title, sub);
  const sessions = (await API.get("/api/sessions")).filter(s => s.mode === mode);
  if (!sessions.length) { main().appendChild(emptyMsg(`No ${mode} viewers right now.`)); return; }
  const t = document.createElement("table");
  t.innerHTML = `<tr><th>Channel</th><th>Device</th><th>Mode</th><th>For</th></tr>`;
  sessions.forEach(s => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${s.source_name}</td><td>${s.device_name}</td>
      <td><span class="pill ${s.mode}">${s.mode}</span></td><td>${s.age_s}s</td>`;
    t.appendChild(tr);
  });
  main().appendChild(t);
}

// --- playback ------------------------------------------------------------
let hls = null;
async function playSource(sourceId, name) {
  try {
    const res = await API.post(`/api/play?device_id=${encodeURIComponent(state.device.id)}&source_id=${encodeURIComponent(sourceId)}`);
    if (!res.ok) { toast(`Can't play: ${res.reason}`); return; }
    state.playSession = { id: null, source_id: sourceId };
    // find our viewing session id for heartbeats
    const sessions = await API.get("/api/sessions");
    const mine = sessions.find(s => s.source_id === sourceId && s.device_id === state.device.id);
    if (mine) state.playSession.id = mine.id;

    const video = document.getElementById("pl-video");
    document.getElementById("pl-title").textContent = `${name} · ${res.mode}`;
    document.getElementById("player").classList.add("open");
    const url = res.play_url;
    if (hls) { hls.destroy(); hls = null; }
    video.removeAttribute("src"); video.load();
    const isHls = url.includes(".m3u8");
    if (isHls && window.Hls && Hls.isSupported()) {
      hls = new Hls({ enableWorker: true });
      hls.on(Hls.Events.ERROR, (_e, d) =>
        console.log(`HLS_ERR ${d.type} ${d.details} fatal=${d.fatal}`));
      hls.loadSource(url); hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
    } else {
      // direct file (local movie) or native-HLS browser (Safari)
      video.src = url;
    }
    video.play().catch(() => {});
    startHeartbeat(video);
  } catch (e) { toast(e.message); }
}
function startHeartbeat(video) {
  clearInterval(state.heartbeat);
  state.heartbeat = setInterval(async () => {
    if (!state.playSession?.id) return;
    try {
      await API.post(`/api/sessions/${state.playSession.id}/heartbeat?position_s=${video.currentTime || 0}`);
    } catch {}
  }, 5000);
}
async function closePlayer() {
  const p = document.getElementById("player");
  if (!p.classList.contains("open")) return;
  p.classList.remove("open");
  const video = document.getElementById("pl-video");
  video.pause();
  if (hls) { hls.destroy(); hls = null; }
  clearInterval(state.heartbeat);
  if (state.playSession) {
    const { id, source_id } = state.playSession;
    try {
      await API.post("/api/history", { source_id, position_s: video.currentTime || 0, duration_s: video.duration || null });
      if (id) await API.post(`/api/sessions/${id}/end`);
    } catch {}
    state.playSession = null;
  }
}
document.getElementById("pl-close").onclick = closePlayer;

// --- misc ----------------------------------------------------------------
function val(sel) { const e = document.querySelector(sel); return e ? e.value.trim() : ""; }
function fmtAgo(ts) {
  if (!ts) return "-";
  const s = Date.now() / 1000 - ts;
  if (s < 90) return "just now";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
let toastTimer = null;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

async function render() {
  clearInterval(state.diagTimer);
  try { await screens[state.route](); }
  catch (e) { page("Error", e.message); }
  // focus first item for remote users
  const first = main().querySelector(".focusable") || document.querySelector(".nav-item.active");
  if (first && document.activeElement === document.body) first.focus();
}

// --- spatial D-pad navigation -------------------------------------------
function focusables() {
  return [...document.querySelectorAll(".focusable")].filter(el => el.offsetParent !== null);
}
function moveFocus(dir) {
  const cur = document.activeElement;
  const items = focusables();
  if (!items.length) return;
  if (!cur || !items.includes(cur)) { items[0].focus(); return; }
  const r = cur.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of items) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    const dx = bx - cx, dy = by - cy;
    const ok = dir === "left" ? dx < -4 : dir === "right" ? dx > 4 :
               dir === "up" ? dy < -4 : dy > 4;
    if (!ok) continue;
    const along = (dir === "left" || dir === "right") ? Math.abs(dx) : Math.abs(dy);
    const cross = (dir === "left" || dir === "right") ? Math.abs(dy) : Math.abs(dx);
    const score = along + cross * 2.5;   // prefer same row/column
    if (score < bestScore) { bestScore = score; best = el; }
  }
  if (best) best.focus();
}
document.addEventListener("keydown", (e) => {
  const playerOpen = document.getElementById("player").classList.contains("open");
  if (e.key === "Escape" || e.key === "Backspace" || e.key === "GoBack") {
    if (playerOpen) { e.preventDefault(); closePlayer(); return; }
  }
  if (playerOpen) return;  // let video controls handle the rest
  switch (e.key) {
    case "ArrowLeft": e.preventDefault(); moveFocus("left"); break;
    case "ArrowRight": e.preventDefault(); moveFocus("right"); break;
    case "ArrowUp": e.preventDefault(); moveFocus("up"); break;
    case "ArrowDown": e.preventDefault(); moveFocus("down"); break;
    case "Enter": if (document.activeElement?.classList.contains("focusable")) document.activeElement.click(); break;
  }
});

// --- boot ----------------------------------------------------------------
(async function boot() {
  if (localStorage.getItem("theme")) document.documentElement.dataset.theme = localStorage.getItem("theme");
  buildNav();
  try { await ensureDevice(); } catch (e) { /* hub may be read-only */ }
  await render();
})();
