"use strict";

function specValue(item, key) {
  return Number(item[key] || 0);
}

function specForm(item) {
  const fields = {
    hp: ["Мощность, л.с.", "Power, hp", 3000, 1],
    max_speed: ["Максимальная скорость, км/ч", "Maximum speed, km/h", 200, 1],
    capacity: ["Вместимость, л", "Capacity, L", 500000, 50],
    working_width: ["Ширина захвата, м", "Working width, m", 60, 0.1],
    needed_hp: ["Требуемая мощность, л.с.", "Required power, hp", 3000, 1],
    production_cost: ["Расходы в час", "Hourly operating costs", 100000, 10],
    slots: ["Количество мест", "Number of slots", 512, 1],
    prod_cycles: ["Циклы в час (все линии)", "Cycles per hour (all lines)", 200, 0.1],
    prod_output: ["Выход за цикл (все линии)", "Output per cycle (all lines)", 5000000, 1],
    prod_input: ["Сырьё за цикл (все линии)", "Input per cycle (all lines)", 5000000, 1],
    prod_cost_month: ["Расходы в активный месяц", "Costs per active month", 5000000, 1],
    storage_capacity: ["Внутренний склад, л", "Internal storage, L", 20000000, 500],
    goods_count: ["Принимаемых типов продукции", "Accepted product types", 512, 1],
  };
  let html = '<div class="field2">' + (item.spec_fields || []).map(key => {
    const meta = fields[key];
    if (!meta) return "";
    return `<div class="field"><label>${esc(uiText(meta[0], meta[1]))}</label>
      <input type="number" data-spec="${key}" min="0" max="${meta[2]}" step="${meta[3]}"
      value="${specValue(item, key)}"${key === "slots" ? " disabled" : ""}></div>`;
  }).join("") + "</div>";
  if ((item.productions || []).length) {
    html += `<h4>${uiText("Линии производства", "Production lines")}</h4>` +
      item.productions.map(line => `<div class="production-line"><b>${esc(line.title)}</b>
      <p>${fmt2(line.cycles_per_hour)} ${uiText("циклов/ч", "cycles/h")} ·
      ${fmt2(line.throughput)} ${uiText("ед./ч", "units/h")}</p>
      <p>${uiText("Сырьё", "Inputs")}: ${(line.inputs || []).map(input =>
        `${esc(input.fillType || input.fill_type || input.type || "")} ${fmt2(input.amount)}`).join(", ") || "—"}</p>
      <p>${uiText("Выпуск", "Outputs")}: ${(line.outputs || []).map(output =>
        `${esc(output.fillType || output.fill_type || output.type || "")} ${fmt2(output.amount)}`).join(", ") || "—"}</p></div>`).join("");
    html += `<p class="dim sm">${uiText(
      "Общие значения распределяются между линиями пропорционально исходным. Цена обновляется в предпросмотре.",
      "Totals are distributed between lines in their original proportions. The price updates in the preview.")}</p>`;
  }
  return html;
}

function motorsForm(item) {
  return (item.motors || []).map((motor, index) =>
    `<div class="field2 production-line"><div class="field"><label>${esc(motor.label)}</label>
    <input type="number" data-mhp="${index}" min="0" max="3000" step="1" value="${Number(motor.hp) || 0}"></div>
    <div class="field"><label>${uiText("Наценка двигателя (единицы XML)", "Engine surcharge (XML units)")}</label>
    <input type="number" data-mprice="${index}" min="0" max="1000000000" step="1" value="${Number(motor.price_delta) || 0}"></div></div>`
  ).join("");
}

function priceRow(item) {
  return `<div class="field"><label>${uiText("Своя итоговая цена, ₽ (0 — авторасчёт)", "Custom final price, ₽ (0 = automatic)")}</label>
    <input id="mPrice" type="number" min="0" max="100000000000" step="1"
    value="${toRubles(item.manual_price || 0)}">
    <button class="mini" id="mPriceAuto">${uiText("Вернуть авторасчёт", "Restore automatic price")}</button></div>`;
}

