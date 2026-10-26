/* FS25 Balancer v15 — UI-слой (vanilla JS, без CDN: работает офлайн в exe) */
"use strict";

const API_PROXY = "__FS25_API__";
const S = {
  boot: null, items: new Map(), order: [],
  filter: "all", query: "", busy: false,
  brandTab: null, tourStep: -1, probed: false,
};

/* ── мост к Python ── */
function api() {
  if (window.pywebview && window.pywebview.api) return window.pywebview.api;
  return null;
}
async function call(name, ...args) {
  const a = api();
  // До завершения boot мост может отсутствовать первые сотни мс — молча ретраимся,
  // тостим только когда UI уже живёт, а вызов всё равно не проходит.
  if (!a || typeof a[name] !== "function") {
    if (S.boot) toast("err", "Мост Python ещё не готов");
    return null;
  }
  try {
    return await a[name](...args);
  } catch (e) {
    console.error(name, e);
    toast("err", "Ошибка вызова: " + name);
    return null;
  }
}

/* ── утилиты ── */
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
const fmt = n => { n = Math.round(Number(n) || 0); return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u2009"); };
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const clampNum = (v, min, max, def) => {
  const n = parseFloat(String(v).replace(",", "."));
  if (!isFinite(n)) return def;
  return Math.min(max, Math.max(min, n));
};
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function toast(kind, text, ms) {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  const ic = { ok: "\u2713", err: "\u2715", warn: "\u26a0", info: "\u25cf" }[kind] || "\u25cf";
  el.innerHTML = `<i>${ic}</i><span>${esc(text)}</span>`;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("is-out"); setTimeout(() => el.remove(), 260); }, ms || 3400);
}

let _ac = null;
/* Мягкий обволакивающий финальный аккорд (успех) или поникший дуэт (ошибка) */
function chime(kind) {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    _ac = _ac || new AC();
    if (_ac.state === "suspended") _ac.resume();
    const ac = _ac, t0 = ac.currentTime;
    const master = ac.createGain();
    master.gain.setValueAtTime(0.0001, t0);
    master.gain.linearRampToValueAtTime(kind === "err" ? 0.07 : 0.09, t0 + 0.06);
    master.gain.exponentialRampToValueAtTime(0.0001, t0 + 2.1);
    const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 2200; lp.Q.value = 0.6;
    lp.connect(master); master.connect(ac.destination);
    const notes = kind === "err" ? [392.0, 311.13] : [523.25, 659.25, 783.99, 1046.5];
    notes.forEach((f, i) => {
      const o = ac.createOscillator(); o.type = "sine"; o.frequency.value = f;
      const g = ac.createGain();
      const st = t0 + i * (kind === "err" ? 0.16 : 0.13);
      g.gain.setValueAtTime(0.0001, st);
      g.gain.linearRampToValueAtTime(1 - i * 0.16, st + 0.05);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 2.0);
      o.connect(g); g.connect(lp); o.start(st); o.stop(t0 + 2.1);
    });
  } catch (e) { /* украшение, не критично */ }
}

/* JS-ошибки иначе исчезают молча: пересылаем их в python-лог (crash.log) и показываем тост */
function reportJsError(where, e) {
  const msg = (e && (e.message || e.reason)) || String(e);
  const file = (e && (e.filename || e.sourceURL)) || "";
  const line = e && (e.lineno || e.line || e.lineNumber) ? ":" + (e.lineno || e.line || e.lineNumber) : "";
  const txt = "[js-error] " + where + " " + msg + " @" + file + line;
  try { call("log", txt); } catch (err) {}
  try { console.error(txt); } catch (err) {}
  if (!window.__jsErrToast) {
    window.__jsErrToast = 1;
    setTimeout(() => toast("err", "Ошибка интерфейса: " + msg, 9000), 900);
  }
}
window.addEventListener("error", e => reportJsError("window", e));
window.addEventListener("unhandledrejection", e => reportJsError("promise", (e && e.reason) || e));

function log(text, state) {
  const bar = $(".logbar");
  $("#logText").textContent = text;
  bar.classList.remove("is-busy", "is-ok", "is-err");
  if (state) bar.classList.add("is-" + state);
}

/* ── слайдеры: заполнение трека + живое значение ── */
function bindRange(el, out, text, fmtFn) {
  const paint = () => {
    const min = parseFloat(el.min), max = parseFloat(el.max), v = parseFloat(el.value);
    el.style.setProperty("--fill", ((v - min) / (max - min) * 100).toFixed(2) + "%");
    if (out) out.textContent = fmtFn ? fmtFn(v) : v;
  };
  el.addEventListener("input", paint);
  paint();
  if (text) el.addEventListener("change", text);
  return paint;
}

/* ── навигация ── */
const VIEW_TITLES = {
  scan: "Скан и таблица", prices: "Цены и коэффициенты", countries: "Страны",
  fields: "Поля и расстояние", pro: "PRO-режим / ИИ",
};
function showView(key) {
  $$(".nav-i").forEach(b => b.classList.toggle("is-on", b.dataset.view === key));
  $$(".view").forEach(v => v.classList.toggle("is-on", v.id === "view-" + key));
  $("#viewTitle").textContent = VIEW_TITLES[key] || "";
  if (key === "fields") drawCurve();
}
$$(".nav-i").forEach(b => {
  b.onclick = () => { showView(b.dataset.view); if (S.tourStep >= 0) placeTour(); };
});

/* ── кинематографичная заставка (стиль Ubisoft) ── */
S.introDone = false;
let _fxRAF = 0;
let _introRes = null;
const _introP = new Promise(r => { _introRes = r; });

function finishIntro() {
  if (S.introDone) return;
  S.introDone = true;
  if (_fxRAF) cancelAnimationFrame(_fxRAF);
  const el = $("#intro");
  if (el) { el.classList.add("is-out"); setTimeout(() => el.remove(), 550); }
  if (_introRes) _introRes();
}

function introWait() { return S.introDone ? Promise.resolve() : _introP; }

function introSound() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ac = new AC();
    const t0 = ac.currentTime;
    const master = ac.createGain(); master.gain.value = 0.11;
    const lp = ac.createBiquadFilter(); lp.type = "lowpass";
    lp.frequency.setValueAtTime(180, t0);
    lp.frequency.linearRampToValueAtTime(2600, t0 + 3.4);
    lp.frequency.linearRampToValueAtTime(700, t0 + 7.2);
    lp.Q.value = 0.8;
    lp.connect(master); master.connect(ac.destination);
    [55, 82.41, 110, 164.81, 220, 329.63].forEach((f, i) => {
      const o = ac.createOscillator(); o.type = i < 2 ? "sine" : "triangle";
      o.frequency.value = f; o.detune.value = (i % 2 ? 4 : -4);
      const g = ac.createGain(); g.gain.value = 0.0;
      g.gain.linearRampToValueAtTime(i < 2 ? 1 : 0.4, t0 + 2.6 + i * 0.18);
      g.gain.linearRampToValueAtTime(0.0001, t0 + 7.5);
      o.connect(g); g.connect(lp); o.start(t0); o.stop(t0 + 7.6);
    });
    const bump = ac.createOscillator(); bump.type = "sine";
    bump.frequency.setValueAtTime(70, t0 + 0.4);
    bump.frequency.exponentialRampToValueAtTime(38, t0 + 1.3);
    const bg = ac.createGain();
    bg.gain.setValueAtTime(0.0001, t0 + 0.35);
    bg.gain.linearRampToValueAtTime(1, t0 + 0.5);
    bg.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.6);
    bump.connect(bg); bg.connect(master); bump.start(t0 + 0.35); bump.stop(t0 + 1.7);
    const len = ac.sampleRate * 7.4;
    const nb = ac.createBuffer(1, len, ac.sampleRate);
    for (let i = 0; i < len; i++) nb.getChannelData(0)[i] = (Math.random() * 2 - 1) * Math.pow(i / len, 2.2);
    const ns = ac.createBufferSource(); ns.buffer = nb;
    const nf = ac.createBiquadFilter(); nf.type = "bandpass"; nf.frequency.value = 900; nf.Q.value = 0.9;
    const ng = ac.createGain(); ng.gain.value = 0.16;
    ns.connect(nf); nf.connect(ng); ng.connect(master); ns.start(t0);
  } catch (e) { /* звук — украшение, не критично */ }
}

function startIntro() {
  const el = $("#intro");
  if (!el) return finishIntro();
  introSound();
  $("#inTitle").innerHTML = "FS25 BALANCER".split("").map((ch, i) =>
    `<span style="animation-delay:${(2.35 + i * 0.075).toFixed(2)}s">${ch === " " ? "&nbsp;" : esc(ch)}</span>`).join("");
  introFx();
  const par = $("#inPar");
  el.addEventListener("mousemove", e => {
    const r = el.getBoundingClientRect();
    const dx = (e.clientX - r.width / 2) / r.width, dy = (e.clientY - r.height / 2) / r.height;
    if (par) par.style.transform = `translate3d(${(dx * 16).toFixed(1)}px, ${(dy * 10).toFixed(1)}px, 0) rotateY(${(dx * 5).toFixed(2)}deg) rotateX(${(-dy * 3.5).toFixed(2)}deg)`;
  });
  setTimeout(finishIntro, 7800);
  const skip = () => { finishIntro(); document.removeEventListener("click", skip); document.removeEventListener("keydown", skip); };
  document.addEventListener("click", skip);
  document.addEventListener("keydown", skip);
}

/* Космо-частицы: летящая на камеру глубина (z-buffer), живой параллакс */
function introFx() {
  const cv = $("#inFx");
  if (!cv || !cv.getContext) return;
  const ctx = cv.getContext("2d");
  let W = cv.width = innerWidth, H = cv.height = innerHeight;
  addEventListener("resize", () => { W = cv.width = innerWidth; H = cv.height = innerHeight; });
  const N = 160;
  const pts = Array.from({ length: N }, () => ({ z: Math.random(), a: Math.random() * 6.283, r: 0.15 + Math.random() * 0.9 }));
  const hues = ["140,160,255", "120,220,255", "200,160,255", "255,255,255"];
  const t0 = performance.now();
  const loop = t => {
    if (S.introDone) return;
    const dt = (t - t0) / 1000;
    ctx.clearRect(0, 0, W, H);
    const fade = Math.min(1, dt * 0.8);
    for (let i = 0; i < N; i++) {
      const p = pts[i];
      const z = ((p.z - dt * 0.11) % 1 + 1) % 1;
      const sp = 1 / (z * 6 + 0.12);
      const x = W / 2 + Math.cos(p.a + dt * 0.05) * p.r * W * 0.55 * sp * 0.32;
      const y = H * 0.5 + Math.sin(p.a + dt * 0.05) * p.r * H * 0.45 * sp * 0.32;
      if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;
      const s = Math.max(0.4, 2.6 * sp * 0.5);
      const al = Math.min(0.9, (1 - z) * 0.95) * fade;
      ctx.fillStyle = `rgba(${hues[i % 4]},${al.toFixed(3)})`;
      ctx.beginPath(); ctx.arc(x, y, s, 0, 6.283); ctx.fill();
    }
    _fxRAF = requestAnimationFrame(loop);
  };
  _fxRAF = requestAnimationFrame(loop);
}

