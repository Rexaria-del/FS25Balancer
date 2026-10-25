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

function startIntro() {
  const el = $("#intro");
  if (!el) return finishIntro();
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
    call("log", "js shell visible");
    maybeTour();
  }, 450);
}

function fillScanTargets(list, current) {
  $("#scanTarget").innerHTML = (list || []).map(t =>
    `<option value="${t.key}"${t.key === current ? " selected" : ""}>${esc(t.label)}</option>`).join("");
}

function applyConfigToUI(c) {
  $("#gds").value = c.global_difficulty_scale;
  $("#place").value = c.k_placeable;
  $("#fieldK").value = c.k_field;
  $("#retroK").value = Math.round(c.k_retro * 100);
  $("#wearK").value = Math.round(c.retro_wear * 100);
  $("#addCurr").checked = !!c.use_additional_currencies;
  $("#rate").value = c.exchange_rate;
  $("#adjFields").checked = !!c.adjust_field_prices;
  $("#retroOn").checked = c.retro_enabled !== false;
  paintRetroState(c.retro_enabled !== false);
  $("#maxD").value = c.field_max_distance;
  $("#spread").value = Math.round(c.field_distance_spread * 100);
  $("#backups").checked = !!c.create_backups;
  $("#useAi").checked = !!c.use_local_ai;
  $("#aiModel").value = c.ai_model_name;
  $("#shopX").value = (c.shop_coordinates.shop || [0, 0])[0];
  $("#shopZ").value = (c.shop_coordinates.shop || [0, 0])[1];
  $("#scanTarget").value = c.scan_target;
  $$("#vGds, #vPlace, #vField").forEach(() => {});
  $("#vGds").textContent = Number(c.global_difficulty_scale).toFixed(2);
  $("#vPlace").textContent = Number(c.k_placeable).toFixed(2);
  $("#vField").textContent = Number(c.k_field).toFixed(2);
  $("#vRetroK").textContent = Math.round(c.k_retro * 100);
  $("#vWearK").textContent = Math.round(c.retro_wear * 100);
  $("#vMaxD").textContent = Number(c.field_max_distance).toFixed(1);
  $("#vSpread").textContent = Math.round(c.field_distance_spread * 100);
  ["gds", "place", "fieldK", "retroK", "wearK", "maxD", "spread"].forEach(id => {
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
    case "recalc_done":
      setBusy(false);
      flushRows();
      renderTable();
      log(`Цены пересчитаны: ${d.items} позиций за ${d.elapsed} с (без скана)`, "ok");
      toast("ok", `⚡ Пересчитано ${d.items} позиций без повторного сканирования`);
      break;
    case "applied":
      setBusy(false);
      log(d.aborted ? "Применение прервано" : `Записано в моды: ${d.count} позиций`, d.aborted ? "warn" : "ok");
      toast(d.aborted ? "warn" : "ok", d.aborted ? "Применение прервано" : `💾 Готово: изменено ${d.count} файлов позиций`);
      break;
    case "ai_status":
      checkAi();
      break;
    case "ai_progress":
      log(d.msg || "", "busy");
      break;
    case "ai_done":
      setBusy(false);
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
      (inst.length ? `<div class="hr"></div><div class="dim sm">Установленные модели (${inst.length}) — можно удалить из программы:</div>` +
        inst.map(n => `
        <div class="ai-i"><span>${esc(n)}${n === st.current ? ' <span class="dim"> · текущая</span>' : ""}</span>
          <button class="mini danger" data-del="${esc(n)}">🗑 удалить</button></div>`).join("") : "") +
      `<div class="hr"></div>
      <div class="dim sm">Или любой тег из библиотеки Ollama:</div>
      <div style="display:flex;gap:8px"><input type="text" id="aiModelCustom" placeholder="например mistral:latest" value="${esc(st.current || "")}">
      <button class="mini" id="btnCustomSetup">настроить</button></div>
      <div class="btnrow"><button class="mini danger" id="btnAiUninstall">🗑 Удалить Ollama из системы</button></div>`;
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
  const bc = $("#btnCustomSetup");
  if (bc) bc.onclick = () => { const v = $("#aiModelCustom").value.trim(); if (v) aiOneClick(v); else toast("warn", "Введите тег модели"); };
  const bu = $("#btnAiUninstall");
  if (bu) bu.onclick = async () => {
    if (!confirm("Удалить Ollama из системы? Запустится тихий деинсталлятор; папка со скачанными моделями (%USERPROFILE%\\.ollama) останется — снесёшь её руками при желании.")) return;
    const r = await call("ai_uninstall");
    if (r && r.ok) toast("info", "Запускаю деинсталляцию Ollama…");
  };
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
  return `<div class="c-new">
      <button class="price-btn" data-price="${esc(it.unique_key)}" title="${hasMotors ? "Выбрать комплектацию" : "Задать цену вручную"}">
        <b>${fmt(it.new_price)}</b>${hasMotors ? ' <span class="dim">▾</span>' : ""}${manual ? ' <span title="вручную">✎</span>' : ""}
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
    <span class="c-specs" title="${specs}">${specs}</span>
    <span class="c-old">${fmt(it.old_price)}</span>
    <span class="c-base">${fmt(it.base_price)}</span>
    ${priceCell(it)}
    <span class="c-rub">${fmt(it.new_price_rub)}</span>
    <span class="c-src" title="${esc(it.ai_reason)} · kC=${fmt2(it.country_mult)} kR=${fmt2(it.retro_mult)}">${esc(it.ai_reason)}</span>`;
  return tr;
}
const fmt1 = v => Number(v || 0).toFixed(1).replace(/\.0$/, "");
const fmt2 = v => Number(v || 0).toFixed(2);

/* делегирование кликов таблицы */
$("#tbody").addEventListener("click", e => {
  const sw = e.target.closest("[data-retro]");
  if (sw) { toggleRetro(sw.dataset.retro, !sw.classList.contains("is-on")); return; }
  const pb = e.target.closest("[data-price]");
  if (pb) { openPriceMenu(pb.dataset.price, pb); return; }
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

/* ── модалка ТТХ / ручной цены ── */
let ttxKey = null;
function openTtx(key) {
  const it = S.items.get(key);
  if (!it) return;
  ttxKey = key;
  $("#modalTitle").textContent = `${it.type_icon} ${it.title}`;
  let html = "";
  if (it.item_type === "field") {
    html = `
      ${it.needs_review ? `<div class="mnote">⚠️ ${esc(it.ai_reason)} — подтверди или впиши значения вручную.</div>` : ""}
      <div class="mrow"><label>Площадь, га</label>
        <input type="number" id="fArea" min="0" max="5000" step="0.1" value="${it.field_area || 0}">
        <span class="dim">поиск: 1 га = 10 000 м²</span></div>
      <div class="mrow"><label>Дистанция до магазина, км</label>
        <input type="number" id="fDist" min="-1" max="50" step="0.1" value="${it.field_distance}">
        <span class="dim">-1 = неизвестно</span></div>
      <div class="mrow"><label>Своя цена</label>
        <input type="number" id="fPrice" min="50" step="100" value="${it.new_price}">
        <span class="dim">0 = авторасчёт</span></div>
      <div class="dim sm">Координаты поля: ${it.field_coord ? it.field_coord.map(n => Math.round(n)).join(" / ") : "не найдены"}</div>`;
  } else {
    html = `<div class="mrow"><label>Своя цена (${it.item_type === "vehicle" ? "базовая" : ""})</label>
        <input type="number" id="mPrice" min="50" step="100" value="${it.manual_price != null ? it.manual_price : 0}">
        <span class="dim">0 = авторасчёт</span></div>
      <div class="dim sm">Страна: ${it.country_flag} ${esc(it.country)} · кC=${fmt2(it.country_mult)} ·
        кРетро=${fmt2(it.retro_mult)} · изношенный коэффициент=${fmt2(it.wear_mult)}</div>`;
    if (it.motors && it.motors.length) {
      html += `<div class="ctx-h" style="padding-left:0">Комплектации (ТТХ двигателя)</div>
        <div class="mrow"><label>Название</label><label>Л.С.</label><label>Наценка</label></div>` +
        it.motors.map(m => `
          <div class="mrow">
            <input type="text" data-mlabel="${m.index}" value="${esc(m.label)}">
            <input type="number" data-mhp="${m.index}" min="0" max="2000" step="1" value="${m.hp}">
            <input type="number" data-mprice="${m.index}" min="0" step="100" value="${m.price_delta}">
          </div>`).join("");
    }
  }
  $("#modalBody").innerHTML = html;
  $("#modal").hidden = false;
  $("#modalSave").dataset.mode = it.item_type === "field" ? "field" : "item";
}
function closeTtx() { $("#modal").hidden = true; ttxKey = null; }
$("#modalCancel").onclick = closeTtx;
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeTtx(); });

$("#modalSave").onclick = async () => {
  if (!ttxKey) return closeTtx();
  const it = S.items.get(ttxKey);
  if ($("#modalSave").dataset.mode === "field") {
    const area = $("#fArea").value, dist = $("#fDist").value, price = $("#fPrice").value;
    const a = clampNum(area, 0, 5000, NaN), d = clampNum(dist, -1, 50, NaN);
    if (!isFinite(a)) { markBad("#fArea"); return toast("err", "Площадь должна быть числом 0..5000"); }
    if (!isFinite(d)) { markBad("#fDist"); return toast("err", "Дистанция должна быть числом (-1 = неизвестно)"); }
    const r = await call("patch_field", ttxKey, a, d);
    if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка сохранения поля");
    S.items.set(ttxKey, r.item);
    const p = clampNum(price, 0, 100000000, 0);
    if (p > 0) { const r2 = await call("set_price", ttxKey, p); if (r2 && r2.ok) S.items.set(ttxKey, r2.item); }
    patchRow(r.item);
    toast("ok", "Поле обновлено");
  } else {
    const price = clampNum($("#mPrice").value, 0, 100000000, 0);
    if (price > 0) {
      const r = await call("set_price", ttxKey, price);
      if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка цены");
      S.items.set(ttxKey, r.item);
    } else {
      const idx = $$("#modalBody [data-mhp]");
      for (const el of idx) {
        const i = Number(el.dataset.mhp);
        const hpEl = $(`#modalBody [data-mhp="${i}"]`), prEl = $(`#modalBody [data-mprice="${i}"]`);
        const lbEl = $(`#modalBody [data-mlabel="${i}"]`);
        const hp = clampNum(hpEl.value, 0, 2000, NaN);
        const dp = clampNum(prEl.value, 0, 5000000, NaN);
        if (!isFinite(hp)) { markBad(`#modalBody [data-mhp="${i}"]`); return toast("err", `Л.С. комплектации ${i + 1}: нужно число`); }
        if (!isFinite(dp)) { markBad(`#modalBody [data-mprice="${i}"]`); return toast("err", `Наценка ${i + 1}: нужно число`); }
        if (lbEl) it.motors[i].label = lbEl.value || it.motors[i].label;
        const r = await call("set_motor", ttxKey, i, hp, Math.round(dp));
        if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка ТТХ");
        S.items.set(ttxKey, r.item);
      }
      if (!$$("#modalBody [data-mhp]").length) {
        const r = await call("set_price", ttxKey, it.new_price);
        if (r && r.ok) S.items.set(ttxKey, r.item);
      }
    }
    patchRow(S.items.get(ttxKey));
    toast("ok", "ТТХ сохранены");
  }
  updateStats();
  closeTtx();
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
  $$("#multList [data-mult]").forEach(i => { mults[i.dataset.mult] = parseFloat(i.value); });
  const r = await call("select_countries", [...selSet], mults);
  if (!r || !r.ok) return toast("err", (r && r.error) || "Ошибка сохранения стран");
  S.boot.config.selected_countries = r.selected;
  toast("ok", `Пул стран обновлён: ${r.selected.length}`);
};

/* ── список коэффициентов стран ── */
function renderMultList() {
  const sel = new Set(S.boot.config.selected_countries || []);
  const mult = S.boot.config.country_multipliers || {};
  $("#multList").innerHTML = S.boot.countries.map(c => `
    <div class="mult-i ${sel.has(c.name) ? "" : "is-off"}" data-row="${esc(c.name)}">
      <span class="nm"><span>${c.flag}</span><span>${esc(c.name)}</span></span>
      <input type="range" data-mult="${esc(c.name)}" min="0.1" max="3" step="0.01"
        value="${mult[c.name] != null ? mult[c.name] : c.k}" ${sel.has(c.name) ? "" : "disabled"}>
      <span class="val">${fmt2(mult[c.name] != null ? mult[c.name] : c.k)}×</span>
    </div>`).join("");
  $$("#multList input[type=range]").forEach(el => {
    const paint = () => {
      const min = +el.min, max = +el.max, v = +el.value;
      el.style.setProperty("--fill", ((v - min) / (max - min) * 100).toFixed(1) + "%");
      el.closest(".mult-i").querySelector(".val").textContent = fmt2(v) + "×";
    };
    el.addEventListener("input", paint); paint();
  });
}

/* ── слайдеры настроек ── */
function bindSettings() {
  const map = [
    ["gds", "#vGds", v => Number(v).toFixed(2), "global_difficulty_scale"],
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
    ["addCurr", "use_additional_currencies"], ["adjFields", "adjust_field_prices"],
    ["backups", "create_backups"], ["useAi", "use_local_ai"], ["retroOn", "retro_enabled"],
  ];
  for (const [id, key] of sw) {
    document.getElementById(id).addEventListener("change", async e => {
      const r = await call("set_config", { [key]: e.target.checked });
      if (r && r.ok) {
        S.boot.config = r.config;
        if (key === "adjust_field_prices") drawCurve();
        if (key === "retro_enabled") paintRetroState(e.target.checked);
        if (key === "retro_enabled" && S.order.length) guard(call("recalc"));
      }
      toast(e.target.checked ? "ok" : "info", labelOf(key) + (e.target.checked ? " — вкл" : " — выкл"));
    });
  }
  $("#rate").addEventListener("change", async e => {
    const v = clampNum(e.target.value, 1, 100000, NaN);
    if (!isFinite(v)) { markBad("#rate"); return toast("err", "Курс — число от 1 до 100000"); }
    const r = await call("set_config", { exchange_rate: v });
    if (r && r.ok) { S.boot.config = r.config; toast("ok", "Курс сохранён: " + v + " за 1 €"); }
  });
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
  $("#aiModel").addEventListener("change", async e => {
    const r = await call("set_config", { ai_model_name: e.target.value });
    if (r && r.ok) S.boot.config = r.config;
  });
  $("#btnSavePrices").onclick = () => {
    const mults = {};
    $$("#multList [data-mult]").forEach(i => { if (!i.disabled) mults[i.dataset.mult] = parseFloat(i.value); });
    call("select_countries", [...selSet], mults).then(r => {
      if (r && r.ok) toast("ok", "Коэффициенты и пул стран сохранены");
    });
  };
  $("#btnSaveFields").onclick = () => { drawCurve(); toast("ok", "Настройки полей сохранены"); };
}
function labelOf(key) {
  return { use_additional_currencies: "Доп. валюта", adjust_field_prices: "Изменять цены на поля",
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
$("#btnAiDl").onclick = async () => { const m = $("#aiModel").value.trim(); if (m) { await call("ai_download", m); toast("info", "Скачивание " + m + " — следи за логом внизу"); } };

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
  { sel: "#btnScan", title: "Шаг 1 · Сканирование",
    text: "Укажи папку mods и нажми «Сканировать». Программа прочитает modDesc.xml и XML техники, зданий и полей — файлы при этом не меняются." },
  { sel: "#btnRecalc", title: "Шаг 2 · Обновить цены",
    text: "Кнопка пересчитывает цены по текущим коэффициентам и ретро-настройкам БЕЗ повторного сканирования — изменения видны мгновенно." },
  { sel: '[data-view="countries"]', title: "Шаг 3 · Пул стран",
    text: "Выбери страны, которые вообще допустимы. ИИ и словари брендов не выйдут за этот пул: всё сомнительное попадёт в фильтр «Проверить»." },
  { sel: ".thead .c-country", title: "Шаг 4 · Смена региона",
    text: "Двойной клик по стране в строке — анимированный список стран. Выбор запоминается для бренда и сразу пересчитывает цену." },
  { sel: ".thead .c-retro", title: "Шаг 5 · Ретро-тумблер",
    text: "Переключатель в строке делает технику ретро: цена умножается на коэффициент ретро, а dailyUpkeep — на коэффициент износа." },
  { sel: ".thead .c-new", title: "Шаг 6 · Комплектации",
    text: "Клик по цене откроет список комплектаций двигателя с разными л.с. и ценами; «Своя цена / правка ТТХ» — ручной ввод характеристик." },
  { sel: '[data-view="fields"]', title: "Шаг 7 · Поля и расстояние",
    text: "Включи «Изменять цены на поля» и укажи координаты магазина: чем ближе поле, тем дороже. Если площадь или дистанция не определились — строка попадёт на ручное подтверждение." },
  { sel: "#btnApply", title: "Шаг 8 · Применить",
    text: "Только после «Применить» программа перепишет файлы модов. Резервные копии складываются в _backup_original_mods." },
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
  const el = $(step.sel);
  if (!el) { S.tourStep++; return placeTour(); }
  $("#tourTitle").textContent = step.title;
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

/* ── нижняя панель: «?» и ссылка на обучение ── */
function injectFooterButtons() {
  const bar = $(".logbar");
  const box = document.createElement("div");
  box.style.cssText = "margin-left:auto;display:flex;gap:8px";
  box.innerHTML = `<button class="mini" id="btnTour">? Обучение</button><button class="mini" id="btnCl">v${(S.boot && S.boot.version) || "15.0"} · история</button>`;
  bar.appendChild(box);
  $("#btnTour").onclick = startTour;
  $("#btnCl").onclick = openChangelog;
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
