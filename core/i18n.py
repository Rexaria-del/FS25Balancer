# -*- coding: utf-8 -*-
"""Словарь локализации RU/EN для строк, которые формирует Python-слой.

Хром интерфейса (подписи кнопок, обучение, подсказки) переводит web/js/i18n.js.
Здесь — только то, что приходит из бэкенда: категории, подгруппы зданий,
названия стран, поля ТТХ, источник решения, режимы сканирования.
"""

from typing import Any, Dict, List, Optional

LANGS: List[str] = ["ru", "en"]
DEFAULT_LANG = "ru"

# key -> (RU, EN)
STRINGS: Dict[str, tuple] = {
    # ── подгруппы зданий ──
    "sg.production":  ("Производства", "Productions"),
    "sg.selling":     ("Точки продажи", "Sales points"),
    "sg.storage":     ("Хранение", "Storage"),
    "sg.animals":     ("Животноводство", "Livestock"),
    "sg.farm":        ("Фермы и постройки", "Farms & buildings"),
    "sg.decor":       ("Декор и освещение", "Decor & lights"),
    "sg.other":       ("Прочие объекты", "Other placeables"),
    # ── категории зданий ──
    "cat.silos":            ("Силос / Хранилище", "Silo / storage"),
    "cat.storages":         ("Склад", "Warehouse"),
    "cat.liquidstorages":   ("Ёмкость для жидкостей", "Liquid tank"),
    "cat.productions":      ("Производство", "Production plant"),
    "cat.productionpoints": ("Производственная точка", "Production point"),
    "cat.animalpens":       ("Загон для животных", "Animal pen"),
    "cat.animals":          ("Животноводство", "Livestock"),
    "cat.farmhouses":       ("Фермерский дом", "Farmhouse"),
    "cat.sheds":            ("Ангар / Навес", "Shed / canopy"),
    "cat.buildings":        ("Строение", "Building"),
    "cat.decorations":      ("Декорации", "Decorations"),
    "cat.fences":           ("Ограждения", "Fences"),
    "cat.lights":           ("Освещение", "Lighting"),
    "cat.sellingpoints":    ("Точка продажи", "Sales point"),
    "cat.greenhouses":      ("Теплица", "Greenhouse"),
    "cat.beehives":         ("Пасека / Ульи", "Apiary / hives"),
    "cat.placeables":       ("Размещаемый объект", "Placeable"),
    "cat.misc":             ("Прочее", "Misc"),
    "cat.field":            ("Поле", "Field"),
    # ── категории техники (типичные из XML модов) ──
    "vcat.tractors":            ("Тракторы", "Tractors"),
    "vcat.harvesters":          ("Комбайны", "Harvesters"),
    "vcat.forwarders":          ("Форвардеры", "Forwarders"),
    "vcat.skidders":            ("Скердеры", "Skidders"),
    "vcat.excavators":          ("Экскаваторы", "Excavators"),
    "vcat.wheelLoaders":        ("Погрузчики", "Wheel loaders"),
    "vcat.trucks":              ("Грузовики", "Trucks"),
    "vcat.trailers":            ("Прицепы", "Trailers"),
    "vcat.vehicles":            ("Транспорт", "Vehicles"),
    "vcat.tools":               ("Навесное оборудование", "Implements"),
    "vcat.cultivators":         ("Культиваторы", "Cultivators"),
    "vcat.ploughs":             ("Плуги", "Ploughs"),
    "vcat.seeders":             ("Сеялки", "Seeders"),
    "vcat.sprayers":            ("Опрыскиватели", "Sprayers"),
    "vcat.mowers":              ("Косилки", "Mowers"),
    "vcat.tedders":             ("Грабли-ворошилки", "Tedders"),
    "vcat.combine":             ("Комбайны", "Harvesters"),
    # ── режимы сканирования ──
    "scan.vehicle":   ("Техника", "Vehicles"),
    "scan.placeable": ("Здания и объекты", "Buildings & placeables"),
    "scan.field":     ("Поля", "Fields"),
    "scan.all":       ("Всё (техника + здания + поля)", "Everything (vehicles + buildings + fields)"),
    # ── группы стран ──
    "grp.CIS":   ("СНГ", "CIS"),
    "grp.WEST":  ("Европа", "Europe"),
    "grp.US":    ("Америка", "Americas"),
    "grp.ASIA":  ("Азия", "Asia"),
    "grp.OTHER": ("Прочие", "Other"),
    # ── поля ТТХ ──
    "spec.hp":               ("Мощность двигателя", "Engine power"),
    "spec.max_speed":        ("Максимальная скорость", "Max speed"),
    "spec.capacity":         ("Вместимость", "Capacity"),
    "spec.working_width":    ("Ширина захвата", "Working width"),
    "spec.needed_hp":        ("Требуемая мощность", "Required power"),
    "spec.prod_cycles":      ("Циклов в час", "Cycles per hour"),
    "spec.prod_output":      ("Выход за цикл", "Output per cycle"),
    "spec.prod_input":       ("Расход сырья за цикл", "Input per cycle"),
    "spec.prod_cost_month":  ("Расходы в месяц", "Monthly running costs"),
    "spec.prod_cost_hour":   ("Расходы в час", "Hourly running costs"),
    "spec.storage_capacity": ("Вместимость склада завода", "Plant storage capacity"),
    "spec.goods_count":      ("Принимаемых товаров", "Accepted products"),
    "spec.production_cost":  ("Расходы на производство", "Production running costs"),
    "spec.slots":            ("Места (слоты/стенды)", "Slots / stands"),
    "unit.hp":        ("л.с.", "hp"),
    "unit.kmh":       ("км/ч", "km/h"),
    "unit.liter":     ("л", "l"),
    "unit.meter":     ("м", "m"),
    "unit.cph":       ("цикл/ч", "cycles/h"),
    "unit.percycle":  ("л/цикл", "l/cycle"),
    "unit.rub_month": ("/мес", "/month"),
    "unit.rub_hour":  ("/час", "/hour"),
    "unit.pcs":       ("шт", "pcs"),
    # ── источник решения (колонка «Источник») ──
    "src.dict":      ("Словари", "Brand dictionaries"),
    "src.memory":    ("Память", "Learned memory"),
    "src.ai_cache":  ("Кэш ИИ", "AI cache"),
    "src.ai":        ("ИИ-классификация", "AI classification"),
    "src.ai_prefix": ("ИИ: {0}", "AI: {0}"),
    "src.brand_fix": ("Здание: бренд не указан", "Building: brand not set"),
    "src.field":     ("Поле", "Field"),
    "src.field_prefix": ("Поле: {0}", "Field: {0}"),
    "src.field_noarea":   ("площадь не определена", "area not detected"),
    "src.field_noshop":   ("нет координат магазина/поля", "shop/field coordinates missing"),
    "src.cheat_dict":     ("словарь-пороги", "threshold rules"),
    "src.cheat_ai":       ("ИИ", "AI"),
    # ── разбор цены ──
    "bd.base":      ("Базовая цена по классу", "Class base price"),
    "bd.size":      ("Поправка на размер", "Size adjustment"),
    "bd.brand":     ("Коэффициент бренда", "Brand multiplier"),
    "bd.country":   ("Коэффициент страны", "Country multiplier"),
    "bd.retro":     ("Коэффициент ретро", "Retro multiplier"),
    "bd.cycles":    ("Производительность (циклы/ч)", "Throughput (cycles/h)"),
    "bd.storecap":  ("Вместимость складов завода", "Plant storage capacity"),
    "bd.upkeep":    ("Расходы на линию", "Line running costs"),
    "bd.goods":     ("Число принимаемых товаров", "Accepted product types"),
    "bd.field_area": ("Площадь поля", "Field area"),
    "bd.field_dist": ("Близость к магазину", "Distance to shop"),
    "bd.round":     ("Округление до красивого числа", "Rounding to clean number"),
    "bd.diff":      ("Общий масштаб сложности", "Global difficulty scale"),
    "bd.manual":    ("Цена задана вручную", "Manual price"),
    "bd.to_rub":    ("Перевод в рубли по курсу", "Converted to RUB at rate"),
    "bd.k_placeable": ("Коэффициент зданий", "Building multiplier"),
    "bd.class_obj":   ("Класс объекта", "Object class"),
    "bd.class_veh":   ("Класс техники", "Vehicle class"),
    "bd.specs_calc":  ("Характеристики для расчёта", "Specs used in the calculation"),
    "bd.base_ttx":    ("База по ТТХ", "Base from specs"),
    "bd.base_area":   ("База по площади", "Base from area"),
    "bd.area_field":  ("Площадь поля", "Field area"),
    "bd.area_none":   ("не определена (ручной ввод)", "not detected (enter manually)"),
    "bd.per_ha":      ("{0} € за га, минимум 1500 €", "{0} EUR per ha, min 1500 EUR"),
    "bd.no_distance": ("нет дистанции", "distance missing"),
    "bd.retro_on":    ("Износ ретро (dailyUpkeep)", "Retro wear (dailyUpkeep)"),
    "bd.retro_off":   ("помечено, но режим ретро выключен в настройках",
                       "flagged, but retro mode is off in settings"),
    "bd.result_rub":  ("Итог в рублях", "Total in rubles"),
    "bd.manual_line": ("Ручная цена (переопределяет расчёт)", "Manual price (overrides calc)"),
    "bd.motor_pick":  ("Выбрана комплектация (переопределяет расчёт)", "Config selected (overrides calc)"),
    "bd.xml_rub":     ("₽ напрямую", "rubles written directly"),
    "bd.xml_eur":     ("€-база · игра сама домножит на {0}",
                       "EUR base · the game multiplies by {0}"),
    "bd.motor":       ("Комплектация «{0}»", 'Motor config "{0}"'),
    "bd.xml_write": ("Что ляжет в файл мода", "What goes into the mod file"),
    "bd.motor_val":   ("{0} л.с. · +{1} = {2}", "{0} hp · +{1} = {2}"),
    "bd.lines":       ("Линии производства", "Production lines"),
    "bd.line":        ("Линия «{0}»", 'Line "{0}"'),
    "bd.line_val":    ("{0} цикл/ч · выпуск {1} л · сырьё {2} л",
                       "{0} cycles/h · output {1} l · input {2} l"),
    "bd.rub_equiv":   ("₽-эквивалент {0}", "RUB equivalent {0}"),
    "sent.country":   ("Коэф. страны «{0}»", 'Country multiplier "{0}"'),
    "bd.k_field":   ("Коэффициент полей", "Field multiplier"),
    # ── читерский детект ──
    "cheat.hp":       ("Мощность {0} л.с. выше порога {1}", "Power {0} hp exceeds limit {1}"),
    "cheat.speed":    ("Скорость {0} км/ч выше порога {1}", "Speed {0} km/h exceeds limit {1}"),
    "cheat.width":    ("Ширина захвата {0} м выше порога {1}", "Working width {0} m exceeds limit {1}"),
    "cheat.capacity": ("Вместимость {0} л выше порога {1}", "Capacity {0} l exceeds limit {1}"),
    "cheat.cycles":   ("{0} циклов/ч выше порога {1}", "{0} cycles/h exceeds limit {1}"),
    "cheat.price":    ("Цена в файле {0} при расчётной {1} — подозрительно занищена/завышена",
                       "File price {0} vs computed {1} — suspiciously off"),
    "cheat.ai":       ("ИИ назвал мод неадекватным: {0}", "AI flagged the mod as unreasonable: {0}"),
    "cheat.need_hp":  ("Требуемая мощность {0} л.с. выше порога {1}", "Required power {0} hp exceeds limit {1}"),
    # ── источник решения: уточнения ──
    "src.brand_in":   ("Бренд: {0}", "Brand: {0}"),
    "src.no_pool":    ("Нет выбранных стран", "No countries selected"),
    "src.default":    ("По умолчанию", "Default country"),
    "src.out_of_pool": ("Вне пула: {0}", "Outside pool: {0}"),
    "sent.unknown":   ("Неизвестно", "Unknown"),
    "sent.review":    ("Проверить", "Needs review"),
    "sent.none":      ("Без страны", "No country"),
    # ── железо / рекомендация модели ──
    "hw.ram":     ("ОЗУ {0} ГБ", "RAM {0} GB"),
    "hw.gpu":     (", {0} ({1} ГБ VRAM)", ", {0} ({1} GB VRAM)"),
    "hw.nogpu":   (", дискретной GPU нет — расчёт на ОЗУ", ", no discrete GPU — sized by RAM"),
    "hw.offline": ("Ollama не запущена", "Ollama is not running"),
    "hw.nodisk":  ("Накопитель не определён", "Storage not detected"),
    "unit.gb":    ("ГБ", "GB"),
    "unit.mb":    ("МБ", "MB"),
    "unit.kb":    ("КБ", "KB"),
    # ── читерство: статус ──
    "cheat.off":  ("Детект выключен", "Detection off"),
    "cheat.nothing": ("Детект включён, но порог не задан и ИИ выключен — ничего не помечается",
                      "Detection is on but no threshold is set and AI is off — nothing gets flagged"),
    "src.no_goods":  ("не определено число товаров точки продажи",
                      "sales point product count not detected"),
    "src.field_short": ("Поле", "Field"),
    "cfg.scan":      ("Что сканируем", "What to scan"),
    # ── подписи колонки «Хар-ки» (строка ТТХ позиции) ──
    "unit.ha":    ("га", "ha"),
    "unit.km":    ("км", "km"),
    "lbl.retro":  ("Ретро", "Retro"),
    "lbl.cheat":  ("ЧИТЕР?", "CHEAT?"),
    "lbl.hp":     ("{0} л.с.", "{0} hp"),
    "lbl.cap":    ("{0} л", "{0} l"),
    "lbl.spd":    ("{0} км/ч", "{0} km/h"),
    "lbl.width":  ("{0} м", "{0} m"),
    "lbl.cycles": ("{0} ц/ч", "{0} cyc/h"),
    "lbl.out":    ("выпуск {0} л/цикл", "output {0} l/cycle"),
    "lbl.in":     ("сырьё {0} л/цикл", "input {0} l/cycle"),
    "lbl.store":  ("склад {0} л", "storage {0} l"),
    "lbl.goods":  ("товаров: {0}", "products: {0}"),
    "lbl.upkeep": ("расходы {0}/ч", "costs {0}/h"),
    "lbl.slots":  ("{0} слотов", "{0} slots"),
    "lbl.area":   ("{0} га", "{0} ha"),
    "lbl.area_q": ("га ?", "area ?"),
    "lbl.dist":   ("{0} км до магазина", "{0} km to shop"),
    "lbl.dist_q": ("дистанция ?", "distance ?"),
}