/* ── загрузка ── */
async function boot() {
  try {
    await bootInner();
  } catch (e) {
    console.error("boot error", e);
    call("log", "js boot ERR " + String((e && e.message) || e));
    const h = document.querySelector(".boot-hint");
    if (h) h.textContent = "boot error: " + String((e && e.message) || e);
    setTimeout(boot, 1000);
    return;
  }
}

async function bootInner() {
  call("log", "js bootInner start");
  const b = await call("boot");
  if (!b) { setTimeout(boot, 300); return; }
  S.boot = b;
  call("log", "js boot ok");
  $("#verTag").textContent = "v" + b.version;
  $("#dataPath").textContent = b.data_dir;
  $("#modsDir").value = b.config.mods_dir || b.default_mods_dir || "";
  $("#crumbs").textContent = b.config.mods_dir || "папка mods не выбрана";

  fillScanTargets(b.scan_targets, b.config.scan_target);
  applyConfigToUI(b.config);
  renderMultiserial();
  renderMultList();
  renderBrandTabs();
  checkAi();
  (b.items || []).forEach(putItem);
  renderTable();

  setTimeout(async () => {
    await introWait();
    $("#boot").classList.add("is-out");
    $("#shell").hidden = false;
    setTimeout(() => { $("#boot").remove(); }, 600);
    startPoll();
    setInterval(() => { if (!document.hidden) refreshStatuses(); }, 6000);
    call("log", "js shell visible");
    maybeTour();
  }, 450);
}

function fillScanTargets(list, current) {
  $("#scanTarget").innerHTML = (list || []).map(t =>
    `<option value="${t.key}"${t.key === current ? " selected" : ""}>${esc(t.label)}</option>`).join("");
}

function applyConfigToUI(c) {
  $("#place").value = c.k_placeable;
  $("#fieldK").value = c.k_field;
  $("#retroK").value = Math.round(c.k_retro * 100);
  $("#wearK").value = Math.round(c.retro_wear * 100);
  $("#acMod").checked = !!c.ac_mod_installed;
  $("#acConv").checked = !!c.ac_converter;
  $("#rate").value = c.exchange_rate;
  updateCurrencyUI(c);
  $("#adjFields").checked = !!c.adjust_field_prices;
  $("#retroOn").checked = c.retro_enabled !== false;
  paintRetroState(c.retro_enabled !== false);
  $("#maxD").value = c.field_max_distance;
  $("#spread").value = Math.round(c.field_distance_spread * 100);
  $("#backups").checked = !!c.create_backups;
  $("#stopAiClose").checked = c.stop_ai_on_close !== false;
  $("#useAi").checked = !!c.use_local_ai;
  { const t = $("#aiModelCurTxt"); if (t && c.ai_model_name) t.textContent = c.ai_model_name; }
  $("#shopX").value = (c.shop_coordinates.shop || [0, 0])[0];
  $("#shopZ").value = (c.shop_coordinates.shop || [0, 0])[1];
  $("#scanTarget").value = c.scan_target;
  $("#vPlace").textContent = Number(c.k_placeable).toFixed(2);
  $("#vField").textContent = Number(c.k_field).toFixed(2);
  $("#vRetroK").textContent = Math.round(c.k_retro * 100);
  $("#vWearK").textContent = Math.round(c.retro_wear * 100);
  $("#vMaxD").textContent = Number(c.field_max_distance).toFixed(1);
  $("#vSpread").textContent = Math.round(c.field_distance_spread * 100);
  ["place", "fieldK", "retroK", "wearK", "maxD", "spread"].forEach(id => {
    const p = document.getElementById(id).paintRange; if (p) p();
    document.getElementById(id).dispatchEvent(new Event("input"));
  });
}

/* ── очередь событий из Python ── */
let pollTimer = null;
function startPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const evs = await call("poll");
    if (!evs || !evs.length) return;
    for (const ev of evs) handleEvent(ev);
  }, 350);
}

let rowBatch = [], rowBatchTimer = null;
function flushRows() {
  const box = $("#tbody");
  const empty = $("#empty");
  if (empty && rowBatch.length) empty.hidden = true;
  const frag = document.createDocumentFragment();
  for (const it of rowBatch) {
    if (!matches(it)) continue;
    frag.appendChild(rowEl(it));
  }
  box.appendChild(frag);
  rowBatch = [];
  updateStats();
}

function handleEvent(ev) {
  const d = ev.data || {};
  switch (ev.type) {
    case "scan_start":
      setBusy(true, "Сканирование…");
      $("#progress").hidden = false;
      $("#tbody").innerHTML = "";
      S.items.clear(); S.order = [];
      break;
    case "progress":
      $("#progFill").style.width = (d.current / d.total * 100).toFixed(1) + "%";
      $("#progPct").textContent = Math.round(d.current / d.total * 100) + "%";
      $("#progText").textContent = `[${d.current}/${d.total}] ${d.item}`;
      log("Обработка: " + d.item, "busy");
      break;
    case "item":
      putItem(d);
      rowBatch.push(d);
      if (!rowBatchTimer) rowBatchTimer = setTimeout(() => { rowBatchTimer = null; flushRows(); }, 90);
      break;
    case "scan_done":
      flushRows();
      setBusy(false);
      $("#progress").hidden = true;
      if (!d.aborted) chime("ok");
      if (d.stats) S.boot.config.stats = d.stats;
      updateStats();
      log(d.aborted ? "Прервано" : (d.apply ? "Цены записаны в моды" : "Сканирование завершено"),
          d.aborted ? "warn" : "ok");
      toast(d.apply ? "ok" : "info",
        `Найдено ${d.found}: 🚜 ${d.stats.vehicles} · 🏗️ ${d.stats.placeables} · 🌾 ${d.stats.fields}` +
        (d.stats.retro ? ` · 🕰️ ${d.stats.retro}` : "") + ` за ${d.stats.elapsed} с`, 6000);
      if (d.uncertain && d.uncertain.length) {
        toast("warn", `⚠️ ${d.uncertain.length} позиций требуют проверки — см. фильтр «Проверить»`, 7000);
        S.boot.uncertain = d.uncertain;
      }
      break;
    case "recalc_start":
      setBusy(true, "Пересчёт цен…");
      $("#progress").hidden = false;
      break;
    case "applied_start":
      setBusy(true, "Запись в моды…");
      $("#progress").hidden = false;
      break;
    case "recalc_done":
      setBusy(false);
      $("#progress").hidden = true;
      chime("ok");
      flushRows();
      renderTable();
      log(`Цены пересчитаны: ${d.items} позиций за ${d.elapsed} с (без скана)`, "ok");
      toast("ok", `⚡ Пересчитано ${d.items} позиций без повторного сканирования`);
      break;
    case "applied":
      setBusy(false);
      $("#progress").hidden = true;
      if (!d.aborted) chime("ok");
      log(d.aborted ? "Применение прервано" : `Записано в моды: ${d.count} позиций`, d.aborted ? "warn" : "ok");
      toast(d.aborted ? "warn" : "ok", d.aborted ? "Применение прервано" : `💾 Готово: изменено ${d.count} файлов позиций`);
      break;
    case "ai_status":
      checkAi();
      break;
    case "ai_progress":
      log(d.msg || "", "busy");
      if (d.pct != null) {
        const box = $("#aiProgress"); if (!box) break;
        box.hidden = false;
        $("#aiProgBar").style.width = d.pct + "%";
        $("#aiProgPct").textContent = d.pct + "%";
        $("#aiProgSpeed").textContent = d.speed || "";
        $("#aiProgSize").textContent = d.total ? fmtBytes(d.done) + " / " + fmtBytes(d.total) : "";
        $("#aiProgMsg").textContent = d.msg || "";
      }
      break;
    case "ai_done":
      setBusy(false);
      const pb = $("#aiProgress"); if (pb) pb.hidden = true;
      if (!/ошиб|не удал|не удалось/i.test(d.msg || "")) chime("ok"); else chime("err");
      toast("info", d.msg || "Готово", 6000);
      checkAi();
      break;
    case "log":
      log(d.message, "busy");
      break;
    case "error":
      setBusy(false);
      log(d.message, "err");
      toast("err", d.message, 6000);
      break;
  }
}

function putItem(it) { S.items.set(it.unique_key, it); if (!S.order.includes(it.unique_key)) S.order.push(it.unique_key); }
function setBusy(on, text) {
  S.busy = on;
  ["#btnScan", "#btnApply", "#btnRecalc"].forEach(s => { $(s).disabled = !!on; $(s).classList.toggle("is-busy", !!on); });
  $("#btnStop").disabled = !on;
  if (on) log(text || "Работаю…", "busy");
}

async function checkAi() {
  const st = await call("ai_catalog");
  if (!st) return;
  S.ai = st;
  const pill = $("#aiPill");
  pill.className = "ai-pill " + (st.running ? "is-on" : "is-off");
  pill.innerHTML = `<i></i><span>${st.running ? "Ollama активна" : (st.ollama_installed ? "Ollama: служба выключена" : "Ollama не установлена")}</span>`;
  renderAiCatalog();
}