function fieldForm(item) {
  return `<div class="field2"><div class="field"><label>${uiText("Площадь, га", "Area, ha")}</label>
    <input id="fArea" data-spec="area" type="number" min="0" max="5000" step="0.01" value="${Number(item.field_area) || 0}"></div>
    <div class="field"><label>${uiText("До магазина, км (−1 — неизвестно)", "Distance to shop, km (−1 = unknown)")}</label>
    <input id="fDist" data-spec="distance" type="number" min="-1" max="50" step="0.01" value="${Number(item.field_distance)}"></div></div>
    <p class="dim sm">${uiText("Проверьте площадь и расстояние, если карта не содержит точных данных.",
      "Check the area and distance if the map does not provide reliable data.")}</p>` + priceRow(item);
}

function toRubles(value) {
  const config = S.boot?.config || {};
  return Math.round(Number(value || 0) * (config.write_direct_rubles === false ? Number(config.exchange_rate) || 1 : 1));
}

function fromRubles(value) {
  const config = S.boot?.config || {};
  return Math.round(Number(value || 0) / (config.write_direct_rubles === false ? Number(config.exchange_rate) || 1 : 1));
}

function patchRow(item) {
  putItem(item);
  const previous = [...$("#tbody").children].find(row => row.dataset.key === item.unique_key);
  if (previous) {
    if (matches(item)) previous.replaceWith(rowEl(item));
    else previous.remove();
  } else if (matches(item)) $("#tbody").appendChild(rowEl(item));
  updateStats();
  renderSelection();
}

function closePop() { $("#pop").hidden = true; }
function closeMenu() { $("#motorPop").hidden = true; $("#pricePop").hidden = true; }

function positionPopup(popup, anchor) {
  const bounds = anchor.getBoundingClientRect();
  popup.hidden = false;
  popup.style.position = "fixed";
  popup.style.left = Math.max(8, Math.min(bounds.left, innerWidth - popup.offsetWidth - 8)) + "px";
  popup.style.top = Math.max(8, Math.min(bounds.bottom + 5, innerHeight - popup.offsetHeight - 8)) + "px";
}

function openCountry(anchor, keys) {
  closeMenu();
  const popup = $("#pop"), search = $("#popSearch"), list = $(".pop-list", popup);
  const paint = () => {
    const selected = new Set(S.boot.config.selected_countries || []);
    list.innerHTML = S.boot.countries.filter(country =>
      selected.has(country.name) && (country.name + " " + (country.display_name || "")).toLowerCase().includes(search.value.toLowerCase())
    ).map(country => `<button class="country-option" data-value="${esc(country.name)}">${country.flag} ${esc(country.display_name || country.name)}</button>`).join("");
    $$("[data-value]", list).forEach(button => button.onclick = async () => {
      closePop();
      for (const key of keys) {
        const result = await call("set_country", key, button.dataset.value);
        if (result?.ok) patchRow(result.item);
      }
      toast("ok", uiText("Страна назначена", "Country assigned"));
    });
  };
  search.value = ""; search.oninput = paint; paint(); positionPopup(popup, anchor); search.focus();
}