# ISO2 -> EN (RU-имя остаётся ключом в базе стран)
COUNTRY_EN: Dict[str, str] = {
    "RU": "Russia", "SU": "USSR", "BY": "Belarus", "UA": "Ukraine", "KZ": "Kazakhstan",
    "UZ": "Uzbekistan", "KG": "Kyrgyzstan", "TJ": "Tajikistan", "TM": "Turkmenistan",
    "AZ": "Azerbaijan", "AM": "Armenia", "GE": "Georgia", "MD": "Moldova",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain", "PT": "Portugal",
    "GB": "United Kingdom", "IE": "Ireland", "NL": "Netherlands", "BE": "Belgium",
    "LU": "Luxembourg", "AT": "Austria", "CH": "Switzerland", "PL": "Poland",
    "CZ": "Czechia", "SK": "Slovakia", "HU": "Hungary", "SI": "Slovenia", "HR": "Croatia",
    "BA": "Bosnia and Herzegovina", "RS": "Serbia", "ME": "Montenegro", "MK": "North Macedonia",
    "AL": "Albania", "GR": "Greece", "BG": "Bulgaria", "RO": "Romania", "LT": "Lithuania",
    "LV": "Latvia", "EE": "Estonia", "SE": "Sweden", "NO": "Norway", "FI": "Finland",
    "DK": "Denmark", "IS": "Iceland", "MT": "Malta", "CY": "Cyprus", "TR": "Turkey",
    "AD": "Andorra", "MC": "Monaco", "SM": "San Marino", "LI": "Liechtenstein",
    "US": "United States", "CA": "Canada", "MX": "Mexico", "GT": "Guatemala",
    "BZ": "Belize", "HN": "Honduras", "SV": "El Salvador", "NI": "Nicaragua",
    "CR": "Costa Rica", "PA": "Panama", "CU": "Cuba", "JM": "Jamaica",
    "HT": "Haiti", "DO": "Dominican Republic", "BS": "Bahamas", "BB": "Barbados",
    "TT": "Trinidad and Tobago", "CO": "Colombia", "VE": "Venezuela", "GY": "Guyana",
    "SR": "Suriname", "EC": "Ecuador", "PE": "Peru", "BO": "Bolivia", "PY": "Paraguay",
    "UY": "Uruguay", "AR": "Argentina", "BR": "Brazil", "CL": "Chile",
    "CN": "China", "JP": "Japan", "KR": "South Korea", "KP": "North Korea",
    "MN": "Mongolia", "IN": "India", "PK": "Pakistan", "BD": "Bangladesh",
    "NP": "Nepal", "BT": "Bhutan", "LK": "Sri Lanka", "MM": "Myanmar", "TH": "Thailand",
    "VN": "Vietnam", "LA": "Laos", "KH": "Cambodia", "MY": "Malaysia", "SG": "Singapore",
    "ID": "Indonesia", "PH": "Philippines", "BN": "Brunei", "TL": "East Timor",
    "IL": "Israel", "PS": "Palestine", "LB": "Lebanon", "SY": "Syria", "IQ": "Iraq",
    "IR": "Iran", "SA": "Saudi Arabia", "YE": "Yemen", "OM": "Oman", "AE": "United Arab Emirates",
    "QA": "Qatar", "BH": "Bahrain", "KW": "Kuwait", "JO": "Jordan",
    "AF": "Afghanistan", "TW": "Taiwan", "HK": "Hong Kong", "MO": "Macau",
    "AU": "Australia", "NZ": "New Zealand", "FJ": "Fiji", "PG": "Papua New Guinea",
    "SB": "Solomon Islands", "VU": "Vanuatu", "WS": "Samoa", "TO": "Tonga",
    "EG": "Egypt", "LY": "Libya", "TN": "Tunisia", "DZ": "Algeria", "MA": "Morocco",
    "SD": "Sudan", "SS": "South Sudan", "ET": "Ethiopia", "ER": "Eritrea", "DJ": "Djibouti",
    "SO": "Somalia", "KE": "Kenya", "UG": "Uganda", "TZ": "Tanzania", "RW": "Rwanda",
    "BI": "Burundi", "CF": "Central African Republic", "TD": "Chad", "NE": "Niger",
    "NG": "Nigeria", "BJ": "Benin", "TG": "Togo", "GH": "Ghana", "CI": "Ivory Coast",
    "LR": "Liberia", "SL": "Sierra Leone", "GN": "Guinea", "GW": "Guinea-Bissau",
    "MR": "Mauritania", "ML": "Mali", "BF": "Burkina Faso", "GM": "Gambia", "SN": "Senegal",
    "GA": "Gabon", "CG": "Republic of the Congo", "CD": "DR Congo", "AO": "Angola",
    "ZM": "Zambia", "ZW": "Zimbabwe", "BW": "Botswana", "NA": "Namibia", "ZA": "South Africa",
    "LS": "Lesotho", "SZ": "Eswatini", "MZ": "Mozambique", "MG": "Madagascar",
    "MW": "Malawi", "KM": "Comoros", "MU": "Mauritius", "SC": "Seychelles",
    "XK": "Kosovo",
}


