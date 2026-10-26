# -*- coding: utf-8 -*-
"""Расчёт цен: перенос алгоритмов v13 + ретро, комплектации, поля по расстоянию."""

import math
from typing import Any, Dict, List, Optional, Tuple

from core.models import BalancerConfig, ItemSpec, MotorSpec

# ── Категории техники (базовые пороги алгоритма v13) ──
VEHICLE_IGNORED_CATS = {
    "placeables", "farmhouses", "sheds", "silos", "productions",
    "animals", "greenhouses", "tools_placeables", "decorations", "lights",
    "storages", "sellingpoints", "pallets", "fences", "buildings",
    "productionpoints", "beehives", "animalpens",
}

VEHICLE_IGNORED_FN = {
    "storage", "trigger", "fence", "gate", "building", "placeable",
    "house", "silo", "tank", "water", "sell", "buy", "pallet", "bag",
    "bale", "object", "decor", "light", "sign", "generator", "workshop",
    "construction", "foundation", "greenhouse", "stable", "shed",
    "production", "bee", "hive", "animal", "pen",
}

PLACEABLE_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "silos":           {"label": "Силос / Хранилище",       "base": 18000, "mult": 1.0},
    "storages":        {"label": "Склад",                    "base": 12000, "mult": 0.9},
    "liquidstorages":  {"label": "Ёмкость для жидкостей",    "base": 8000,  "mult": 0.8},
    "productions":     {"label": "Производство",             "base": 45000, "mult": 1.3},
    "productionpoints": {"label": "Производственная точка",  "base": 35000, "mult": 1.2},
    "animalpens":      {"label": "Загон для животных",       "base": 28000, "mult": 1.1},
    "animals":         {"label": "Животноводство",           "base": 22000, "mult": 1.0},
    "farmhouses":      {"label": "Фермерский дом",           "base": 55000, "mult": 1.2},
    "sheds":           {"label": "Ангар / Навес",            "base": 15000, "mult": 0.85},
    "buildings":       {"label": "Строение",                 "base": 20000, "mult": 1.0},
    "decorations":     {"label": "Декорации",                "base": 800,   "mult": 0.5},
    "fences":          {"label": "Ограждения",               "base": 400,   "mult": 0.3},
    "lights":          {"label": "Освещение",                "base": 500,   "mult": 0.4},
    "sellingpoints":   {"label": "Точка продажи",            "base": 30000, "mult": 1.0},
    "greenhouses":     {"label": "Теплица",                  "base": 18000, "mult": 0.95},
    "beehives":        {"label": "Пасека / Ульи",            "base": 5000,  "mult": 0.6},
    "placeables":      {"label": "Размещаемый объект",       "base": 10000, "mult": 0.8},
    "misc":            {"label": "Прочее",                   "base": 5000,  "mult": 0.7},
}

PLACEABLE_SIZE_KEYWORDS = {
    "small": 0.6, "medium": 1.0, "large": 1.6, "xl": 2.2, "xxl": 3.0,
    "big": 1.5, "huge": 2.5, "tiny": 0.4, "mega": 3.5,
}

# ── Множители для зданий (v16) ──
# Производительность линии: cyclesPerHour * выход за цикл (л/час).
# Мягкая зависимость по корню, чтобы один «в 10 раз быстрее» не давал цену x10.
PROD_THROUGHPUT_REF = 2000.0     # л/час — около этого линия считается «нормальной»
PROD_MULT_MIN, PROD_MULT_MAX = 0.5, 3.0
# Точка продажи: множитель по числу принимаемых типов продукции.
GOODS_BASE, GOODS_STEP, GOODS_MULT_MIN, GOODS_MULT_MAX = 0.80, 0.05, 0.6, 2.5
# Сколько «часовых» расходов закладываем в цену здания
UPKEEP_IN_PRICE = 0.4

FUEL_FILL_TYPES = {
    "diesel", "def", "adblue", "electriccharge", "methane", "air",
    "oil", "coolant", "unknown",
}

FIELD_BASE_PRICE_PER_HA = 4800.0
SHOP_PLACEABLE_HINTS = {"sellingspoint", "sellingpoint", "shop", "farm", "garage", "workshop"}