async function openPrice(anchor, item) {
  closePop(); closeMenu();
  const popup = $("#pricePop");
  popup.innerHTML = `<div class="ctx-h">${esc(item.title)}</div><div class="pp-row">
    <input id="customRubles" type="number" min="1" max="100000000000" step="1"
    value="${Number(item.new_price_rub) || toRubles(item.new_price)}"><b>₽</b></div>
    <div class="pp-chain">${chainLine(item)}</div><div class="pp-hint" id="customDelta"></div>
    <div class="pp-btns"><button class="btn btn-accent sm" id="customSave">${uiText("Сохранить", "Save")}</button>
    <button class="btn btn-ghost sm" id="customAuto">${uiText("Авторасчёт", "Automatic")}</button></div>`;
  positionPopup(popup, anchor);
  const input = $("#customRubles");
  const breakdown = await call("breakdown", item.unique_key);
  if (popup.hidden || !input.isConnected) return;
  const automatic = Number(breakdown?.breakdown?.auto_price_rub) || item.new_price_rub;
  const paint = () => {
    const value = Number(input.value);
    const valid = Number.isFinite(value) && value > 0 && value <= 100000000000;
    $("#customSave").disabled = !valid;
    $("#customDelta").textContent = valid
      ? `${uiText("Авторасчёт", "Automatic")}: ${fmt(automatic)} ₽ · ${value >= automatic ? "+" : "−"}${fmt(Math.abs(value - automatic))} ₽`
      : uiText("Введите положительное число", "Enter a positive number");
  };
  input.oninput = paint; paint(); input.focus(); input.select();
  $("#customSave").onclick = async () => {
    if ($("#customSave").disabled) return;
    const result = await call("set_price", item.unique_key, fromRubles(Number(input.value)), "manual");
    if (result?.ok) { closeMenu(); patchRow(result.item); }
  };
  $("#customAuto").onclick = async () => {
    const result = await call("clear_price", item.unique_key);
    if (result?.ok) { closeMenu(); patchRow(result.item); }
  };
  input.onkeydown = event => { if (event.key === "Enter") $("#customSave").click(); };
}

function openMotors(anchor, item) {
  closeMenu();
  const popup = $("#motorPop");
  popup.innerHTML = (item.motor_prices || []).map((motor, index) =>
    `<button class="country-option" data-motor="${index}">${esc(motor.label)} · ${fmt(toRubles(motor.total))} ₽</button>`
  ).join("") + `<button class="country-option" id="editMotors">${uiText("Изменить ТТХ двигателей", "Edit engine specifications")}</button>`;
  positionPopup(popup, anchor);
  $$("[data-motor]", popup).forEach(button => button.onclick = async () => {
    const motor = item.motor_prices[Number(button.dataset.motor)];
    const result = await call("set_price", item.unique_key, motor.total, "motor");
    if (result?.ok) { closeMenu(); patchRow(result.item); }
  });
  $("#editMotors").onclick = () => { closeMenu(); openTtx(item.unique_key); };
}

const cheatConfirmed = new Set();
function confirmCheat(items) {
  if (!S.boot?.config.cheat_detect) return true;
  const flagged = items.filter(item => item.is_cheat && !cheatConfirmed.has(item.unique_key + item.cheat_reason));
  if (!flagged.length) return true;
  if (!confirm(uiText(
    "Подозрительные характеристики могут нарушить атмосферу и баланс игры. Продолжить работу с этими модами?",
    "Unusual specifications may disrupt immersion and game balance. Continue working with these mods?") +
    "\n\n" + flagged.slice(0, 12).map(item => item.title + ": " + item.cheat_reason).join("\n"))) return false;
  flagged.forEach(item => cheatConfirmed.add(item.unique_key + item.cheat_reason));
  return true;
}

function renderSelection() {
  const bar = $("#selectionBar");
  if (!bar) return;
  bar.hidden = !S.selected.size;
  $("#selectionCount").textContent = uiText("Выбрано: ", "Selected: ") + S.selected.size;
}

