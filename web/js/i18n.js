"use strict";

let UI_LANG = "ru";
try { UI_LANG = localStorage.getItem("fs25_language") === "en" ? "en" : "ru"; } catch (_) {}
const originalText = new WeakMap();
const originalAttributes = new WeakMap();
const translationCache = new Map();
const UI_PAIRS = [
  ["FS25 Автобалансировщик", "FS25 Balancer"],
  ["Проверка баланса модов", "Mod balance checks"],
  ["Подозрительные", "Flagged mods"], ["🤖 ИИ", "🤖 AI"], ["Выбрано:", "Selected:"],
  ["Как определены страна/ретро", "How country/retro were determined"],
  ["Назначить страну", "Assign country"], ["Выбрать видимые", "Select visible"],
  ["Снять выделение", "Clear selection"], ["Старая", "Original"], ["₽ итог", "RUB total"],
  ["Валюта в моде", "Mod currency"], ["пишем ₽", "write RUB"], ["пишем €", "write EUR"],
  ["В папке mods установлен мод Additional Currencies", "Additional Currencies is installed in the mods folder"],
  ["В игре включена опция «Конвертировать валюты»", "Currency conversion is enabled in the game"],
  ["— авто из currencies.xml", "— auto from currencies.xml"],
  ["файла мода ложится", "in the mod file is"], ["сумма в рублях", "an amount in rubles"],
  [": база (EUR-алгоритм) ×", ": base (EUR pricing algorithm) ×"],
  ["Мод Additional Currencies не нужен — игра отобразит это число в своей валюте.",
   "Additional Currencies is not needed. The game displays this amount in its selected currency."],
  ["Создавать бэкапы перед применением", "Back up changed XML before applying"],
  ["Ретро-техника", "Retro vehicles"], ["Режим «Ретро» включён", "Retro mode enabled"],
  ["Коэффициент цены ретро, %", "Retro price multiplier, %"],
  ["Коэффициент износа ретро, %", "Retro wear multiplier, %"],
  ["СНГ / Восток", "CIS / East"], ["Запад и Европа", "Western Europe"],
  ["Латинская Америка", "Latin America"], ["Азия и Б. Восток", "Asia & Middle East"],
  ["Африка", "Africa"], ["Океания", "Oceania"],
  ["Использовать ИИ для классификации", "Use AI for classification"],
  ["Активная модель — выбор из установленных и готовых к работе", "Active model — choose an installed, ready model"],
  ["моделей не установлено — скачай в каталоге ниже", "no models installed — download one from the catalog below"],
  ["Железо:", "Hardware:"], ["не определено", "not detected"], ["Рекомендуем", "Recommended"],
  ["— лучший баланс точности и скорости для задач программы (короткая классификация «страна/ретро» на русском).",
   "— a balance of speed and capability for country, retro and specification checks."],
  ["Сортировка:", "Sort:"], ["Удалить Ollama из системы", "Uninstall Ollama"],
  ["выбери модель из списка", "choose an installed model"],
  ["Рекомендованная модель", "Recommended model"], ["для твоего железа", "for your hardware"],
  ["оценка для задач", "task fit"], ["выбрать", "select"], ["заново", "again"],
  ["Остальные модели", "Other models"], ["Установленные и готовые к работе модели", "Installed and ready models"],
  ["лучшее понимание русского, оптимальный старт", "good Russian understanding, a starting option"],
  ["эталонная стабильность, требует ресурсов", "stable output, needs more resources"],
  ["флагман Meta для сложных спорных случаев", "Meta model for difficult classification cases"],
  ["максимальная точность на русском", "strong Russian classification"],
  ["надёжная классификация, средний вес", "classification with a medium download size"],
  ["новое поколение Google, хорошая русская речь", "Google model with multilingual support"],
  ["улучшенная phi3, многоязычная", "multilingual Phi model"],
  ["быстрая и лёгкая, для слабых ПК", "small and fast, for lower memory PCs"],
  ["компактная, для быстрого старта", "compact, quick to download"],
  ["с reasoning, но русским слабее", "reasoning model, weaker in Russian"],
  ["самая быстрая из «умных», черновой вариант", "fast, lightweight option"],
  ["сверхлёгкий минимум точности", "very small, lower classification capability"],
  ["ориентир по доступной памяти. Оценка моделей — условный рейтинг для задач программы, не измеренная точность.",
   "a suggestion based on available memory. Scores describe estimated task suitability, not measured accuracy."],
  ["выпуск", "output"], ["сырьё", "input"], ["склад", "storage"], ["расходы", "costs"],
  ["ц/ч", "cycles/h"], ["л/цикл", "L/cycle"], ["база", "base"],
  ["/ч", "/h"],
  ["Производительно", "Throughput"], ["Материальная от", "Material yield"],
  ["Производство", "Production"], ["В", "In"], ["л", "L"],
  ["Автобалансировщик цен", "Price balancer"],
  ["Баланс рынка · 177 стран · ретро · локальный ИИ", "Market balance · countries · retro · local AI"],
  ["клик или клавиша — пропустить", "click or press a key to skip"],
  ["инициализация модуля расчётов…", "initializing the pricing engine…"],
  ["Скан и таблица", "Scan & table"], ["Цены и коэффициенты", "Prices & multipliers"],
  ["PRO-режим / ИИ", "PRO mode / AI"], ["Цены", "Prices"], ["Страны", "Countries"],
  ["Поля и расстояние", "Fields & distance"], ["Поля", "Fields"], ["PRO / ИИ", "PRO / AI"],
  ["папка mods не выбрана", "no mods folder selected"],
  ["элементов", "items"], ["элементы", "items"], ["ретро", "retro"], ["сек", "sec"],
  ["Сканировать", "Scan"], ["Обновить цены", "Update prices"], ["Применить", "Apply"],
  ["Общие коэффициенты", "General multipliers"], ["Коэф. зданий", "Building multiplier"],
  ["Коэф. полей", "Field multiplier"], ["Коэффициент цены Ретро", "Retro price multiplier"],
  ["Коэффициент износа Ретро", "Retro wear multiplier"], ["Режим Ретро", "Retro mode"],
  ["Ретро-механика", "Retro mechanics"], ["Ретро", "Retro"], ["Обновление цен", "Price updates"],
  ["Пул стран", "Country pool"], ["Коэффициенты стран", "Country multipliers"],
  ["Личный множитель для каждой выбранной страны — он заменяет прежний глобальный коэффициент сложности. Применяется к технике и зданиям этой страны при каждом пересчёте цены.",
   "Each selected country has its own price multiplier. It applies to vehicles and buildings from that country whenever prices are recalculated."],
  ["Выбранные страны определяют работу ИИ и словарей брендов. Техника вне пула помечается «⚠️ Проверить».",
   "AI and brand dictionaries use only the selected countries. Uncertain items are marked for review."],
  ["Глобальной «сложности» больше нет: общий множитель задаётся отдельно для каждой страны во вкладке",
   "Set an individual multiplier for each country in the"],
  ["Поиск страны…", "Search countries…"], ["Поиск по названию, бренду или моду…", "Search name, brand or mod…"],
  ["Поиск…", "Search…"], ["Все", "All"], ["Всё", "All"], ["Техника", "Vehicles"],
  ["Здания и объекты", "Buildings & placeables"], ["Здания", "Buildings"], ["Проверить", "Review"],
  ["Свои цены", "Custom prices"], ["Страна", "Country"], ["Бренд", "Brand"],
  ["Хар-ки", "Specs"], ["ХАР-КИ", "SPECS"], ["МОД", "MOD"], ["НАЗВАНИЕ", "NAME"],
  ["БРЕНД", "BRAND"], ["СТРАНА", "COUNTRY"], ["РЕТРО", "RETRO"],
  ["СТАРАЯ", "ORIGINAL"], ["БАЗА", "BASE"], ["НОВАЯ", "FINAL"], ["ИТОГО", "TOTAL"],
  ["РУБЛИ", "RUBLES"], ["РАСЧЁТ", "BREAKDOWN"], ["Название", "Name"], ["База", "Base"],
  ["Базовая", "Base"], ["Исходная", "Original"], ["Новая", "Final"], ["Итоговая", "Final"],
  ["Как считается", "Calculation"], ["Источник", "Source"], ["Файл мода", "Mod file"],
  ["Ничего не найдено", "No items found"], ["Пока пусто", "No items yet"],
  ["Сначала отсканируй моды", "Scan your mods first"],
  ["Начните со сканирования папки mods", "Start by scanning your mods folder"],
  ["Европа", "Europe"], ["Америка", "Americas"], ["Азия", "Asia"], ["Прочие", "Other"],
  ["СНГ", "CIS"], ["Топ-12", "Top 12"], ["Сброс", "Reset"],
  ["Сохранить пул стран", "Save country pool"], ["Сохранить коэффициенты", "Save multipliers"],
  ["Показать все страны", "Show all countries"], ["Дефолты стран", "Default multipliers"],
  ["Системный промпт ИИ", "AI system prompt"], ["Бренды по странам", "Brands by country"],
  ["Выбери страну и редактируй список брендов (по одному на строку или через запятую).",
   "Choose a country and edit its brands (one per line or separated by commas)."],
  ["Промпт для классификации…", "Classification prompt…"], ["Сохранить PRO", "Save PRO settings"],
  ["Сбросить промпт", "Reset prompt"], ["Экспорт профиля", "Export profile"],
  ["Цены для друга", "Share prices with a friend"], ["Экспорт цен", "Export prices"],
  ["Импорт цен", "Import prices"], ["Откатить из бэкапа", "Restore backup"],
  ["Свой прайс-бандл не загружен.", "No price bundle loaded."],
  ["Чужой прайс-бандл не загружен.", "No shared price bundle loaded."],
  ["«Экспорт цен» создаёт файл, который можно отправить другу вместо всего модпака — у него кнопки «Импорт цен» хватит.",
   "Export prices creates a small file to send to your friend. With the same mod versions installed, they can import it and click Apply."],
  ["Модпак весит 20+ ГБ, а цены — десятки килобайт. «Экспорт» пишет один JSON: финальные цены, ретро-флаги, страны и ручные правки ТТХ. Друг жмёт «Импорт» у себя — и получает те же цифры, не перебирая моды заново.",
   "Share a small JSON file instead of a 20+ GB mod pack. It contains final prices, countries, retro flags and edited specifications. Your friend needs the same mod versions: scan, import the file, then Apply."],
  ["Изменять цены на поля по расстоянию до магазина", "Adjust field prices by distance to the shop"],
  ["Макс. дистанция, км", "Maximum distance, km"], ["Разброс цены у магазина, %", "Premium near the shop, %"],
  ["Координата магазина X", "Shop coordinate X"], ["Координата магазина Z", "Shop coordinate Z"],
  ["у магазина (дороже)", "near the shop (more expensive)"], ["на границе радиуса", "at the radius boundary"],
  ["Сохранить настройки полей", "Save field settings"],
  ["Без мода Additional Currencies", "Without Additional Currencies"],
  ["Валюта и рубли", "Currency & rubles"], ["Курс ₽ за 1 €", "RUB per EUR"],
  ["Курс рубля", "Ruble exchange rate"], ["Валюта XML", "XML currency"],
  ["Мод Additional Currencies установлен", "Additional Currencies is installed"],
  ["Конвертер валют включён", "Currency conversion enabled"],
  ["Найти мод и курс автоматически", "Detect currency mod and exchange rate"],
  ["Найти мода и курс автоматически", "Detect currency mod and exchange rate"],
  ["Создавать резервные копии", "Back up changed files"],
  ["Локальный ИИ", "Local AI"], ["Использовать локальный ИИ", "Use local AI"],
  ["Активная модель", "Active model"], ["Выключать Ollama и все модели при закрытии программы",
   "Stop Ollama and unload all models when closing this app"],
  ["Очистить всю память", "Clear learned data and caches"],
  ["Запустить Ollama", "Start Ollama"], ["Остановить службу", "Stop service"],
  ["Обновить список", "Refresh list"], ["Удалить Ollama", "Uninstall Ollama"],
  ["Каталог моделей", "Model catalog"], ["Рекомендуемая модель", "Recommended model"],
  ["РЕКОМЕНДУЕМ", "RECOMMENDED"], ["рекомендована", "recommended"],
  ["установить и использовать", "install & use"], ["Установить и использовать", "Install & use"],
  ["Использовать", "Use"], ["использовать", "use"], ["удалить", "delete"], ["Удалить", "Delete"],
  ["на диске", "on disk"], ["не установлена", "not installed"], ["установлена", "installed"],
  ["Запущена", "Running"], ["готов к работе", "ready"], ["активна", "active"],
  ["по весу", "by size"], ["По весу", "By size"], ["по точности", "by accuracy"],
  ["По точности", "By accuracy"], ["Тяжёлые сверху", "Largest first"], ["Лёгкие сверху", "Smallest first"],
  ["Точность", "Accuracy"], ["Вес", "Size"], ["Скачать", "Download"],
  ["Выбрать", "Choose"], ["Выбор папки", "Choose folder"], ["Папка mods", "Mods folder"],
  ["Обучение", "Tutorial"], ["История обновлений", "Release history"], ["история", "history"],
  ["больше не показывать", "don't show again"], ["Пропустить", "Skip"], ["Далее", "Next"],
  ["Готово", "Done"], ["Сохранить", "Save"], ["Отмена", "Cancel"], ["Из файла", "From mod file"],
  ["Из чего складывается цена", "Price breakdown"], ["Живой предпросмотр", "Live preview"],
  ["без изменений", "unchanged"], ["считаю…", "calculating…"],
  ["вручную", "manual"], ["комплектация", "engine configuration"],
  ["Комплектации", "Engine configurations"], ["Цена не ручная — выбрана комплектация. ↺ рядом вернёт базовую",
   "An engine configuration is selected. Click ↺ to restore the automatic base price"],
  ["Цену задал ты. «Обновить цены» и коэффициенты её не трогают",
   "Custom price. Update prices and multipliers will not change it"],
  ["Вернуть авторасчёт", "Restore automatic price"], ["Клик — задать свою цену", "Click to set a custom price"],
  ["Двойной клик — сменить страну", "Double-click to change country"],
  ["Клик или двойной клик — правка характеристик и разбор цены", "Click to edit specifications and see the price breakdown"],
  ["клик — своя цена и разбор", "click for custom price and breakdown"],
  ["Снять ВСЕ ручные цены и вернуть авторасчёт", "Reset ALL custom prices to automatic prices"],
  ["Сканирование", "Scanning"], ["Сканирование завершено", "Scan complete"],
  ["Пересчёт цен…", "Recalculating prices…"], ["Подготовка…", "Preparing…"],
  ["Запись в моды…", "Writing changes…"], ["Откат из бэкапа…", "Restoring backup…"],
  ["Восстановление исходных цен…", "Restoring original prices…"],
  ["Мост Python ещё не готов", "The Python connection is initializing"],
  ["Сначала выполни сканирование", "Scan your mods first"],
  ["Страна назначена", "Country assigned"], ["Загружен бандл", "Price bundle loaded"],
  ["забыть", "forget"], ["позиций", "items"], ["выбрано", "selected"], ["строк", "rows"],
  ["из", "of"], ["МБ", "MB"], ["ГБ", "GB"], ["КБ", "KB"],
];
const UI_TRANSLATIONS = UI_PAIRS.slice().sort((first, second) => second[0].length - first[0].length);