def rub_from_xml(price_xml: float, cfg: BalancerConfig) -> int:
    """Рубли из числа, которое ляжет в <price>: ₽ напрямую или €-база × курс."""
    v = float(price_xml or 0)
    return clean_round(v if cfg.write_direct_rubles else v * cfg.exchange_rate)


def clean_round(val: float) -> int:
    val = max(50.0, float(val))
    if val < 500:     return int(round(val / 10) * 10)
    if val < 2500:    return int(round(val / 50) * 50)
    if val < 15000:   return int(round(val / 100) * 100)
    if val < 100000:  return int(round(val / 500) * 500)
    if val < 1000000: return int(round(val / 1000) * 1000)
    return int(round(val / 5000) * 5000)


def calc_vehicle_price(cat: str, hp: float, spd: float, cap: float,
                       ww: float, nhp: float, bm: float, gs: float) -> float:
    """Базовая цена техники в EUR (алгоритм v13, без_country_scale)."""
    c = (cat or "misc").lower()

    if any(k in c for k in ("handtool", "chainsaw", "tool")):
        return max(80.0, (150 + cap * 0.5 + ww * 200) * bm * gs)

    is_light = ("truck" in c and 0 < hp <= 175 and cap <= 9500) or "car" in c or "vehicles" in c

    if is_light:
        ehp = hp if hp > 0 else 110
        espd = max(0.0, (spd if spd > 0 else 100) - 80)
        raw = 11500 + ehp * 135 + espd * 115 + cap * 1.75
    elif "truck" in c:
        ehp = hp if hp > 0 else 300
        espd = max(0.0, (spd if spd > 0 else 80) - 65)
        cb = 16000 if cap <= 0 else 0
        raw = 24000 + ehp * 255 + cap * 1.15 + espd * 190 + cb
    elif "tractor" in c:
        ehp = hp if hp > 0 else 120
        espd = max(0.0, (spd if spd > 0 else 35) - 30)
        raw = 9500 + math.pow(ehp, 1.18) * 238 + espd * 340
    elif any(k in c for k in ("harvester", "beet", "potato", "cotton",
                              "sugarcane", "grape", "olive", "mowervehicle")):
        if hp > 0:
            espd = max(0.0, (spd if spd > 0 else 25) - 20)
            raw = 62000 + hp * 515 + cap * 5.2 + espd * 450
        else:
            raw = 28000 + nhp * 220 + cap * 3.8 + ww * 4500
    else:
        if hp > 0:
            raw = 14000 + hp * 240 + cap * 1.2
        elif cap > 0 or ww > 0:
            raw = 3500 + cap * 1.15 + ww * 2600 + nhp * 95
        else:
            raw = 4500

    return max(350.0, raw * bm * gs)


def throughput_multiplier(throughput: float) -> float:
    """Мягкий множитель производительности линии: sqrt(факт / эталон), в коридоре 0.5..3."""
    tp = max(0.0, float(throughput or 0.0))
    if tp <= 0:
        return 1.0
    return min(PROD_MULT_MAX, max(PROD_MULT_MIN, math.sqrt(tp / PROD_THROUGHPUT_REF)))


def goods_multiplier(count: int) -> float:
    """Множитель точки продажи по числу принимаемых типов продукции."""
    n = max(0, int(count or 0))
    if n <= 0:
        return 1.0
    return min(GOODS_MULT_MAX, max(GOODS_MULT_MIN, GOODS_BASE + GOODS_STEP * n))


def chain_step(label: str, detail: str, value: float = 0.0,
               effect: str = "", running: float = 0.0) -> Dict[str, Any]:
    """Один шаг разбора цены: что применили, к чему это привело."""
    return {"label": label, "detail": detail, "value": round(float(value or 0.0), 4),
            "effect": effect, "running": round(float(running or 0.0), 2)}