S.aiSort = S.aiSort || "weight";
function sortCatalog(list) {
  const arr = [...list];
  if (S.aiSort === "accuracy") arr.sort((a, b) => (b.rank || 0) - (a.rank || 0) || b.gb - a.gb);
  else arr.sort((a, b) => b.gb - a.gb);
  return arr;
}
function renderAiCatalog() {
  const st = S.ai || { catalog: [], installed: [], running: false, current: "", ollama_installed: false, rec: "" };
  const inst = st.installed || [];
  const has = n => inst.some(x => x === n || x.indexOf(n.split(":")[0] + ":") === 0);
  const cat = sortCatalog(st.catalog || []);
  const recM = cat.find(m => m.name === st.rec);
  const rest = cat.filter(m => m.name !== st.rec);
  const row = (m, pinned) => `
    <div class="ai-i${pinned ? " is-rec" : ""}"><span><b>${esc(m.name)}</b>${pinned ? ' <span class="rec-badge">✓ для твоего железа</span>' : ""}
      <span class="dim">· ${esc(m.size)} · точность ${m.rank || 0}/100 · ${esc(m.desc)}</span></span>
      <span style="display:flex;gap:6px;flex:0 0 auto">
        ${has(m.name) ? `<button class="mini" data-use="${esc(m.name)}">${st.current === m.name ? "✓ выбрана" : "выбрать"}</button>` : ""}
        <button class="mini" data-setup="${esc(m.name)}">${has(m.name) ? "⟳ заново" : "⬇ установить и использовать"}</button>
      </span></div>`;
  $("#aiList").innerHTML =
      `<div class="hw-rec">Железо: ${esc(st.rec_reason || "не определено")}. Рекомендуем <b>${esc(st.rec || "?")}</b> — лучший баланс точности и скорости для задач программы (короткая классификация «страна/ретро» на русском).</div>
      <div class="ai-sort"><span class="dim">Сортировка:</span>
        <button class="mini${S.aiSort === "weight" ? " is-on" : ""}" data-sort="weight">по весу ↓</button>
        <button class="mini${S.aiSort === "accuracy" ? " is-on" : ""}" data-sort="accuracy">по точности ↓</button>
      </div>` +
      (recM ? `<div class="ai-sec">★ Рекомендованная модель</div>${row(recM, true)}
               <div class="ai-sec">Остальные модели (${rest.length})</div>` : "") +
      rest.map(m => row(m, false)).join("") +
      (inst.length ? `<div class="hr"></div><div class="dim sm">Установленные и готовые к работе модели (${inst.length}):</div>` +
        inst.map(n => {
          const ld = (st.loaded || []).find(x => x.name === n || x.name.split(":")[0] === n.split(":")[0]);
          const gpu = ld && ld.size > 0 && ld.vram / ld.size >= 0.5;
          return `
        <div class="ai-i"><span>${esc(n)}${n === st.current ? ' <span class="dim"> · текущая</span>' : ""}
          ${ld ? `<span class="vram-badge ${gpu ? "is-gpu" : "is-cpu"}" title="${gpu ? "Модель в видеопамяти — быстрый отклик" : "Модель в ОЗУ — медленнее, GPU не задействован"}">${gpu ? "⚡ GPU" : "≡ CPU"}${gpu ? " · " + fmtBytes(ld.vram) : ""}</span>` : '<span class="vram-badge is-idle">в покое</span>'}</span>
          <span style="display:flex;gap:6px;flex:0 0 auto">
            <button class="mini" data-use="${esc(n)}">${st.current === n ? "✓ выбрана" : "использовать"}</button>
            <button class="mini danger" data-del="${esc(n)}">🗑 удалить</button>
          </span></div>`; }).join("") : "") +
      `<div class="hr"></div>
      <div class="btnrow"><button class="mini danger" id="btnAiUninstall">🗑 Удалить Ollama из системы</button></div>`;
  renderModelDl(inst, st.current);
  $$("#aiList [data-sort]").forEach(b => b.onclick = () => { S.aiSort = b.dataset.sort; renderAiCatalog(); });
  $$("#aiList [data-use]").forEach(b => b.onclick = async () => {
    const r = await call("set_config", { ai_model_name: b.dataset.use, use_local_ai: true });
    if (r && r.ok) { toast("ok", "Модель выбрана: " + b.dataset.use); S.ai.current = b.dataset.use; renderAiCatalog(); }
  });
  $$("#aiList [data-setup]").forEach(b => b.onclick = () => aiOneClick(b.dataset.setup));
  $$("#aiList [data-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Удалить модель " + b.dataset.del + " с диска?")) return;
    const r = await call("ai_delete", b.dataset.del);
    if (r && r.ok) toast("info", "Удаляю " + b.dataset.del + " — следи за журналом");
  });
  const bu = $("#btnAiUninstall");
  if (bu) bu.onclick = async () => {
    if (!confirm("Удалить Ollama из системы? Запустится тихий деинсталлятор; папка со скачанными моделями (%USERPROFILE%\\.ollama) останется — снесёшь её руками при желании.")) return;
    const r = await call("ai_uninstall");
    if (r && r.ok) toast("info", "Запускаю деинсталляцию Ollama…");
  };
}

/* Дропдаун активной модели: только реально установленные и готовые к работе теги.
   Ручной ввод убран — выбор возможен исключительно из списка, опечатка невозможна. */
function renderModelDl(inst, current) {
  const cur = $("#aiModelCur"), dl = $("#aiModelDl"), txt = $("#aiModelCurTxt");
  if (!cur || !dl) return;
  if (txt) txt.textContent = current || (inst.length ? "выбери модель из списка" : "моделей не установлено — скачай в каталоге ниже");
  cur.classList.toggle("is-off", !inst.length);
  dl.hidden = true;
  if (!inst.length) { dl.innerHTML = ""; return; }
  dl.innerHTML = inst.map(n => `<div class="dl-o${n === current ? " is-on" : ""}" data-q="${esc(n)}">` +
    `${n === current ? "&#10003; " : ""}<b>${esc(n)}</b><em class="dl-o-note">${n === (current || "") ? "активна" : "готов к работе"}</em></div>`).join("");
  $$("#aiModelDl .dl-o").forEach(o => o.onclick = async () => {
    dl.hidden = true;
    const r = await call("set_config", { ai_model_name: o.dataset.q, use_local_ai: true });
    if (r && r.ok) {
      toast("ok", "Модель выбрана: " + o.dataset.q);
      S.boot.config.ai_model_name = o.dataset.q;
      S.ai.current = o.dataset.q;
      renderAiCatalog();
    }
  });
  cur.onclick = e => { e.stopPropagation(); if (inst.length) dl.hidden = !dl.hidden; };
}

async function refreshStatuses() {
  if (!S.ai) return;
  const st = await call("ai_catalog");
  if (!st) return;
  S.ai = Object.assign(S.ai, st);
  if ($("#view-pro").classList.contains("is-on")) renderAiCatalog();
}

async function aiOneClick(model) {
  const st = S.ai || {};
  if (!st.ollama_installed) {
    if (!confirm("Ollama не найдена на этом ПК.\nСкачать и установить её тихо (~1 ГБ), затем загрузить модель " + model + "?\nУстановка идёт в фоне, прогресс — в журнале внизу.")) return;
    const r = await call("ai_install_setup", model);
    if (!r || !r.ok) return toast("err", (r && r.error) || "Не удалось начать установку");
    toast("info", "Устанавливаю Ollama и модель в фоне — следите за журналом");
    return;
  }
  const r = await call("ai_setup", model);
  if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка настройки");
  toast("info", "Модель " + model + ": загрузка/запуск в фоне");
}