function uiText(russian, english) { return UI_LANG === "en" ? english : russian; }

function translateUI(value) {
  if (UI_LANG !== "en" || !/[А-Яа-яЁё]/.test(value)) return value;
  if (translationCache.has(value)) return translationCache.get(value);
  let translated = value;
  const protectedNames = [];
  if (typeof S !== "undefined" && S.boot) {
    const names = new Intl.DisplayNames(["en"], { type: "region" });
    for (const country of [...(S.boot.countries || [])].sort((a, b) => b.name.length - a.name.length)) {
      const name = country.iso2 === "SU" ? "USSR" : /^[A-Z]{2}$/.test(country.iso2 || "") ? names.of(country.iso2) : null;
      if (name && translated.includes(country.name)) {
        const marker = "\uE000" + protectedNames.length + "\uE001";
        protectedNames.push([marker, name]);
        translated = translated.split(country.name).join(marker);
      }
    }
  }
  for (const [russian, english] of UI_TRANSLATIONS) {
    if (russian.length < 4) {
      translated = translated.replace(new RegExp("(?<![\\p{L}])" + russian + "(?![\\p{L}])", "gu"), english);
    } else translated = translated.split(russian).join(english);
  }
  for (const [marker, name] of protectedNames) translated = translated.split(marker).join(name);
  if (translationCache.size > 3000) translationCache.clear();
  translationCache.set(value, translated);
  return translated;
}