def calc_placeable_price_ex(category: str, title: str, filename: str,
                            capacity: float, slots: int, prod_cost: float,
                            k_place: float, gs: float,
                            prod_throughput: float = 0.0, goods_count: int = 0,
                            storage_capacity: float = 0.0, lang: str = "ru") -> Tuple[float, List[Dict[str, Any]]]:
    """Цена здания + честная цепочка разбора (видно пользователю всегда).

    Вместимость наружных резервуаров и внутренних складов завода не суммируется дважды:
    берётся максимум, чтобы «склад при заводе» не удваивал бонус.
    """
    from core.i18n import category_label as _cat_label, t as _t

    cat_key = str(category or "misc").strip().lower()
    cat_info = PLACEABLE_CATEGORIES.get(cat_key, PLACEABLE_CATEGORIES["misc"])
    base = float(cat_info["base"])
    cat_mult = float(cat_info["mult"])

    size_lbl, size_mult = detect_placeable_size(title, filename)
    eff_cap = max(float(capacity or 0.0), float(storage_capacity or 0.0))

    cap_bonus = math.log2(max(1.0, eff_cap / 1000)) * 2500 if eff_cap > 0 else 0.0
    slot_bonus = max(0, int(slots or 0)) * 800
    prod_bonus = max(0.0, float(prod_cost or 0.0)) * UPKEEP_IN_PRICE
    thr_mult = throughput_multiplier(prod_throughput)
    goods_mult = goods_multiplier(goods_count)

    sum_part = base + cap_bonus + slot_bonus + prod_bonus
    running = sum_part
    steps: List[Dict[str, Any]] = [
        chain_step(_t("bd.base", lang),
                   "%s · %s" % (_cat_label(cat_key, lang, cat_key), "{0:,.0f}".format(base)),
                   base, "+base", running),
    ]
    if cap_bonus > 0:
        running += cap_bonus
        steps.append(chain_step(_t("bd.storecap", lang),
                                "{0:,.0f} л".format(eff_cap), cap_bonus, "+", running))
    if slot_bonus > 0:
        running += slot_bonus
        steps.append(chain_step(_t("spec.slots", lang),
                                "%d" % slots, slot_bonus, "+", running))
    if prod_bonus > 0:
        running += prod_bonus
        steps.append(chain_step(_t("bd.upkeep", lang),
                                "{0:,.0f}/ч".format(prod_cost), prod_bonus, "+", running))

    running = sum_part * cat_mult
    if abs(cat_mult - 1.0) > 1e-6:
        steps.append(chain_step(_t("cat." + cat_key, lang), "x", cat_mult, "x", running))

    if abs(size_mult - 1.0) > 1e-6:
        running *= size_mult
        steps.append(chain_step(_t("bd.size", lang), size_lbl or "", size_mult, "x", running))

    if abs(thr_mult - 1.0) > 1e-6:
        running *= thr_mult
        steps.append(chain_step(_t("bd.cycles", lang),
                                "{0:,.0f} л/ч".format(prod_throughput), thr_mult, "x", running))

    if abs(goods_mult - 1.0) > 1e-6:
        running *= goods_mult
        steps.append(chain_step(_t("bd.goods", lang), str(int(goods_count or 0)),
                                goods_mult, "x", running))

    if abs(k_place - 1.0) > 1e-6:
        running *= k_place
        steps.append(chain_step(_t("bd.k_placeable", lang), "", k_place, "x", running))

    if abs(gs - 1.0) > 1e-6:
        running *= gs
        steps.append(chain_step(_t("bd.diff", lang), "scale", gs, "x", running))

    return max(200.0, running), steps


def calc_placeable_price(category: str, title: str, filename: str,
                         capacity: float, slots: int, prod_cost: float,
                         k_place: float, gs: float,
                         prod_throughput: float = 0.0, goods_count: int = 0,
                         storage_capacity: float = 0.0) -> float:
    """Совместимость со старыми вызовами: только цена, без цепочки."""
    price, _steps = calc_placeable_price_ex(category, title, filename, capacity, slots,
                                            prod_cost, k_place, gs, prod_throughput,
                                            goods_count, storage_capacity)
    return price