/* ── таблица ── */
function matches(it) {
  if (S.filter === "vehicle" && it.item_type !== "vehicle") return false;
  if (S.filter === "placeable" && it.item_type !== "placeable") return false;
  if (S.filter === "field" && it.item_type !== "field") return false;
  if (S.filter === "retro" && !it.is_retro) return false;
  if (S.filter === "review" && !it.needs_review) return false;
  if (S.query) {
    const q = S.query.toLowerCase();
    const hay = `${it.title} ${it.brand} ${it.mod_name} ${it.country} ${it.category_label}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function renderTable() {
  const box = $("#tbody");
  box.innerHTML = "";
  const list = S.order.map(k => S.items.get(k)).filter(Boolean).filter(matches);
  const frag = document.createDocumentFragment();
  list.forEach(it => frag.appendChild(rowEl(it)));
  box.appendChild(frag);
  $("#empty").hidden = list.length > 0;
  $("#shownCount").textContent = `${list.length} из ${S.order.length} строк`;
  updateStats();
}

function priceCell(it) {
  const hasMotors = it.item_type === "vehicle" && it.motor_prices && it.motor_prices.length > 1;
  const manual = it.manual_price != null;
  const cfg = (S.boot && S.boot.config) || {};
  const suffix = cfg.write_direct_rubles === false ? " €" : " ₽";
  return `<div class="c-new">
      <button class="price-btn" data-price="${esc(it.unique_key)}" title="${hasMotors ? "Выбрать комплектацию" : "Задать цену вручную"}">
        <b>${fmt(it.new_price)}</b><span class="cur">${suffix}</span>${hasMotors ? ' <span class="dim">▾</span>' : ""}${manual ? ' <span title="вручную">✎</span>' : ""}
      </button></div>`;
}

function rowEl(it) {
  const tr = document.createElement("div");
  tr.className = "trow" + (it.needs_review ? " is-review" : "") + (it.is_retro ? " is-retro" : "") +
                 (it.manual_price != null ? " is-manual" : "");
  tr.dataset.key = it.unique_key;
  const dist = it.field_distance < 0 ? "?" : fmt1(it.field_distance) + " км";
  const specs = it.item_type === "field"
    ? `${it.field_area > 0 ? fmt1(it.field_area) + " га" : "га ?"} | ${dist}`
    : esc(it.specs_str);
  tr.innerHTML = `
    <span class="c-type" title="${esc(it.item_type)}">${it.type_icon}</span>
    <span class="c-mod" title="${esc(it.mod_name)}">${esc(it.mod_name)}</span>
    <span class="c-name" title="${esc(it.title)}"><b>${esc(it.title)}</b></span>
    <span class="c-brand" title="${esc(it.brand)}">${esc(it.brand)}</span>
    <span class="c-country" data-country="${esc(it.unique_key)}" title="Двойной клик — сменить страну">
      <span class="fl">${it.country_flag}</span><em>${esc(it.country)}</em></span>
    <span class="c-retro"><span class="mini-sw${it.is_retro ? " is-on" : ""}${(S.boot && S.boot.config.retro_enabled === false) ? " is-dis" : ""}" data-retro="${esc(it.unique_key)}"
      title="Ретро: цена × коэффициент ретро"><i></i></span></span>
    <span class="c-specs" data-specs="${esc(it.unique_key)}" title="Клик или двойной клик — правка характеристик и разбор цены">${specs}</span>
    <span class="c-old">${fmt(it.old_price)}</span>
    <span class="c-base">${fmt(it.base_price)}</span>
    ${priceCell(it)}
    <span class="c-rub">${fmt(it.new_price_rub)}</span>
    <span class="c-src" title="${esc(it.ai_reason)} · kC=${fmt2(it.country_mult)} kR=${fmt2(it.retro_mult)}">${esc(it.ai_reason)}</span>`;
  return tr;
}
const fmt1 = v => Number(v || 0).toFixed(1).replace(/\.0$/, "");
function fmtBytes(n) { n = Number(n) || 0;
  if (n >= 2 ** 30) return (n / 2 ** 30).toFixed(2) + " ГБ";
  if (n >= 2 ** 20) return (n / 2 ** 20).toFixed(1) + " МБ";
  return Math.round(n / 1024) + " КБ"; }
const fmt2 = v => Number(v || 0).toFixed(2);

/* делегирование кликов таблицы */
$("#tbody").addEventListener("click", e => {
  const sw = e.target.closest("[data-retro]");
  if (sw) { toggleRetro(sw.dataset.retro, !sw.classList.contains("is-on")); return; }
  const pb = e.target.closest("[data-price]");
  if (pb) { openPriceMenu(pb.dataset.price, pb); return; }
  const sp = e.target.closest("[data-specs]");
  if (sp) { openTtx(sp.dataset.specs); return; }
  const cc = e.target.closest("[data-country]");
  if (cc) { openCountryPicker(cc.dataset.country, cc); return; }
});
$("#tbody").addEventListener("dblclick", e => {
  const cc = e.target.closest("[data-country]");
  if (cc) { openCountryPicker(cc.dataset.country, cc); return; }
  const tr = e.target.closest(".trow");
  if (tr) openTtx(tr.dataset.key);
});

async function toggleRetro(key, on) {
  if (S.boot && S.boot.config.retro_enabled === false) return toast("warn", "Ретро-режим выключен в настройках");
  const r = await call("set_retro", key, on);
  if (!r || !r.ok) { toast("err", (r && r.error) || "Не удалось переключить ретро"); return; }
  S.items.set(key, r.item);
  patchRow(r.item);
  updateStats();
}

async function setCountry(key, country) {
  const r = await call("set_country", key, country);
  if (!r || !r.ok) { toast("err", (r && r.error) || "Ошибка смены страны"); return; }
  S.items.set(key, r.item);
  patchRow(r.item);
  toast("ok", `${r.item.title} → ${r.item.country} (коэф. ${fmt2(r.item.country_mult)})`);
}

function patchRow(it) {
  const tr = $(`.trow[data-key="${CSS.escape(it.unique_key)}"]`);
  if (!tr || !matches(it)) { renderTable(); return; }
  const fresh = rowEl(it);
  tr.className = fresh.className;
  tr.innerHTML = fresh.innerHTML;
}

/* ── выбор страны (анимированный поповер) ── */
let popKey = null;
function openCountryPicker(key, anchor) {
  closePop();
  popKey = key;
  const pop = $("#pop");
  const sel = (S.boot.config.selected_countries || []).length
    ? S.boot.config.selected_countries : S.boot.countries.map(c => c.name);
  const rows = S.boot.countries.filter(c => sel.includes(c.name));
  pop.querySelector(".pop-list").innerHTML = rows.map(c =>
    `<div class="po" data-c="${esc(c.name)}"><span class="fl">${c.flag}</span><span>${esc(c.name)}</span>
     <span class="k">${fmt2(c.mult != null ? c.mult : c.k)}</span></div>`).join("");
  pop.hidden = false;
  positionPop(pop, anchor);
  $$("#pop .po").forEach(el => el.onclick = () => { setCountry(key, el.dataset.c); closePop(); });
  const inp = $("#popSearch");
  inp.value = "";
  inp.oninput = () => {
    const q = inp.value.toLowerCase();
    $$("#pop .po").forEach(el => {
      el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  };
  inp.onkeydown = e => { if (e.key === "Escape") closePop(); };
  setTimeout(() => inp.focus(), 30);
}

function positionPop(pop, anchor) {
  const r = anchor.getBoundingClientRect();
  const w = 240, h = Math.min(320, pop.scrollHeight || 320);
  let top = r.bottom + 6;
  if (top + h > innerHeight - 8) top = Math.max(8, r.top - h - 6);
  pop.style.top = top + "px";
  pop.style.left = Math.min(Math.max(8, r.left), innerWidth - w - 8) + "px";
  pop.style.width = w + "px";
}
function closePop() { $("#pop").hidden = true; popKey = null; }
document.addEventListener("click", e => {
  if (!e.target.closest("#aiModelDl") && !e.target.closest(".dl-cur")) { const dl = $("#aiModelDl"); if (dl) dl.hidden = true; }
  if (!popKey) return;
  if (e.target.closest("#pop") || e.target.closest("[data-country]")) return;
  closePop();
});
window.addEventListener("resize", closePop);
window.addEventListener("scroll", closePop, true);

/* ── меню комплектаций (клик по цене) ── */
let menuKey = null;
async function openPriceMenu(key, anchor) {
  const it = S.items.get(key);
  if (!it) return;
  closeMenu();
  menuKey = key;
  const menu = $("#motorPop");
  let html = `<div class="ctx-h">${it.type_icon} ${esc(it.title)} — базовая ${fmt(it.new_price)}</div>`;
  if (it.item_type === "vehicle" && it.motor_prices && it.motor_prices.length) {
    html += it.motor_prices.map(m =>
      `<div class="ctx-i" data-motor="${m.index}"><span>${esc(m.label)} · ${fmt(m.hp)} л.с.</span><b>${fmt(m.total)}</b></div>`
    ).join("");
    html += `<div class="ctx-sep"></div>`;
  }
  html += `<div class="ctx-i" data-edit="1"><span>✎ Своя цена / правка ТТХ</span></div>`;
  menu.innerHTML = html;
  menu.hidden = false;
  positionPop(menu, anchor);
  $$("#motorPop [data-motor]").forEach(el => el.onclick = () => {
    const idx = Number(el.dataset.motor);
    const m = it.motor_prices.find(x => x.index === idx);
    applyMotorPrice(key, m);
    closeMenu();
  });
  const ed = $("#motorPop [data-edit]");
  if (ed) ed.onclick = () => { closeMenu(); openTtx(key); };
}
function closeMenu() { $("#motorPop").hidden = true; menuKey = null; }
document.addEventListener("click", e => {
  if (!menuKey) return;
  if (e.target.closest("#motorPop") || e.target.closest("[data-price]")) return;
  closeMenu();
});

function applyMotorPrice(key, m) {
  const it = S.items.get(key);
  it.manual_price = m.total;
  it.new_price = m.total;
  toast("info", `Выбрана комплектация «${m.label}»: ${fmt(m.total)} (${fmt(m.hp)} л.с.)`);
  patchRow(it);
  call("set_price", key, m.total);
}

/* ── модалка ТТХ: поля только того класса, что есть в XML + разбор цены ── */
const SPEC_META = {
  hp: { label: "Мощность двигателя", unit: "л.с.", min: 0, max: 3000, step: 1 },
  max_speed: { label: "Максимальная скорость", unit: "км/ч", min: 0, max: 200, step: 1 },
  capacity: { label: "Вместимость", unit: "л", min: 0, max: 500000, step: 50 },
  working_width: { label: "Ширина захвата", unit: "м", min: 0, max: 60, step: 0.1 },
  needed_hp: { label: "Требуемая мощность", unit: "л.с.", min: 0, max: 3000, step: 1 },
  production_cost: { label: "Стоимость производства", unit: "за час", min: 0, max: 100000, step: 10 },
  slots: { label: "Места (слоты/стенды)", unit: "шт", min: 0, max: 512, step: 1, readonly: true },
};
let ttxKey = null;
let ttxTimer = 0;

function specValue(it, k) {
  const map = { hp: it.hp, max_speed: it.max_speed, capacity: it.capacity,
                working_width: it.working_width, needed_hp: it.needed_hp,
                production_cost: it.production_cost, slots: it.slots };
  const v = Number(map[k] || 0);
  return isFinite(v) ? v : 0;
}

function specForm(it) {
  const fields = (it.spec_fields || []).filter(k => SPEC_META[k]);
  const patch = it.spec_patch || {};
  if (!fields.length) {
    return '<div class="dim sm">В файле этой позиции нет редактируемых характеристик — доступна своя цена.</div>';
  }
  return `<div class="ctx-h" style="padding-left:0">Характеристики · только те, что есть в этом файле мода</div>
    <div class="spec-grid">` + fields.map(k => {
      const m = SPEC_META[k];
      const stored = patch[k] != null ? Number(patch[k]) : null;
      const v = stored != null ? stored : specValue(it, k);
      const shown = m.step === 0.1 ? v.toFixed(1) : String(Math.round(v));
      return `<div class="spec-r${stored != null ? " is-patched" : ""}">
        <label>${m.label}${stored != null ? ' <em class="pbadge">изменено</em>' : ""}</label>
        <input type="number" data-spec="${k}" min="${m.min}" max="${m.max}" step="${m.step}" value="${shown}"${m.readonly ? " disabled" : ""}>
        <span class="unit">${m.unit}</span>
      </div>`;
    }).join("") + `</div>
    <div class="dim sm">Правки ложатся в XML мода при «Применить» (с бэкапом в _backup_original_mods). До этого — только предпросмотр.</div>`;
}

function motorsForm(it) {
  if (!it.motors || !it.motors.length) return "";
  return `<div class="ctx-h" style="padding-left:0">Комплектации двигателя</div>
    <div class="mrow head"><label>Название</label><label>Л.С.</label><label>Наценка</label></div>` +
    it.motors.map(m => `
      <div class="mrow">
        <input type="text" data-mlabel="${m.index}" value="${esc(m.label)}">
        <input type="number" data-mhp="${m.index}" min="0" max="2000" step="1" value="${Math.round(m.hp || 0)}">
        <input type="number" data-mprice="${m.index}" min="0" step="100" value="${Math.round(m.price_delta || 0)}">
      </div>`).join("");
}

function priceRow(it) {
  return `<div class="mrow">
      <label>Своя цена (${it.item_type === "vehicle" ? "базовая" : ""})</label>
      <input type="number" id="mPrice" min="50" step="100" value="${it.manual_price != null ? it.manual_price : 0}">
      <span class="dim">0 = авторасчёт</span></div>`;
}

function fieldForm(it) {
  return `${it.needs_review ? `<div class="mnote">⚠️ ${esc(it.ai_reason)} — подтверди или впиши значения вручную.</div>` : ""}
    <div class="spec-grid">
      <div class="spec-r"><label>Площадь</label>
        <input type="number" data-spec="area" id="fArea" min="0" max="5000" step="0.1" value="${it.field_area || 0}">
        <span class="unit">га</span></div>
      <div class="spec-r"><label>Дистанция до магазина</label>
        <input type="number" data-spec="distance" id="fDist" min="-1" max="50" step="0.1" value="${it.field_distance}">
        <span class="unit">км · -1 = неизвестно</span></div>
    </div>
    <div class="mrow">
      <label>Своя цена</label>
      <input type="number" id="mPrice" min="50" step="100" value="${it.manual_price != null ? it.manual_price : 0}">
      <span class="dim">0 = авторасчёт</span></div>
    <div class="dim sm">Координаты поля: ${it.field_coord ? it.field_coord.map(n => Math.round(n)).join(" / ") : "не найдены"}</div>`;
}

function openTtx(key) {
  const it = S.items.get(key);
  if (!it) return;
  ttxKey = key;
  $("#modalTitle").textContent = it.type_icon + " " + it.title + " · " + (it.category_label || it.item_type);
  let html;
  if (it.item_type === "field") {
    html = fieldForm(it);
  } else {
    html = specForm(it) + motorsForm(it) + priceRow(it);
  }
  html += `<div class="bd-wrap">
    <div class="ctx-h" style="padding-left:0">Из чего складывается цена</div>
    <div id="mBreak" class="bd"><div class="dim sm">считаю…</div></div></div>`;
  $("#modalBody").innerHTML = html;
  $("#modal").hidden = false;
  $("#modalSave").dataset.mode = it.item_type === "field" ? "field" : "item";
  $$("#modalBody [data-spec]").forEach(el => {
    if (el.disabled) return;
    el.addEventListener("input", () => schedulePreview());
    el.addEventListener("change", () => schedulePreview());
  });
  schedulePreview(0);
}

function collectPatch() {
  const it = S.items.get(ttxKey);
  if (!it) return {};
  const p = {};
  $$("#modalBody [data-spec]").forEach(el => {
    if (el.disabled) return;
    const k = el.dataset.spec;
    const v = parseFloat(el.value);
    if (!isFinite(v)) return;
    if (k === "area" || k === "distance") { p[k] = v; return; }
    const before = specValue(it, k);
    if (Math.abs(v - before) > 1e-9) p[k] = v;
  });
  return p;
}

function schedulePreview(delay) {
  clearTimeout(ttxTimer);
  ttxTimer = setTimeout(previewNow, delay === 0 ? 0 : 220);
}

async function previewNow() {
  if (!ttxKey) return;
  const r = await call("preview_specs", ttxKey, collectPatch());
  if (!r || !r.ok) return;
  renderBreakdown(r);
}

function renderBreakdown(r) {
  const box = $("#mBreak");
  if (!box) return;
  const diff = Math.round(Number(r.diff || 0));
  const cur = Number(r.current_price || 0);
  const pct = cur ? Math.round(diff / cur * 100) : 0;
  box.innerHTML = (r.lines || []).map(l =>
    `<div class="bd-line${l.hi ? " is-hi" : ""}${l.warn ? " is-warn" : ""}"><span>${esc(l.k)}</span><b>${esc(l.v)}</b></div>`).join("") +
    `<div class="bd-total"><span>Живой предпросмотр</span><b class="${diff > 0 ? "up" : diff < 0 ? "down" : ""}">${fmt(r.auto_price_rub || 0)} ₽` +
    (diff ? ` <i>${diff > 0 ? "+" : "−"}${fmt(Math.abs(diff))} · ${pct > 0 ? "+" : ""}${pct}%</i>` : " <i>без изменений</i>") + `</b></div>` +
    ((r.warnings || []).length ? `<div class="bd-warn">${r.warnings.map(w => "⚠️ " + esc(w)).join("<br>")}</div>` : "");
}

function closeTtx() {
  $("#modal").hidden = true;
  ttxKey = null;
  clearTimeout(ttxTimer);
}
$("#modalCancel").onclick = closeTtx;
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeTtx(); });

$("#modalReset").onclick = async () => {
  if (!ttxKey) return;
  const key = ttxKey;
  const r = await call("reset_specs", key);
  if (!r || !r.ok) return toast("err", (r && r.error) || "Не удалось вернуть значения из файла");
  S.items.set(key, r.item);
  patchRow(r.item);
  updateStats();
  toast("ok", r.note ? "Готово: " + r.note : "Характеристики взяты заново из файла мода");
  openTtx(key);
};

$("#modalSave").onclick = async () => {
  if (!ttxKey) return closeTtx();
  const key = ttxKey;
  const mode = $("#modalSave").dataset.mode;
  const price = clampNum($("#mPrice").value, 0, 1000000000, 0);

  if (mode === "field") {
    const p = collectPatch();
    const a = p.area, d = p.distance;
    if (!isFinite(a)) { markBad("#fArea"); return toast("err", "Площадь должна быть числом 0..5000"); }
    if (!isFinite(d)) { markBad("#fDist"); return toast("err", "Дистанция должна быть числом (-1 = неизвестно)"); }
    const r = await call("patch_field", key, a, d);
    if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка сохранения поля");
    S.items.set(key, r.item);
    if (price > 0) {
      const r2 = await call("set_price", key, price);
      if (r2 && r2.ok) S.items.set(key, r2.item);
    }
    patchRow(S.items.get(key));
    updateStats();
    toast("ok", "Поле обновлено");
    closeTtx();
    return;
  }

  const sp = collectPatch();
  let specsSaved = false;
  if (Object.keys(sp).length) {
    const r = await call("update_specs", key, sp);
    if (!r || !r.ok) return toast("err", (r && r.error) || "Не удалось сохранить ТТХ");
    S.items.set(key, r.item);
    specsSaved = true;
    if ((r.warnings || []).length) toast("warn", r.warnings.join(" · "), 7000);
  }

  if (price > 0) {
    const r = await call("set_price", key, price);
    if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка цены");
    S.items.set(key, r.item);
  } else {
    for (const el of $$("#modalBody [data-mhp]")) {
      const i = Number(el.dataset.mhp);
      const hpEl = $("#modalBody [data-mhp=\"" + i + "\"]");
      const prEl = $("#modalBody [data-mprice=\"" + i + "\"]");
      const lbEl = $("#modalBody [data-mlabel=\"" + i + "\"]");
      const hp = clampNum(hpEl.value, 0, 2000, NaN);
      const dp = clampNum(prEl.value, 0, 1000000000, NaN);
      if (!isFinite(hp)) { markBad("#modalBody [data-mhp=\"" + i + "\"]"); return toast("err", "Л.С. комплектации " + (i + 1) + ": нужно число"); }
      if (!isFinite(dp)) { markBad("#modalBody [data-mprice=\"" + i + "\"]"); return toast("err", "Наценка " + (i + 1) + ": нужно число"); }
      const it = S.items.get(key);
      if (lbEl && it.motors[i]) it.motors[i].label = lbEl.value || it.motors[i].label;
      const r = await call("set_motor", key, i, hp, Math.round(dp));
      if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка ТТХ двигателя");
      S.items.set(key, r.item);
    }
  }
  patchRow(S.items.get(key));
  updateStats();
  toast("ok", specsSaved ? "ТТХ сохранены, цена пересчитана" : "Сохранено");
  if (specsSaved) openTtx(key); else closeTtx();
};

function markBad(sel) {
  const el = $(sel);
  if (!el) return;
  el.classList.add("is-bad");
  setTimeout(() => el.classList.remove("is-bad"), 700);
  el.focus();
}

function updateStats() {
  const all = S.order.map(k => S.items.get(k)).filter(Boolean);
  $("#statItems").innerHTML = `<b>${all.length}</b><i>элементов</i>`;
  $("#statRetro").innerHTML = `<b>${all.filter(i => i.is_retro).length}</b><i>ретро</i>`;
  const el = (S.boot.config.stats && S.boot.config.stats.elapsed) || 0;
  $("#statTime").innerHTML = `<b>${fmt1(el)}</b><i>сек</i>`;
  const shown = $$(".trow").length;
  $("#shownCount").textContent = `${shown} из ${all.length} строк`;
  $("#empty").hidden = shown > 0;
}

/* ── мультиселект стран ── */
let selSet = new Set();
function renderMultiserial() {
  selSet = new Set(S.boot.config.selected_countries || []);
  const ms = $("#countrySelect");
  const paint = () => {
    $("#msTags").innerHTML = [...selSet].slice(0, 14).map(n => {
      const c = S.boot.countries.find(x => x.name === n) || { flag: "🏳" };
      return `<span class="tag">${c.flag} ${esc(n)}<button data-del="${esc(n)}" title="Убрать">×</button></span>`;
    }).join("") + (selSet.size > 14 ? `<span class="tag dim">+${selSet.size - 14}</span>` : "");
    $("#countryCount").textContent = `выбрано ${selSet.size} из ${S.boot.countries.length}`;
    $$("#msTags [data-del]").forEach(b => b.onclick = e => {
      e.stopPropagation(); selSet.delete(b.dataset.del); syncChecks(); paint();
    });
  };
  const groups = {};
  S.boot.countries.forEach(c => (groups[c.group] = groups[c.group] || []).push(c));
  $("#msGroups").innerHTML = Object.entries(groups).map(([g, list]) => `
    <div class="mgroup"><h4>${esc(S.boot.groups[g] || g)} <span>${list.length}</span></h4>
      <div class="mopts">${list.map(c => `
        <label class="mopt"><input type="checkbox" value="${esc(c.name)}" ${selSet.has(c.name) ? "checked" : ""}>
          <span class="fl">${c.flag}</span><span class="nm">${esc(c.name)}</span>
          <span class="k">${fmt2(c.k)}</span></label>`).join("")}</div></div>`).join("");

  $$("#msGroups input[type=checkbox]").forEach(cb => cb.onchange = () => {
    cb.checked ? selSet.add(cb.value) : selSet.delete(cb.value);
    paint();
  });
  $("#msHead").onclick = e => {
    if (e.target.closest("input") || e.target.closest("[data-del]")) return;
    ms.classList.toggle("is-open");
  };
  $("#msSearch").oninput = () => {
    const q = $("#msSearch").value.toLowerCase();
    $$("#msGroups .mopt").forEach(el => {
      el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  };
  $("#msSearch").onclick = e => e.stopPropagation();
  $$("#countrySelect [data-bulk]").forEach(b => b.onclick = e => {
    e.stopPropagation();
    const mode = b.dataset.bulk;
    const all = S.boot.countries;
    let pick = [];
    if (mode === "all") pick = all.map(c => c.name);
    else if (mode === "eu") pick = all.filter(c => c.group === "WEST" || c.group === "CIS").map(c => c.name);
    else if (mode === "cis") pick = all.filter(c => c.group === "CIS").map(c => c.name);
    else if (mode === "top") pick = ["Россия", "СССР", "Беларусь", "Украина", "Казахстан", "Германия", "США", "Франция", "Польша", "Китай", "Япония", "Швеция"];
    else if (mode === "none") pick = [];
    selSet = new Set(pick.filter(n => all.some(c => c.name === n)));
    syncChecks(); paint();
  });
  paint();
}
function syncChecks() {
  $$("#msGroups input[type=checkbox]").forEach(cb => { cb.checked = selSet.has(cb.value); });
}

$("#btnSaveCountries").onclick = async () => {
  if (!selSet.size) return toast("warn", "Выбери хотя бы одну страну");
  const mults = {};
  $$("#multList [data-mult]").forEach(i => { const v = parseFloat(i.value); if (isFinite(v)) mults[i.dataset.mult] = v; });
  const r = await call("select_countries", [...selSet], mults);
  if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка сохранения стран");
  S.boot.config = r.config || S.boot.config;
  renderMultList();
  toast("ok", `Пул стран обновлён: ${r.selected.length}${r.recalc ? " — цены пересчитаны" : ""}`);
};

/* ── коэффициенты стран: личный множитель каждой выбранной страны ──
   (пришёл на смену глобальному коэффициенту сложности) */
S.multAll = S.multAll || false;
S.multQ = S.multQ || "";
const clampK = v => { const n = Number(v); return isFinite(n) ? Math.min(10, Math.max(0.05, n)) : 1; };

function renderMultList() {
  const cfg = S.boot.config || {};
  const sel = new Set(cfg.selected_countries || []);
  const mult = cfg.country_multipliers || {};
  const q = (S.multQ || "").trim().toLowerCase();
  const rows = (S.boot.countries || []).slice()
    .filter(c => S.multAll || sel.has(c.name) || (q && c.name.toLowerCase().includes(q)))
    .sort((a, b) => (sel.has(b.name) ? 1 : 0) - (sel.has(a.name) ? 1 : 0) ||
                   a.name.localeCompare(b.name, "ru"));
  const list = $("#multList");
  if (!rows.length) {
    list.innerHTML = '<div class="dim sm">Страны не выбраны — отметь нужные в мультиселекте выше и сохрани пул, их коэффициенты появятся здесь.</div>';
  } else {
    list.innerHTML = rows.map(c => {
      const on = sel.has(c.name);
      const v = clampK(mult[c.name] != null ? mult[c.name] : c.k);
      return `
    <div class="mult-i${on ? "" : " is-off"}" data-row="${esc(c.name)}">
      <span class="nm"><span>${c.flag}</span><span>${esc(c.name)}</span>${on ? "" : ' <em class="dim">вне пула</em>'}</span>
      <input type="range" data-mult="${esc(c.name)}" min="0.05" max="10" step="0.05" value="${v}"${on ? "" : " disabled"}>
      <input type="number" class="mult-num" data-muldn="${esc(c.name)}" min="0.05" max="10" step="0.05" value="${v.toFixed(2)}"${on ? "" : " disabled"}>
      <button class="mini" data-muldef="${esc(c.name)}" title="Дефолт страны ${clampK(c.k).toFixed(2)}×"${on ? "" : " disabled"}>↺</button>
    </div>`;
    }).join("");
  }
  const bar = (rng, v) => {
    const min = +rng.min, max = +rng.max;
    rng.style.setProperty("--fill", ((v - min) / (max - min) * 100).toFixed(1) + "%");
  };
  $$("#multList [data-mult]").forEach(rng => {
    const row = rng.closest(".mult-i"), num = row.querySelector(".mult-num");
    bar(rng, +rng.value);
    rng.addEventListener("input", () => { const v = clampK(rng.value); num.value = v.toFixed(2); bar(rng, v); });
    num.addEventListener("input", () => { const v = clampK(num.value); rng.value = v; bar(rng, v); });
    num.addEventListener("change", () => {
      const raw = parseFloat(num.value);
      if (!isFinite(raw)) { num.classList.add("is-bad"); toast("warn", "Коэффициент — число 0.05…10"); return; }
      num.classList.remove("is-bad");
      const v = clampK(raw); num.value = v.toFixed(2); rng.value = v; bar(rng, v);
    });
  });
  $$("#multList [data-muldef]").forEach(b => b.onclick = () => {
    const c = (S.boot.countries || []).find(x => x.name === b.dataset.muldef);
    if (!c) return;
    const row = b.closest(".mult-i"), rng = row.querySelector("[data-mult]"), num = row.querySelector(".mult-num");
    const v = clampK(c.k); rng.value = v; num.value = v.toFixed(2); bar(rng, v);
    toast("info", `${c.name}: дефолт ${v.toFixed(2)}× — не забудь «Сохранить коэффициенты»`);
  });
  const allBtn = $("#btnMultAll");
  if (allBtn) {
    allBtn.textContent = S.multAll ? "Только выбранные" : "Показать все страны";
    allBtn.onclick = () => { S.multAll = !S.multAll; renderMultList(); };
  }
  const defBtn = $("#btnMultDefault");
  if (defBtn) defBtn.onclick = () => {
    $$("#multList [data-muldef]").forEach(b => b.click());
    toast("info", "Дефолты проставлены — сохрани коэффициенты");
  };
  const si = $("#multSearch");
  if (si && !si._wired) { si._wired = true; si.addEventListener("input", () => { S.multQ = si.value; renderMultList(); }); }
}

/* ── валютный блок: что именно ляжет в <price> файла мода ── */
function updateCurrencyUI(c) {
  c = c || (S.boot && S.boot.config) || {};
  const direct = c.write_direct_rubles !== false;   // нет мода ИЛИ выключен конвертер
  const rate = Number(c.exchange_rate || 0);
  const ac = $("#acConv");
  if (ac) {
    ac.disabled = !c.ac_mod_installed;
    ac.closest(".switch").classList.toggle("is-dis", !c.ac_mod_installed);
  }
  const badge = $("#curBadge");
  if (badge) {
    badge.textContent = direct ? "пишем ₽" : "пишем € → игра переведёт в ₽";
    badge.className = "cur-badge " + (direct ? "is-rub" : "is-eur");
  }
  const rs = $("#rateSrc");
  if (rs) rs.textContent = c.ac_rate_auto ? "— авто из currencies.xml" : "— вручную";
  const note = $("#curNote");
  if (note) note.innerHTML = direct
    ? `В <code>&lt;price&gt;</code> файла мода ложится <b>сумма в рублях</b>: база (EUR-алгоритм) × ${fmt2(rate)}.
       ${c.ac_mod_installed ? "Мод стоит, но конвертер в игре выключен — значит игра показывает ровно то число, что в файле."
                            : "Мод Additional Currencies не нужен — игра отобразит это число в своей валюте."}`
    : `Мод Additional Currencies стоит <b>и</b> конвертер включён: в файл пишем <b>€-базу</b>, а игра сама домножит её на ${fmt2(rate)} и покажет рубли.
       Писать в этом режиме готовые рубли — двойная конвертация, цены раздует в ${Math.round(rate)} раз.`;
  const thN = $("#thNew"), thR = $("#thRub");
  if (thN) thN.textContent = direct ? "Новая ₽" : "Новая €";
  if (thR) thR.textContent = direct ? "₽ итог" : "₽ (домножит игра)";
}

/* ── слайдеры настроек ── */
function bindSettings() {
  const map = [
    ["place", "#vPlace", v => Number(v).toFixed(2), "k_placeable"],
    ["fieldK", "#vField", v => Number(v).toFixed(2), "k_field"],
    ["retroK", "#vRetroK", v => Math.round(v), "k_retro"],
    ["wearK", "#vWearK", v => Math.round(v), "retro_wear"],
    ["maxD", "#vMaxD", v => Number(v).toFixed(1), "field_max_distance"],
    ["spread", "#vSpread", v => Math.round(v), "field_distance_spread"],
  ];
  for (const [id, out, fmtFn, key] of map) {
    const el = document.getElementById(id);
    const paint = bindRange(el, $(out), null, fmtFn);
    el.paintRange = paint;
    el.addEventListener("change", async () => {
      let v = parseFloat(el.value);
      if (!isFinite(v)) return toast("err", "Некорректное значение слайдера");
      if (key === "k_retro" || key === "retro_wear" || key === "field_distance_spread") v = v / 100;
      const r = await call("set_config", { [key]: v });
      if (r && r.ok) { S.boot.config = r.config; if (key.startsWith("field") || key === "adjust") drawCurve(); }
      else toast("err", (r && r.error) || "Не сохранено");
    });
  }

  const sw = [
    ["acMod", "ac_mod_installed"], ["acConv", "ac_converter"], ["adjFields", "adjust_field_prices"],
    ["backups", "create_backups"], ["useAi", "use_local_ai"], ["retroOn", "retro_enabled"],
    ["stopAiClose", "stop_ai_on_close"],
  ];
  for (const [id, key] of sw) {
    document.getElementById(id).addEventListener("change", async e => {
      const r = await call("set_config", { [key]: e.target.checked });
      if (r && r.ok) {
        S.boot.config = r.config;
        if (key === "adjust_field_prices") drawCurve();
        if (key === "retro_enabled") paintRetroState(e.target.checked);
        if (key === "retro_enabled" && S.order.length) guard(call("recalc"));
        if (key === "ac_mod_installed" || key === "ac_converter") {
          updateCurrencyUI(r.config);
          if (S.order.length) guard(call("recalc"));   // режим записи поменял все цены
        }
      }
      toast(e.target.checked ? "ok" : "info", labelOf(key) + (e.target.checked ? " — вкл" : " — выкл"));
    });
  }
  $("#rate").addEventListener("change", async e => {
    const v = clampNum(e.target.value, 1, 100000, NaN);
    if (!isFinite(v)) { markBad("#rate"); return toast("err", "Курс — число от 1 до 100000"); }
    // ручное значение отключает автоподстановку курса из мода
    const r = await call("set_config", { exchange_rate: v, ac_rate_auto: false });
    if (r && r.ok) {
      S.boot.config = r.config; updateCurrencyUI(r.config);
      toast("ok", `Курс сохранён: ${v} ₽ за 1 €`);
      if (S.order.length) guard(call("recalc"));
    }
  });
  $("#btnAcDetect").onclick = async () => {
    const r = await call("detect_currency");
    if (!r || !r.ok) return toast("err", (r && r.error) || "Не удалось проверить папку mods");
    S.boot.config = r.config; applyConfigToUI(r.config); updateCurrencyUI(r.config);
    const i = r.info || {};
    toast(i.found ? "ok" : "warn",
      i.found ? `💱 Найден ${i.mod}` + (i.rate ? ` — курс ${fmt2(i.rate)} ₽ за 1 €` + (r.config.ac_rate_auto ? " (из currencies.xml)" : " (твой ручной курс)") : " — рублёвый курс в мода не найден, задай вручную")
              : "Мод Additional Currencies в папке mods не найден — цены пишутся в рублях напрямую", 6500);
  };
  ["shopX", "shopZ"].forEach(id => document.getElementById(id).addEventListener("change", async () => {
    const x = clampNum($("#shopX").value, -100000, 100000, NaN);
    const z = clampNum($("#shopZ").value, -100000, 100000, NaN);
    if (!isFinite(x) || !isFinite(z)) { markBad("#" + (isFinite(x) ? "shopZ" : "shopX")); return toast("err", "Координаты — числа в метрах"); }
    const r = await call("set_config", { shop_x: x, shop_z: z });
    if (r && r.ok) { S.boot.config = r.config; toast("ok", `Магазин: X=${x}, Z=${z}`); drawCurve(); }
  }));

  $("#modsDir").addEventListener("change", async e => {
    const r = await call("set_config", { mods_dir: e.target.value });
    if (r && r.ok) { S.boot.config = r.config; $("#crumbs").textContent = r.config.mods_dir; toast("ok", "Папка сохранена"); }
    else toast("err", "Папка не найдена — проверь путь");
  });
  $("#btnChoose").onclick = async () => {
    const r = await call("choose_dir");
    if (r && r.ok) { $("#modsDir").value = r.path; $("#crumbs").textContent = r.path; S.boot.config.mods_dir = r.path; }
  };
  $("#scanTarget").addEventListener("change", async e => {
    const r = await call("set_config", { scan_target: e.target.value });
    if (r && r.ok) S.boot.config = r.config;
  });
  $("#btnSavePrices").onclick = () => {
    const mults = {};
    $$("#multList [data-mult]").forEach(i => {
      if (i.disabled) return;
      const v = parseFloat(i.value);
      if (!isFinite(v)) { toast("err", `Коэффициент ${i.dataset.mult}: нужно число`); return; }
      mults[i.dataset.mult] = Math.min(10, Math.max(0.05, v));
    });
    call("select_countries", [...selSet], mults).then(r => {
      if (r && r.ok) {
        S.boot.config = r.config || S.boot.config;
        toast("ok", `Коэффициенты сохранены (${Object.keys(mults).length} стран)` + (r.recalc ? " — цены пересчитаны" : ""));
        renderMultList();
      } else toast("err", (r && r.error) || "Не сохранено");
    });
  };
  $("#btnSaveFields").onclick = () => { drawCurve(); toast("ok", "Настройки полей сохранены"); };
}
function labelOf(key) {
  return { ac_mod_installed: "Мод Additional Currencies", ac_converter: "Конвертер валют в игре",
           adjust_field_prices: "Изменять цены на поля",
           create_backups: "Резервные копии", use_local_ai: "Определять страну через ИИ",
           retro_enabled: "Режим «Ретро»" }[key] || key;
}
function paintRetroState(on) {
  const card = $("#retroCard");
  if (card) card.classList.toggle("is-off", !on);
  ["retroK", "wearK"].forEach(id => { const el = document.getElementById(id); if (el) el.disabled = !on; });
  $$(".mini-sw").forEach(el => el.classList.toggle("is-dis", !on));
}

/* ── график зависимости цены поля от расстояния ── */
function drawCurve() {
  const cv = $("#curve"); if (!cv) return;
  const ctx = cv.getContext("2d");
  const W = cv.width = cv.clientWidth * 2, H = cv.height = 340;
  ctx.clearRect(0, 0, W, H);
  const c = S.boot.config, adj = c.adjust_field_prices;
  const maxD = +c.field_max_distance || 3, spread = (+c.field_distance_spread || 0) ;
  const area = 25, base = Math.max(1500, area * 4800);
  const yMax = adj ? base * (1 + spread) : base, yMin = adj ? base : base;
  const pad = 44, gw = W - pad * 2, gh = H - pad * 2;

  ctx.strokeStyle = "rgba(120,130,160,.16)"; ctx.lineWidth = 1.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad + gh * i / 4;
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke();
  }
  ctx.beginPath();
  for (let i = 0; i <= 100; i++) {
    const d = maxD * i / 100;
    const m = adj ? (1 + spread * (1 - Math.min(1, d / maxD))) : 1;
    const y = pad + gh * (1 - (base * m - base * (adj ? 1 : 1)) / ((adj ? base * spread : 1) || 1) * (adj ? 1 : 0) - (adj ? 0 : .5));
    const yy = adj ? pad + gh * (1 - (m - 1) / (spread || 1)) : pad + gh * .5;
    ctx[i ? "lineTo" : "moveTo"](pad + gw * i / 100, yy);
  }
  const grad = ctx.createLinearGradient(0, 0, W, 0);
  grad.addColorStop(0, "#22c55e"); grad.addColorStop(1, "#6366f1");
  ctx.strokeStyle = adj ? grad : "#3a4162"; ctx.lineWidth = 3; ctx.stroke();

  ctx.fillStyle = "#7a819b"; ctx.font = "22px Segoe UI";
  ctx.fillText("0 км", pad - 8, H - 12);
  ctx.fillText(maxD.toFixed(1) + " км", W - pad - 70, H - 12);
  if (adj) {
    ctx.fillStyle = "#22c55e"; ctx.fillText("×" + (1 + spread).toFixed(2), pad + 6, pad + 24);
    ctx.fillStyle = "#6366f1"; ctx.fillText("×1.00", W - pad - 60, pad + gh - 6);
  } else {
    ctx.fillStyle = "#8b93ad"; ctx.fillText("корректировка выключена — цена не зависит от расстояния", pad + 10, pad + gh / 2);
  }
}

/* ── PRO ── */
function renderBrandTabs() {
  const pro = S.boot.pro;
  $("#prompt").value = pro.custom_prompt || "";
  const sel = new Set(S.boot.config.selected_countries || []);
  const names = [...sel].filter(n => (pro.country_brands || {})[n]);
  const ordered = names.length ? names : Object.keys(pro.country_brands || {});
  if (!S.brandTab || !ordered.includes(S.brandTab)) S.brandTab = ordered[0] || null;
  $("#brandTabs").innerHTML = ordered.map(n => {
    const c = S.boot.countries.find(x => x.name === n) || { flag: "🏳" };
    const cnt = ((pro.country_brands || {})[n] || []).length;
    return `<button class="bt${n === S.brandTab ? " is-on" : ""}" data-tab="${esc(n)}">${c.flag} ${esc(n)}<em>${cnt}</em></button>`;
  }).join("");
  $$("#brandTabs [data-tab]").forEach(b => b.onclick = () => {
    S.brandTab = b.dataset.tab;
    $$("#brandTabs .bt").forEach(x => x.classList.toggle("is-on", x === b));
    $("#brandList").value = ((S.boot.pro.country_brands || {})[S.brandTab] || []).join("\n");
  });
  if (S.brandTab) $("#brandList").value = ((pro.country_brands || {})[S.brandTab] || []).join("\n");
}

$("#btnSavePro").onclick = async () => {
  const brands = JSON.parse(JSON.stringify(S.boot.pro.country_brands || {}));
  if (S.brandTab) brands[S.brandTab] = $("#brandList").value.split(/[\n,]/).map(x => x.trim().toLowerCase()).filter(Boolean);
  const r = await call("save_pro", $("#prompt").value, brands);
  if (r && r.ok) { S.boot.pro = { custom_prompt: $("#prompt").value, country_brands: brands }; renderBrandTabs(); toast("ok", "PRO-настройки сохранены"); }
  else toast("err", "Не сохранено");
};
$("#btnPromptReset").onclick = async () => {
  const r = await call("boot");
  if (r) { $("#prompt").value = r.pro.default_prompt_default || r.pro.custom_prompt; S.boot.pro = r.pro; toast("info", "Промпт сброшен к дефолту"); }
};
$("#btnClearMem").onclick = async () => {
  if (!confirm("Сбросить память брендов и кэш скана? Позиции снова будут определяться с нуля.")) return;
  const r = await call("clear_memory");
  if (r && r.ok) toast("ok", "Память очищена");
};
$("#btnAiStart").onclick = async () => { const r = await call("ai_start"); toast(r && r.ok ? "ok" : "warn", r && r.ok ? "Служба ИИ запущена" : "Не удалось запустить Ollama"); checkAi(); };
$("#btnAiStop").onclick = async () => { await call("ai_stop"); toast("info", "Служба ИИ остановлена"); checkAi(); };
$("#btnAiRefresh").onclick = async () => { await checkAi(); toast("info", "Список готовых моделей обновлён"); };

/* ── кнопки верхней панели ── */
$("#btnScan").onclick = () => guard(call("scan", false));
$("#btnApply").onclick = () => { if (confirm("Записать рассчитанные цены в файлы модов? Будут созданы резервные копии.")) guard(call("apply")); };
$("#btnRecalc").onclick = async () => {
  if (!S.order.length) return toast("warn", "Сначала выполни сканирование");
  const b = $("#btnRecalc");
  b.classList.add("is-busy");
  await new Promise(r => setTimeout(r, 260));
  guard(call("recalc"));
};
$("#btnStop").onclick = () => call("stop");
function guard(p) {
  p.then(r => {
    if (!r) return;
    if (r.ok) setBusy(true, "Подготовка…");
    else { setBusy(false); toast("err", r.error || "Ошибка"); }
  });
}
$("#btnExportProfile").onclick = async () => {
  const r = await call("choose_dir");
  if (!r || !r.ok) return;
  const exp = await call("export_profile", r.path);
  toast(exp && exp.ok ? "ok" : "err", exp && exp.ok ? "Профиль выгружен: " + exp.path : "Экспорт не удался");
};

/* ── фильтры/поиск ── */
$$("#filters .chip").forEach(c => c.onclick = () => {
  S.filter = c.dataset.f;
  $$("#filters .chip").forEach(x => x.classList.toggle("is-on", x === c));
  renderTable();
});
$("#search").addEventListener("input", debounce(e => { S.query = e.target.value.trim(); renderTable(); }, 220));

/* ── прокрутка колесом: WebView2 теряет wheel на вложенных скроллах.
   Крутим ближайший реально прокручиваемый предка; на его границе
   передаём ход родителю (иначе список ловит колесо и не отпускает) ── */
function canScroll(el, dy) {
  if (!el || el === document.documentElement || el === document.body) return false;
  const oy = getComputedStyle(el).overflowY;
  if ((oy !== "auto" && oy !== "scroll") || el.scrollHeight <= el.clientHeight + 4) return false;
  if (dy < 0 && el.scrollTop <= 0) return false;
  if (dy > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 1.5) return false;
  return true;
}
document.addEventListener("wheel", e => {
  let el = e.target instanceof Element ? e.target : (e.target && e.target.parentElement);
  while (el && el !== document.body) {
    if (canScroll(el, e.deltaY)) { el.scrollTop += e.deltaY; e.preventDefault(); return; }
    el = el.parentElement;
  }
  const v = $(".view.is-on");
  if (canScroll(v, e.deltaY)) { v.scrollTop += e.deltaY; e.preventDefault(); return; }
  const se = document.scrollingElement || document.documentElement;
  if (se && se.scrollHeight > se.clientHeight + 4) { se.scrollTop += e.deltaY; e.preventDefault(); }
}, { passive: false });

/* ── heist-эффект кнопок ── */
document.addEventListener("mousemove", e => {
  const b = e.target.closest(".btn");
  if (!b) return;
  const r = b.getBoundingClientRect();
  b.style.setProperty("--mx", (e.clientX - r.left) + "px");
  b.style.setProperty("--my", (e.clientY - r.top) + "px");
});

/* ── интерактивное обучение (пошаговый тур с подсветкой) ── */
const TOUR = [
  { sel: "#btnScan", title: "Сканирование",
    text: "Укажи папку mods и нажми «Сканировать». Программа прочитает modDesc.xml и XML техники, зданий и полей — файлы при этом не меняются." },
  { sel: "#btnRecalc", title: "Обновить цены",
    text: "Кнопка пересчитывает цены по текущим коэффициентам и ретро-настройкам БЕЗ повторного сканирования — изменения видны мгновенно." },
  { sel: '[data-view="countries"]', title: "Пул стран",
    text: "Выбери страны, которые вообще допустимы. ИИ и словари брендов не выйдут за этот пул: всё сомнительное попадёт в фильтр «Проверить». Ниже — отдельный коэффициент цены для каждой выбранной страны: он заменил прежний глобальный масштаб сложности." },
  { sel: ".thead .c-country", title: "Смена региона",
    text: "Двойной клик по стране в строке — анимированный список стран. Выбор запоминается для бренда и сразу пересчитывает цену." },
  { sel: ".thead .c-retro", title: "Ретро-тумблер",
    text: "Переключатель в строке делает технику ретро: цена умножается на коэффициент ретро, а dailyUpkeep — на коэффициент износа." },
  { sel: ".thead .c-new", title: "Комплектации",
    text: "Клик по цене откроет список комплектаций двигателя с разными л.с. и ценами; «Своя цена» — ручной ввод." },
  { sel: ".thead .c-specs", title: "Правка характеристик",
    text: "Клик (или двойной клик) по колонке «Хар-ки» открывает редактор: показаны только те характеристики, которые реально есть в XML этой позиции — л.с. и макс. скорость у техники, вместимость, места и производство у здания, площадь и дистанция у поля. Справа внизу живой разбор: база → коэффициент страны → ретро → итог в ₽, и дельта видна ещё до сохранения." },
  { sel: '[data-view="fields"]', title: "Поля и расстояние",
    text: "Включи «Изменять цены на поля» и укажи координаты магазина: чем ближе поле, тем дороже. Если площадь или дистанция не определились — строка попадёт на ручное подтверждение." },
  { sel: "#btnApply", title: "Применить",
    text: "Только после «Применить» программа перепишет файлы модов. Резервные копии складываются в _backup_original_mods." },
  { sel: "#curBadge", view: "prices", title: "Валюта и рубли",
    text: "Программа всегда считает цену в рублях. Переключатели решают, что ляжет в файл мода: без мода Additional Currencies (или с выключенным конвертером) — сразу рубли; если мод стоит и конвертер включён — база в €, а игра сама домножит её на курс мода. Кнопка «Найти мода и курс автоматически» читает currencies.xml прямо из папки mods." },
  { sel: "#aiModelCur", view: "pro", title: "Локальный ИИ",
    text: "Клик по плашке «Активная модель» — выпадающий список только тех моделей, что уже скачаны и готовы к работе. Ручного ввода больше нет: выбрать можно реально установленное. Новые модели ставятся кнопкой «установить и использовать» в каталоге ниже, там видно %, скорость и статус ⚡ GPU / ≡ CPU." },
];
let tourHole = null;

function ensureHole() {
  if (tourHole) return tourHole;
  tourHole = document.createElement("div");
  tourHole.className = "hole";
  tourHole.hidden = true;
  document.body.appendChild(tourHole);
  return tourHole;
}

function maybeTour() {
  // Обучение обязательно при каждом запуске, пока пользователь не поставил
  // галочку "больше не показывать" (fs25_tour_done больше не используется)
  try { localStorage.removeItem("fs25_tour_done"); } catch (e) {}
  let never = "";
  try { never = localStorage.getItem("fs25_tour_never"); } catch (e) {}
  if (!never) startTour();
}

function startTour() {
  S.tourStep = 0;
  const t = ensureTourEl();
  t.hidden = false;
  placeTour();
}

function ensureTourEl() {
  let t = $("#tour");
  if (t) return t;
  t = document.createElement("div");
  t.className = "tour"; t.id = "tour";
  t.innerHTML = `<h4 id="tourTitle"></h4><p id="tourText"></p>
    <label class="tour-never" title="Тур больше не будет открываться автоматически"><input type="checkbox" id="tourNever"> больше не показывать</label>
    <div class="tour-foot"><div class="tour-dots" id="tourDots"></div>
      <button class="tour-skip" id="tourSkip">Пропустить</button>
      <button class="btn btn-accent sm" id="tourNext">Далее</button></div>`;
  document.body.appendChild(t);
  $("#tourNext").onclick = () => { S.tourStep++; placeTour(); };
  $("#tourSkip").onclick = endTour;
  return t;
}

function placeTour() {
  const t = $("#tour"), hole = ensureHole();
  if (S.tourStep < 0 || S.tourStep >= TOUR.length) return endTour();
  const step = TOUR[S.tourStep];
  // showView("scan") сам дёргает placeTour() — переключаем вьюху только если
  // она реально отличается, иначе взаимная рекурсия showView<->placeTour.
  if (step.sel.startsWith(".thead") && !$("#view-scan").classList.contains("is-on")) {
    showView("scan");
  }
  // шаг из другой вкладки: сначала сделать её активной, иначе rect = 0 и рамка улетает в угол
  if (step.view && !$("#view-" + step.view).classList.contains("is-on")) showView(step.view);
  const el = $(step.sel);
  if (!el || !el.getBoundingClientRect().width) { S.tourStep++; return placeTour(); }
  if (step.view) el.scrollIntoView({ block: "center" });
  $("#tourTitle").textContent = "Шаг " + (S.tourStep + 1) + " из " + TOUR.length + " · " + step.title;
  $("#tourText").textContent = step.text;
  $("#tourDots").innerHTML = TOUR.map((_, i) => `<i class="${i === S.tourStep ? "is-on" : ""}"></i>`).join("");
  $("#tourNext").textContent = S.tourStep === TOUR.length - 1 ? "Готово" : "Далее";

  const r = el.getBoundingClientRect();
  hole.hidden = false;
  hole.style.left = (r.left - 6) + "px";
  hole.style.top = (r.top - 6) + "px";
  hole.style.width = (r.width + 12) + "px";
  hole.style.height = (r.height + 12) + "px";

  const tw = t.offsetWidth || 320, th = t.offsetHeight || 160;
  let top = r.bottom + 14, left = Math.min(Math.max(12, r.left), innerWidth - tw - 12);
  if (top + th > innerHeight - 12) top = Math.max(12, r.top - th - 14);
  t.style.left = left + "px"; t.style.top = top + "px";
}

function endTour() {
  S.tourStep = -1;
  const t = $("#tour"); if (t) t.hidden = true;
  const hole = ensureHole(); hole.hidden = true;
  const cb = $("#tourNever");
  if (cb && cb.checked) {
    try { localStorage.setItem("fs25_tour_never", "1"); } catch (e) {}
    toast("ok", "Понял, больше не показывать. Вернуть тур — кнопка «? Обучение».");
  } else {
    toast("info", "Обучение завершено. Открыть заново — кнопка «? Обучение».");
  }
}
window.addEventListener("resize", () => { if (S.tourStep >= 0) placeTour(); });

/* ── история обновлений ── */
const CHANGELOG = [
  { v: "15.4", date: "2026-10-26", title: "Редактор ТТХ по классам", items: [
    "Двойной клик по строке или «Хар-ки» открывает редактор только тех параметров, что реально есть в XML этого мода: техника, здание/силос, производство",
    "Техника: мощность, максимальная скорость, ширина захвата, объём бака, требуемая мощность; правка л.с. конкретной комплектации двигателя",
    "Здания: вместимость (в т.ч. по узлам), стоимость, производство; слоты показаны как read-only, чтобы не ломать структуру мода",
    "Живой разбор цены: база по классу и размеру → коэф. страны → ретро → ₽-итог, с дельтой «что изменится» ещё до сохранения",
    "Кнопка ↺ «Из файла» — мгновенный сброс всех ручных правок к оригинальным значениям мода",
    "При выходе из программы Ollama и все загруженные модели останавливаются автоматически (переключатель в настройках)",
    "Кнопки «? Обучение» и «v… история» перенесены в шапку: теперь видны при любом размере окна",
  ]},
  { v: "15.0", date: "2026-10-25", title: "Premium Web Edition", items: [
    "Полностью новый интерфейс: стеклянная тёмная тема, анимации, плавные дропдауны (PyWebView + HTML/CSS/JS)",
    "Кнопка «Обновить цены»: пересчёт по коэффициентам без повторного сканирования",
    "База 177 стран мира + СССР, мультиселект с тегами и группами",
    "Смена региона техники двойным кликом, анимированный поиск по странам",
    "Ретро: ручной тумблер в строке, коэффициент цены и коэффициент износа (0–100%)",
    "Несколько комплектаций двигателя у техники, выбор цены из меню, редактор л.с./наценки",
    "PRO: списки брендов для каждой страны + редактируемый системный промпт ИИ",
    "Поля: цена зависит от расстояния до магазина, радиус и сила влияния, график",
    "Ручной ввод площади/дистанции поля; неопознанные значения помечаются «Проверить»",
    "Интерактивное обучение для новых пользователей и журнал версий",
    "ИИ в один клик: каталог из 12 моделей + mistral, рекомендация по железу",
    "Удаление скачанных моделей и деинсталляция Ollama из программы",
    "Общий выключатель режима «Ретро»",
    "Фиксы: колесо мыши, кэш WebView2, обучающий тур, ложный тост о мосте",
    "Кинематографичная заставка в стиле Ubisoft (клик — пропустить)",
    "Фиксы: галочка тура врезана в карточку, достижимая прокрутка до низа",
    "Один общий скролл на вкладке, заметная переливающаяся пульсация рекомендации",
    "Заставка уровня кинотитров: космо-частицы, неоновый пол, орбита, глитч букв, вспышка-кат",
    "Звук заставки: мягкий кинематографичный эмбиент (синтез, без файлов)",
    "Прогресс скачивания моделей: %, скорость МБ/с, размер; дропдаун только установленных; статус GPU/CPU/VRAM по каждой модели",
    "Активная модель — выпадающий список готовых к работе моделей вместо ручного ввода",
    "Единый анимированный прогресс-бар для скана, пересчёта, записи в моды, скачивания и установки; мягкий звук в конце процесса",
    "Поля: колонка «Базовая» = чистая цена по площади, итоговая = с надбавкой за близость к магазину (видно размер надбавки)",
    "Дропдаун готовых моделей видит модели на диске, даже когда служба Ollama остановлена (через манифесты ~/.ollama/models)",
    "Валюта: отдельный переключатель мода Additional Currencies + переключатель конвертера; prices пишутся в ₽ напрямую либо как €-база, если игра конвертирует сама",
    "Автодетект мода и рублёвого курса из currencies.xml в папке mods (112.66 по умолчанию)",
    "Глобальный коэффициент сложности убран: у каждой выбранной страны свой множитель 0.05–10 с числовым полем, поиском и сбросом к дефолту",
    "Смена курса, валютного режима или пула стран автоматически пересчитывает цены",
  ]},
  { v: "14.0", date: "2026-10-18", title: "World Edition (Tkinter)", items: [
    "Страны мира вместо трёх регионов, флаги и коэффициенты",
    "Тег «Ретро», комплектации MotorSpec, зачатки расчёта полей" ]},
  { v: "13.0", date: "2026-09-30", title: "Ultimate Edition", items: [
    "Алгоритмы calc_vehicle_price / calc_placeable_price, балансировка motorConfiguration",
    "Память брендов, кэш модов, обучение спорных позиций, диалог ревью",
    "Резервные копии модов в _backup_original_mods" ]},
  { v: "12.0", date: "2026-09-12", title: "Placeables", items: ["Здания, силосы, производства и точки продажи"] },
  { v: "11.0", date: "2026-08-28", title: "Local AI", items: ["Интеграция с Ollama: автоопределение региона техники"] },
];

function openChangelog() {
  if (!$("#clModal")) {
    const m = document.createElement("div");
    m.className = "modal"; m.id = "clModal"; m.hidden = true;
    m.innerHTML = `<div class="modal-card"><h3>История обновлений</h3>
      <div id="clBody"></div><div class="modal-foot">
      <button class="btn btn-ghost sm" id="clTour">▶ Пройти обучение</button>
      <button class="btn btn-accent sm" id="clClose">Закрыть</button></div></div>`;
    document.body.appendChild(m);
    $("#clClose").onclick = () => { m.hidden = true; };
    $("#clTour").onclick = () => { m.hidden = true; startTour(); };
    m.addEventListener("click", e => { if (e.target === m) m.hidden = true; });
    $("#clBody").innerHTML = CHANGELOG.map(rel => `
      <div style="margin-bottom:18px">
        <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">
          <b style="color:var(--indigo)">v${rel.v}</b>
          <span style="font-size:13px">${esc(rel.title)}</span>
          <span class="dim" style="font-size:11px;margin-left:auto">${rel.date}</span></div>
        <ul style="margin-left:18px;color:var(--muted);font-size:12.5px;line-height:1.7">
          ${rel.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`).join("");
  }
  $("#clModal").hidden = false;
}

/* ── кнопки помощи: в шапке (всегда видны) + продублированы в статус-баре ── */
function injectFooterButtons() {
  const mk = () => `<button class="mini" title="Интерактивное обучение">? Обучение</button>` +
                   `<button class="mini" title="История обновлений программы">` +
                   `v${(S.boot && S.boot.version) || "15.0"} · история</button>`;

  const top = document.createElement("div");
  top.className = "help-box";
  top.innerHTML = mk();
  const tb = $(".tb-right");
  if (tb) tb.appendChild(top);

  const bar = $(".logbar");
  if (bar) {
    const foot = document.createElement("div");
    foot.style.cssText = "margin-left:auto;display:flex;gap:8px";
    foot.innerHTML = mk();
    bar.appendChild(foot);
  }

  document.querySelectorAll(".help-box .mini, .logbar .mini").forEach(b => {
    if (/Обучение/.test(b.textContent)) b.onclick = () => startTour();
    else b.onclick = () => openChangelog();
  });
}

/* ── старт ── */
window.addEventListener("DOMContentLoaded", () => {
  try { bindSettings(); } catch (e) { console.error("bindSettings", e); }
  try { injectFooterButtons(); } catch (e) { console.error("footer", e); }
  boot();
  startIntro();
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closePop(); closeMenu(); closeTtx(); if ($("#clModal")) $("#clModal").hidden = true; }
    if (e.key === "F5") { e.preventDefault(); renderTable(); }
  });
});

/* ── watchdog: диагностика, если boot не пришёл ── */
setTimeout(() => {
  if (!S.boot) {
    const h = document.querySelector(".boot-hint");
    if (h) h.textContent = "boot не получен | pywebview=" + typeof window.pywebview +
      " | api=" + String(!!(window.pywebview && window.pywebview.api));
  }
}, 12000);