function translateTree(root) {
  if (!root || root.nodeType !== 1 || root.closest("script, style, textarea, .logbar, .data-path, .c-name, .c-brand, .c-mod")) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement.closest("[data-ru][data-en]")) continue;
    if (node.parentElement.closest("script, style, textarea, .logbar, .data-path, .c-name, .c-brand, .c-mod")) continue;
    const saved = originalText.get(node);
    const source = saved && node.nodeValue === saved.last ? saved.source : node.nodeValue;
    const translated = translateUI(source);
    if (node.nodeValue !== translated) node.nodeValue = translated;
    originalText.set(node, { source, last: translated });
  }
  for (const element of [root, ...root.querySelectorAll("[title], [placeholder], [aria-label]")]) {
    const saved = originalAttributes.get(element) || {};
    for (const attribute of ["title", "placeholder", "aria-label"]) {
      if (!element.hasAttribute(attribute)) continue;
      const value = element.getAttribute(attribute), previous = saved[attribute];
      const source = previous && value === previous.last ? previous.source : value;
      const translated = translateUI(source);
      if (value !== translated) element.setAttribute(attribute, translated);
      saved[attribute] = { source, last: translated };
    }
    originalAttributes.set(element, saved);
  }
  for (const element of root.querySelectorAll("[data-ru][data-en]")) {
    const expected = UI_LANG === "en" ? element.dataset.en : element.dataset.ru;
    if (element.textContent !== expected) element.textContent = expected;
  }
}