function subgroupMenu(anchor) {
  closeMenu();
  const popup = $("#motorPop");
  const groups = S.boot.subgroups || [];
  popup.innerHTML = `<div class="ctx-h">${uiText("Подгруппы зданий", "Building subgroups")}</div>` +
    groups.map(group => `<label class="country-option"><input type="checkbox" data-subgroup="${esc(group.key)}"
    ${!S.subgroups.size || S.subgroups.has(group.key) ? "checked" : ""}> ${esc(group.label)}</label>`).join("") +
    `<button class="btn btn-accent sm" id="subgroupSave">${uiText("Показать", "Show")}</button>`;
  positionPopup(popup, anchor);
  $("#subgroupSave").onclick = () => {
    S.subgroups = new Set($$("[data-subgroup]:checked", popup).map(input => input.dataset.subgroup));
    if (!S.subgroups.size) S.subgroups.add("__none__");
    S.filter = "placeable"; closeMenu(); renderTable();
  };
}

document.addEventListener("DOMContentLoaded", () => {
  const settings = document.createElement("div");
  settings.id = "cheatSettings"; settings.className = "card";
  const limits = [
    ["cheat_max_hp", "Мощность, л.с.", "Power, hp"],
    ["cheat_max_speed", "Скорость, км/ч", "Speed, km/h"],
    ["cheat_max_width", "Захват, м", "Working width, m"],
    ["cheat_max_capacity", "Вместимость, л", "Capacity, L"],
    ["cheat_max_needed_hp", "Требуемая мощность, л.с.", "Required power, hp"],
    ["cheat_max_cycles", "Циклы производства в час", "Production cycles per hour"],
    ["cheat_price_ratio", "Расхождение цены, раз", "Price difference ratio"],
  ];
  settings.innerHTML = `<h3 data-ru="Проверка баланса модов" data-en="Mod balance checks">Проверка баланса модов</h3>
    <label class="switch"><input type="checkbox" id="cheatDetect"><span class="track"><i></i></span>
    <em data-ru="Помечать подозрительные моды" data-en="Flag suspicious mods">Помечать подозрительные моды</em></label>
    <label class="switch"><input type="checkbox" id="cheatAi"><span class="track"><i></i></span>
    <em data-ru="Использовать ИИ для проверки" data-en="Use AI for checks">Использовать ИИ для проверки</em></label>
    <p class="dim sm" data-ru="Режим можно полностью отключить. Ноль означает отсутствие порога. Если пороги не заданы и ИИ недоступен, детект не работает. Помеченные моды участвуют в пересчёте."
    data-en="This mode is optional. Zero means no threshold. Without thresholds or an available AI, detection is inactive. Flagged mods remain included in price calculations.">
    Режим можно полностью отключить. Ноль означает отсутствие порога. Если пороги не заданы и ИИ недоступен, детект не работает. Помеченные моды участвуют в пересчёте.</p>
    <div class="field2">${limits.map(([key, russian, english]) =>
      `<div class="field"><label data-ru="${russian}" data-en="${english}">${russian}</label>
      <input type="number" data-limit="${key}" min="0" max="50000000" step="0.1" value="0"></div>`).join("")}</div>
    <button class="btn btn-accent sm" id="saveCheat" data-ru="Сохранить проверку баланса" data-en="Save balance checks">Сохранить проверку баланса</button>`;
  $("#view-pro").appendChild(settings);
  $("#saveCheat").onclick = async () => {
    const patch = { cheat_detect: $("#cheatDetect").checked, cheat_use_ai: $("#cheatAi").checked };
    for (const input of $$("[data-limit]", settings)) {
      const value = Number(input.value);
      if (!Number.isFinite(value) || value < 0) return toast("err", uiText("Введите положительное число или 0", "Enter a positive number or zero"));
      patch[input.dataset.limit] = value;
    }
    const result = await call("set_config", patch);
    if (result?.ok) {
      S.boot.config = result.config;
      if (S.order.length) guard(call("recalc"));
      toast("ok", uiText("Настройки проверки сохранены", "Balance checks saved"));
    }
  };
  const filters = $("#filters");
  const cheat = document.createElement("button");
  cheat.className = "chip"; cheat.dataset.f = "cheat";
  cheat.textContent = uiText("⚠ Подозрительные", "⚠ Flagged mods");
  cheat.onclick = () => {
    S.filter = "cheat";
    $$(".chip", filters).forEach(chip => chip.classList.toggle("is-on", chip === cheat));
    renderTable();
  };
  filters.appendChild(cheat);
  const buildings = $('[data-f="placeable"]', filters);
  if (buildings) buildings.onclick = () => subgroupMenu(buildings);

  const bar = document.createElement("div");
  bar.id = "selectionBar"; bar.className = "selection-bar"; bar.hidden = true;
  bar.innerHTML = `<span id="selectionCount"></span>
    <button class="mini" id="bulkCountry">${uiText("Назначить страну", "Assign country")}</button>
    <button class="mini" id="selectVisible">${uiText("Выбрать видимые", "Select visible")}</button>
    <button class="mini" id="clearSelection">${uiText("Снять выделение", "Clear selection")}</button>`;
  filters.after(bar);
  $("#bulkCountry").onclick = event => openCountry(event.currentTarget, [...S.selected]);
  $("#selectVisible").onclick = () => { [...S.items.values()].filter(matches).forEach(item => S.selected.add(item.unique_key)); renderTable(); };
  $("#clearSelection").onclick = () => { S.selected.clear(); renderTable(); };
  let previousKey = null;
  $("#tbody").addEventListener("click", async event => {
    const row = event.target.closest(".trow");
    if (!row) return;
    const item = S.items.get(row.dataset.key), key = item.unique_key;
    const select = event.target.closest("[data-select]");
    if (select) {
      if (event.shiftKey && previousKey) {
        const visible = S.order.filter(entry => matches(S.items.get(entry)));
        const start = visible.indexOf(previousKey), end = visible.indexOf(key);
        if (start >= 0 && end >= 0) visible.slice(Math.min(start, end), Math.max(start, end) + 1).forEach(entry => {
          if (select.checked) S.selected.add(entry); else S.selected.delete(entry);
        });
      } else if (select.checked) S.selected.add(key); else S.selected.delete(key);
      previousKey = key; renderTable(); return;
    }
    if (event.target.closest("[data-specs]")) return openTtx(key);
    if (event.target.closest("[data-price]")) return openPrice(event.target.closest("[data-price]"), item);
    if (event.target.closest("[data-configs]")) return openMotors(event.target.closest("[data-configs]"), item);
    if (event.target.closest("[data-auto]")) {
      const result = await call("clear_price", key);
      if (result?.ok) patchRow(result.item);
    }
    if (event.target.closest("[data-retro]") && S.boot.config.retro_enabled) {
      const result = await call("set_retro", key, !item.is_retro);
      if (result?.ok) patchRow(result.item);
    }
  });
  $("#tbody").addEventListener("dblclick", event => {
    const country = event.target.closest("[data-country]");
    if (country) openCountry(country, [country.dataset.country]);
  });
  $("#tbody").addEventListener("contextmenu", event => {
    const row = event.target.closest(".trow");
    if (!row) return;
    event.preventDefault(); closeMenu(); closePop();
    const item = S.items.get(row.dataset.key), popup = $("#motorPop");
    popup.innerHTML = `<button class="country-option" id="webSearch">${uiText("Веб-поиск в Google", "Search Google")}</button>`;
    positionPopup(popup, { getBoundingClientRect: () => ({ left: event.clientX, bottom: event.clientY }) });
    $("#webSearch").onclick = () => {
      closeMenu();
      const query = `${item.brand} ${item.title} ${uiText("характеристики страна производитель", "specifications manufacturer country")}`;
      call("open_url", "https://www.google.com/search?q=" + encodeURIComponent(query));
    };
  });
  document.addEventListener("click", event => {
    if (!event.target.closest("#pop, [data-country], #bulkCountry")) closePop();
    if (!event.target.closest("#motorPop, #pricePop, [data-price], [data-configs], [data-f='placeable']")) closeMenu();
  });
});