def norm_lang(lang: Optional[str]) -> str:
    s = str(lang or "").strip().lower()
    return "en" if s.startswith("en") else DEFAULT_LANG


def t(key: str, lang: Optional[str] = None, *args: Any) -> str:
    """Локализованная строка; args подставляются в {0} {1}. Нет ключа — сам ключ."""
    pair = STRINGS.get(key)
    lg = norm_lang(lang)
    raw = ""
    if pair:
        raw = pair[1] if lg == "en" else pair[0]
    if not raw:
        raw = key
    for i, v in enumerate(args):
        raw = raw.replace("{%d}" % i, str(v))
    return raw


def category_label(cat_key: str, lang: Optional[str] = None, fallback: str = "") -> str:
    """Подпись категории здания/техники по её ключу из XML."""
    key = "cat." + str(cat_key or "misc").strip().lower()
    if key in STRINGS:
        return t(key, lang)
    vk = "vcat." + str(cat_key or "").strip()
    if vk in STRINGS:
        return t(vk, lang)
    return fallback or str(cat_key or "")


def subgroup_label(sg: str, lang: Optional[str] = None) -> str:
    return t("sg." + (sg or "other"), lang)


def country_name(name_ru: str, iso2: str = "", lang: Optional[str] = None) -> str:
    """Название страны в нужном языке (EN по ISO2, иначе как в базе)."""
    if norm_lang(lang) != "en" or not iso2:
        return name_ru
    return COUNTRY_EN.get(str(iso2).upper(), name_ru)


def scan_target_label(key: str, lang: Optional[str] = None) -> str:
    return t("scan." + str(key or "all"), lang)


def spec_label(field: str, lang: Optional[str] = None) -> str:
    return t("spec." + str(field), lang)


def spec_unit(unit_key: str, lang: Optional[str] = None) -> str:
    return t("unit." + str(unit_key), lang)


def group_label(group: str, lang: Optional[str] = None) -> str:
    return t("grp." + (group or "OTHER"), lang)


def n1(v: Any) -> str:
    """Число с разделителями разрядов (без локали-зависимых сюрпризов в UI)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    if abs(f - round(f)) < 1e-9:
        return format(int(round(f)), ",").replace(",", " ")
    return ("%.2f" % f).rstrip("0").rstrip(".").replace(".", ",")


def lang_list() -> List[Dict[str, str]]:
    return [{"key": "ru", "label": "Русский"}, {"key": "en", "label": "English"}]