function applyLanguage(language) {
  UI_LANG = language === "en" ? "en" : "ru";
  translationCache.clear();
  try { localStorage.setItem("fs25_language", UI_LANG); } catch (_) {}
  document.documentElement.lang = UI_LANG;
  document.title = "FS25 Balancer v16.1";
  const button = document.querySelector("#languageSwitch");
  if (button) {
    button.textContent = UI_LANG === "en" ? "🌐 English / RU" : "🌐 Русский / EN";
    button.title = UI_LANG === "en" ? "Switch to Russian" : "Переключить на английский";
  }
  translateTree(document.body);
}

document.addEventListener("DOMContentLoaded", () => {
  const button = document.createElement("button");
  button.id = "languageSwitch"; button.className = "mini";
  document.querySelector(".tb-right").prepend(button);
  button.onclick = async () => {
    if (!S.boot) return;
    const language = UI_LANG === "en" ? "ru" : "en";
    const result = await call("set_config", { ui_lang: language });
    if (!result?.ok) return;
    S.boot.config = result.config;
    const refreshed = await call("boot");
    if (refreshed?.ok === false) return;
    if (refreshed) S.boot = refreshed;
    applyConfigToUI(S.boot.config);
    fillScanTargets(S.boot.scan_categories, S.boot.config.scan_targets);
    S.boot.items.forEach(putItem);
    renderTable(); renderMultiserial(); renderMultList(); renderBrandTabs();
    applyLanguage(language);
    if (S.tourStep >= 0) placeTour();
  };
  applyLanguage(UI_LANG);
  let scheduled = false;
  const observer = new MutationObserver(records => {
    if (scheduled || !records.some(record => !record.target.parentElement?.closest(".logbar, .intro, canvas"))) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; translateTree(document.body); });
  });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  applyLanguage(UI_LANG);
});

const nativeConfirm = window.confirm.bind(window);
window.confirm = text => nativeConfirm(translateUI(String(text)));