def detect_placeable_size(title: str, filename: str) -> Tuple[str, float]:
    combined = f"{title} {filename}".lower()
    for kw, mult in sorted(PLACEABLE_SIZE_KEYWORDS.items(), key=lambda x: -x[1]):
        if kw in combined:
            return kw.capitalize(), mult
    return "", 1.0


def field_price(area_ha: float, distance_km: Optional[float],
                cfg: BalancerConfig) -> float:
    """Цена поля: база по площади × множитель близости к магазину.

    distance_km is None  -> дистанция неизвестна, бонус не применяется.
    """
    base = max(1500.0, float(area_ha) * FIELD_BASE_PRICE_PER_HA)
    if not cfg.adjust_field_prices or distance_km is None:
        return base * cfg.k_field * cfg.global_difficulty_scale
    max_d = max(0.05, float(cfg.field_max_distance))
    spread = min(1.0, max(0.0, float(cfg.field_distance_spread)))
    closeness = 1.0 - min(1.0, max(0.0, float(distance_km)) / max_d)
    dist_mult = 1.0 + spread * closeness
    return base * dist_mult * cfg.k_field * cfg.global_difficulty_scale


def apply_item_multipliers(base_eur: float, country_mult: float,
                           is_retro: bool, cfg: BalancerConfig) -> Tuple[float, float, float]:
    """Цена = база * коэф.страны * коэф.ретро. Возвращает (цена, k_country, k_retro)."""
    k_retro = float(cfg.k_retro) if (is_retro and cfg.retro_enabled) else 1.0
    price = base_eur * country_mult * k_retro
    return price, country_mult, k_retro


def finish_chain(inner: List[Dict[str, Any]], base_eur: float, country_mult: float,
                 k_retro: float, is_retro: bool, xml_factor: float, new_xml: int,
                 new_rub: int, lang: str = "ru", manual: bool = False) -> List[Dict[str, Any]]:
    """Достраивает разбор цены: страна → ретро → округление → запись в XML → рубли."""
    from core.i18n import t as _t
    steps = list(inner or [])
    if manual:
        return steps + [chain_step(_t("bd.manual", lang), "", float(new_xml), "=", new_xml)]
    steps += multiplier_chain_steps(base_eur, country_mult, is_retro, k_retro, lang)
    steps.append(chain_step(_t("bd.round", lang), "x{0:,.2f}".format(float(xml_factor or 1.0)),
                            float(xml_factor or 1.0), "=", float(new_xml)))
    steps.append(chain_step(_t("bd.to_rub", lang), "", 0.0, "=>", float(new_rub)))
    return steps


def multiplier_chain_steps(base_eur: float, country_mult: float, is_retro: bool,
                           k_retro: float, lang: str = "ru") -> List[Dict[str, Any]]:
    """Шапки «страна» и «ретро» для разбора цены (общие для техники и зданий)."""
    from core.i18n import t as _t
    steps: List[Dict[str, Any]] = []
    run = float(base_eur)
    if abs(float(country_mult) - 1.0) > 1e-6:
        run *= float(country_mult)
        steps.append(chain_step(_t("bd.country", lang), "x", country_mult, "x", run))
    if is_retro and float(k_retro or 1.0) != 1.0:
        run *= float(k_retro)
        steps.append(chain_step(_t("bd.retro", lang), "", k_retro, "x", run))
    return steps


def motor_price_for_delta(base_eur: float, hp_delta: float, bm: float,
                          xm: float, is_retro: bool, cfg: BalancerConfig) -> int:
    """Наценка комплектации: дельта л.с. + 2% базы (как в balance_configs v13)."""
    is_retro = bool(is_retro) and cfg.retro_enabled
    if hp_delta > 0:
        p = hp_delta * 215 * bm + base_eur * 0.02
    else:
        p = base_eur * 0.045
    if is_retro:
        p *= float(cfg.k_retro)
    return 0 if p <= 0 else clean_round(p * xm)


def wear_for_item(is_retro: bool, cfg: BalancerConfig) -> float:
    """Коэффициент износа ретро: повышает ежедневное содержание."""
    return 1.0 + float(cfg.retro_wear) if (is_retro and cfg.retro_enabled) else 1.0
