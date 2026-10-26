# -*- coding: utf-8 -*-
"""Парсинг модов FS25: modDesc, XML техники/зданий/полей, запись цен.

Алгоритмы extract_*/calc_* перенесены из v13 без изменений.
Добавлено: ретро-множитель, несколько комплектаций двигателя, поля.
"""

import copy, hashlib, math, os, re, shutil, struct, threading, time, zipfile, zlib
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.ai import ai_cheat_hint, assess_specs, detect_country_and_retro
from core.ai_state import get_learned, get_spec_patches
from core.cheat import evaluate as cheat_evaluate
from core.i18n import category_label as i18n_category, country_name as i18n_country
from core.i18n import norm_lang, t as i18n_t
from core.specs import apply_patch, present_fields
from core.models import (BalancerConfig, ItemSpec, MotorSpec, ProductionSpec, ScanTarget,
                         subgroup_for)
from core.pricing import (
    FUEL_FILL_TYPES, PLACEABLE_CATEGORIES, VEHICLE_IGNORED_CATS, VEHICLE_IGNORED_FN,
    apply_item_multipliers, calc_placeable_price, calc_placeable_price_ex,
    calc_vehicle_price, chain_step, clean_round, detect_placeable_size, field_price,
    finish_chain, motor_price_for_delta, rub_from_xml, wear_for_item,
)


def pf(val: Optional[str], default: float = 0.0) -> float:
    if not val:
        return default
    try:
        m = re.search(r"[-+]?\d*\.?\d+", str(val).replace(",", "."))
        return float(m.group(0)) if m else default
    except Exception:
        return default


def file_hash(path: str) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                buf = f.read(65536)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except Exception:
        return ""


def localized(elem: Optional[ET.Element], l10n: Dict[str, str]) -> str:
    if elem is None:
        return ""
    for lang in ("ru", "en", "de"):
        ch = elem.find(lang)
        if ch is not None and ch.text and ch.text.strip():
            t = ch.text.strip()
            return l10n.get(t.replace("$l10n_", ""), t) if t.startswith("$l10n_") else t
    if elem.text and elem.text.strip():
        t = elem.text.strip()
        return l10n.get(t.replace("$l10n_", ""), t) if t.startswith("$l10n_") else t
    return ""


def parse_moddesc(xml_bytes: bytes) -> Tuple[List[str], Dict[str, str]]:
    files: List[str] = []
    l10n: Dict[str, str] = {}
    try:
        root = ET.fromstring(xml_bytes)
        for si in root.findall(".//storeItems/storeItem"):
            fn = si.get("xmlFilename")
            if fn:
                files.append(fn.replace("\\", "/").lstrip("/"))
        for te in root.findall(".//l10n/text"):
            name = te.get("name")
            if name:
                ru = te.find("ru")
                en = te.find("en")
                val = (ru.text if ru is not None and ru.text else
                       (en.text if en is not None and en.text else None))
                if val:
                    l10n[name] = val.strip()
    except Exception:
        pass
    return files, l10n


# ── Извлечение ТТХ (v13) ──────────────────────────────────────────────────────

def extract_motor(root: ET.Element) -> Tuple[float, float, List[Tuple[ET.Element, float, float, float]]]:
    """(base_hp, max_speed, [(motorConfigElem, hp, speed, torque), ...])"""
    ss = root.find("./storeData/specs")
    spec_hp = pf(ss.findtext("power")) if ss is not None else 0.0
    spec_spd = pf(ss.findtext("maxSpeed")) if ss is not None else 0.0

    configs: List[Tuple[ET.Element, float, float, float]] = []
    max_spd = 0.0

    for mc in root.findall(".//motorConfigurations/motorConfiguration"):
        hp = pf(mc.get("hp"))
        torque = 0.0
        spd = 0.0
        me = mc.find("motor")
        if me is not None:
            spd = pf(me.get("maxForwardSpeed"))
            if spd > max_spd:
                max_spd = spd
            torque = pf(me.get("torqueScale"))
            if hp <= 0 and torque > 0:
                hp = round(torque * 228.0)
        if hp <= 0:
            hp = spec_hp
        if spd <= 0:
            spd = spec_spd
        configs.append((mc, hp, spd, torque))

    base_hp = configs[0][1] if configs else spec_hp
    if base_hp <= 0:
        base_hp = spec_hp
    return base_hp, (spec_spd if spec_spd > 0 else max_spd), configs


def cargo_cap(fu_elem: ET.Element) -> float:
    total = 0.0
    for fu in fu_elem.findall(".//fillUnit"):
        ft = (fu.get("fillTypes") or "").lower().split()
        fc = (fu.get("fillTypeCategories") or "").lower().split()
        if ft and all(f in FUEL_FILL_TYPES for f in ft):
            continue
        if "slurrytank" not in fc and ft and ("diesel" in ft or "def" in ft) and len(ft) <= 2:
            continue
        c = pf(fu.get("capacity"))
        if c > 0:
            total += c
    return total


def extract_caps(root: ET.Element) -> Tuple[float, List[Tuple[ET.Element, float]]]:
    ss = root.find("./storeData/specs")
    spec_c = pf(ss.findtext("capacity")) if ss is not None else 0.0
    configs: List[Tuple[ET.Element, float]] = []
    for fuc in root.findall(".//fillUnitConfigurations/fillUnitConfiguration"):
        configs.append((fuc, cargo_cap(fuc)))
    base = configs[0][1] if configs else spec_c
    if base <= 0:
        base = spec_c
    return base, configs


def extract_placeable_data(root: ET.Element) -> Tuple[float, int, float]:
    cap = 0.0
    for se in root.findall(".//storages/storage"):
        for n in se.findall("node"):
            c = pf(n.get("capacity"))
            if c > 0:
                cap += c
    if cap <= 0:
        for fu in root.findall(".//fillUnit"):
            c = pf(fu.get("capacity"))
            if c > 0:
                cap += c
    if cap <= 0:
        ss = root.find("./storeData/specs")
        if ss is not None:
            cap = ss and pf(ss.findtext("capacity"))

    slots = len(root.findall(".//slots/slot"))
    if slots == 0:
        slots = len(root.findall(".//stalls/stall"))

    prod = sum(max(pf(line.get("costsPerActiveHour")),
                   pf(line.get("costsPerActiveMonth")) / 24)
               for line in root.findall(".//productions/production"))

    return cap, slots, prod


def _capacity_of(el: ET.Element) -> float:
    """Вместимость из атрибута capacity ИЛИ дочернего <capacity> — обе формы в модах."""
    v = pf(el.get("capacity"))
    if v <= 0:
        c = el.find("capacity")
        if c is not None:
            v = pf(c.text)
    return max(0.0, v)


def _attr_num(el: ET.Element, *names: str) -> float:
    """Числовой атрибут без учёта регистра (моды пишут и costsPerActiveHour, и costPerHour)."""
    low = {str(k).lower(): v for k, v in el.attrib.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None:
            f = pf(v)
            if f > 0:
                return f
    return 0.0


def _set_attr_num(element: ET.Element, attribute: str, value: float) -> bool:
    if element.get(attribute) is not None and pf(element.get(attribute)) == float(value):
        return False
    element.set(attribute, "{:g}".format(value))
    return True


def _prod_amount(el: ET.Element) -> float:
    return max(0.0, _attr_num(el, "amount", "amountLiter", "capacity", "value"))


def _prod_name(el: ET.Element) -> str:
    for a in ("product", "fillType", "fillType", "fillTypes", "name"):
        v = (el.get(a) or "").strip()
        if v:
            return v
    return ""


def extract_production_specs(root: ET.Element, l10n: Dict[str, str]) -> List[ProductionSpec]:
    """Все блоки <production>: циклы/ч, сырьё и выпуск за цикл, расходы, свои склады."""
    out: List[ProductionSpec] = []
    nodes = root.findall(".//productions/production") or root.findall(".//production")
    for i, pr in enumerate(nodes):
        title = (pr.get("name") or "").strip()
        loc = localized(pr.find("name"), l10n)
        if loc:
            title = loc
        if title.startswith("$l10n") or title.startswith("$l100"):
            title = ""
        ins = list(pr.findall("input")) + [e for g in pr.findall("inputs") for e in g.findall("input")]
        outs = (list(pr.findall("output")) +
                [e for g in pr.findall("outputs") for e in g.findall("output")])
        st = 0.0
        for se in list(pr.findall(".//storages/storage")) + list(pr.findall("./storage")):
            st += _capacity_of(se)
            for n in se.findall("node"):
                st += max(0.0, pf(n.get("capacity")))
        out.append(ProductionSpec(
            index=i, title=title,
            cycles_per_hour=_attr_num(pr, "cyclesPerHour", "cyclesperhour", "cyclePerHour"),
            input_amount=round(sum(_prod_amount(e) for e in ins), 2),
            output_amount=round(sum(_prod_amount(e) for e in outs), 2),
            costs_per_active_hour=_attr_num(pr, "costsPerActiveHour", "costPerActiveHour"),
            costs_per_active_month=_attr_num(pr, "costsPerActiveMonth", "costPerActiveMonth"),
            storage_capacity=round(st, 2),
            inputs=[{"product": _prod_name(e), "amount": round(_prod_amount(e), 2)} for e in ins],
            outputs=[{"product": _prod_name(e), "amount": round(_prod_amount(e), 2)} for e in outs],
        ))
    return out


def extract_plant_storage(root: ET.Element) -> float:
    """Вместимость внутренних складов здания (storages/storage, включая node-ячейки)."""
    total = 0.0
    for se in root.findall(".//storage"):
        capacities = se.findall("capacity")
        total += sum(max(0.0, pf(cap.get("capacity") or cap.text)) for cap in capacities) if capacities else _capacity_of(se)
        for n in se.findall("node"):
            total += max(0.0, pf(n.get("capacity")))
    return max(0.0, round(total, 2))


GOODS_IGNORE = set(x.lower() for x in FUEL_FILL_TYPES) | {
    "unkown", "none", "true", "false", "all", "everything", "pallet", "bale"}


def count_accepted_goods(root: ET.Element) -> int:
    """Сколько разных типов продукции позиция принимает (нужно для точек продажи)."""
    toks = set()
    for el in root.iter():
        tag = str(el.tag).lower()
        if not any(k in tag for k in ("sell", "fill", "input", "storage", "trigger", "slot")):
            continue
        for a in ("fillTypes", "fillType", "product", "products", "type", "value", "name"):
            for tok in re.split(r"[,;\s]+", (el.get(a) or "")):
                tok = tok.strip().lower()
                if len(tok) >= 3 and tok not in GOODS_IGNORE and not tok.startswith("$"):
                    toks.add(tok)
    return len(toks)


def is_placeable_xml(root: ET.Element, category: str, filename: str) -> bool:
    if root.tag == "placeable":
        return True
    if category.lower() in PLACEABLE_CATEGORIES:
        return True
    fn_l = filename.lower()
    hints = {"placeable", "building", "silo", "storage", "production",
             "greenhouse", "shed", "house", "fence", "beehive",
             "animalpens", "sellingpoint"}
    return any(h in fn_l for h in hints)


def is_field_xml(root: ET.Element, category: str, filename: str) -> bool:
    fn_l = filename.lower()
    if root.tag in ("field", "fields") or "field" in category.lower() or "field" in fn_l:
        return True
    return root.find(".//fieldArea") is not None and pf(root.findtext(".//price"), 0) > 0


def extract_field_data(root: ET.Element) -> Tuple[float, Optional[Tuple[float, float]], bool]:
    """(площадь_га, координата_XZ, площадь_распознана)

    Площадь берётся из явных атрибутов поля; если значение не найдено,
    возвращается (0.0, coord, False) — строка помечается на ручную проверку.
    """
    area_raw = 0.0
    found = False
    for el in root.iter():
        tag = el.tag.lower()
        if tag not in ("field", "fieldarea", "filltypearea", "terrain", "terrainchunk"):
            continue
        for attr in ("area", "areaInHa", "size", "hectares", "surfaceArea"):
            v = pf(el.get(attr))
            if v > 0:
                area_raw = max(area_raw, v)
                found = True
        t = el.find("area")
        if t is not None:
            v = pf(t.text)
            if v > 0:
                area_raw = max(area_raw, v)
                found = True

    coord: Optional[Tuple[float, float]] = None
    for el in root.iter():
        raw = el.get("position") or el.get("translation") or ""
        if not raw:
            continue
        nums = re.findall(r"[-+]?\d*\.?\d+", raw)
        if len(nums) >= 3:
            coord = (float(nums[0]), float(nums[2]))
            break
        if len(nums) == 2:
            coord = (float(nums[0]), float(nums[1]))
            break

    # FS хранит площадь в м2: 1 га = 10 000 м2. Порог отделяет га от м2.
    area_ha = (area_raw / 10000.0) if area_raw > 20000 else area_raw
    return area_ha, coord, found

# ── Обработка одного XML ------------------------------------------------------

def _set_num(el: ET.Element, value: Any) -> bool:
    """Пишет число, только если оно реально меняется (иначе архив пересобирается впустую)."""
    want = str(int(round(float(value))))
    if (el.text or "").strip() == want:
        return False
    el.text = want
    return True


def process_xml_root(root: ET.Element, rel_path: str, mod_name: str,
                     l10n: Dict[str, str], cfg: BalancerConfig,
                     overrides: Optional[Dict[str, int]] = None,
                     write: bool = False) -> Optional[ItemSpec]:
    sd = root.find("storeData")
    if sd is None:
        return None

    category = (sd.findtext("category") or "misc").strip().lower()
    price_el = sd.find("price")
    if price_el is None or not (price_el.text and price_el.text.strip()):
        return None

    old_price = int(pf(price_el.text, 0))
    if old_price <= 0:
        return None

    title = localized(sd.find("name"), l10n) or os.path.splitext(os.path.basename(rel_path))[0]
    brand = (sd.findtext("brand") or "GENERIC").strip()
    ukey = f"{mod_name}::{rel_path}"

    xm = cfg.xml_factor
    lang = norm_lang(getattr(cfg, "ui_lang", "ru"))

    is_field = is_field_xml(root, category, rel_path)
    is_place = is_placeable_xml(root, category, rel_path)

    # ручные правки ТТХ применяются к дереву ДО извлечения характеристик:
    # расчёт, предпросмотр и запись в файл видят уже изменённые значения
    kind = "field" if is_field else ("placeable" if is_place else "vehicle")
    patch = get_spec_patches().get(ukey)
    original_specs = ET.tostring(root) if write and patch else None
    if patch and kind != "field":
        try:
            apply_patch(root, patch, kind)
        except Exception:
            pass

    # что сканируем: мультивыбор категорий (техника / здания / поля)
    if not cfg.wants(kind):
        return None

    # ── ПОЛЕ ──
    if is_field:
        area, coord, area_ok = extract_field_data(root)
        shop = cfg.shop_coordinates.get("shop") or cfg.shop_coordinates.get(mod_name)
        dist: Optional[float] = None
        if coord is not None and shop is not None:
            dist = round(math.hypot(coord[0] - shop[0], coord[1] - shop[1]) / 1000.0, 2)

        reasons = []
        if not area_ok:
            reasons.append(i18n_t("src.field_noarea", lang))
        if cfg.adjust_field_prices and dist is None:
            reasons.append(i18n_t("src.field_noshop", lang))

        steps: List[Dict[str, Any]] = []
        if overrides and ukey in overrides:
            new_xml = int(overrides[ukey])
            base_eur = new_xml / xm
            plain_eur = base_eur
        else:
            # plain_eur — чистая база по площади (без расстояния), base_eur — с бонусом
            # за близость к магазину. В таблице видно «база → итог» именно как надбавку.
            plain_eur = field_price(area if area_ok else 0.0, None, cfg)
            base_eur = field_price(area if area_ok else 0.0, dist, cfg)
            new_xml = clean_round(base_eur * xm)
            steps = [chain_step(i18n_t("bd.field_area", lang),
                                "{0:g} га".format(area if area_ok else 0.0),
                                max(1500.0, float(area or 0.0) * 4800.0), "+base",
                                float(area if area_ok else 0.0) * 4800.0)]
            if cfg.adjust_field_prices and dist is not None:
                dm = (base_eur / plain_eur) if plain_eur else 1.0
                steps.append(chain_step(i18n_t("bd.field_dist", lang),
                                         "{0:g} км".format(dist), dm, "x", base_eur))
            if abs(cfg.k_field - 1.0) > 1e-6:
                steps.append(chain_step(i18n_t("bd.k_field", lang), "", cfg.k_field, "x",
                                         base_eur * cfg.k_field))

        new_rub = rub_from_xml(new_xml, cfg)
        chain = finish_chain(steps, base_eur,
                             1.0, 1.0, False, xm, new_xml, new_rub, lang,
                             manual=bool(overrides and ukey in overrides))
        changed = bool(write and _set_num(price_el, new_xml))

        return ItemSpec(
            mod_name=mod_name, xml_rel_path=rel_path, item_type="field",
            spec_fields=present_fields(root, kind),
            title=title, brand=brand, category="field",
            category_label=i18n_t("cat.field", lang), country="—", country_flag="🌾",
            price_chain=chain, ui_lang=lang, needs_write=changed,
            old_price=old_price, new_price=new_xml, new_price_rub=new_rub,
            base_price=clean_round(plain_eur * xm),
            field_area=area if area_ok else 0.0,
            field_distance=(dist if dist is not None else -1.0),
            field_coord=coord, needs_review=bool(reasons),
            ai_reason=(i18n_t("src.field_prefix", lang, ", ".join(reasons))
                       if reasons else i18n_t("src.field", lang)),
            source_kind="field", country_mult=cfg.k_field,
        )

    # ── ЗДАНИЕ / ОБЪЕКТ ──
    if is_place:
        cap, slots, prod = extract_placeable_data(root)
        size_lbl, _ = detect_placeable_size(title, rel_path)
        cat_key = str(category or "misc").strip().lower()
        cat_info = PLACEABLE_CATEGORIES.get(cat_key, PLACEABLE_CATEGORIES["misc"])
        cat_lbl = i18n_category(cat_key, lang, cat_info.get("label", cat_key))
        sg = subgroup_for(cat_key, "placeable")

        # линии производства: циклы/ч, выпуск и сырьё за цикл, расходы, склады
        lines = extract_production_specs(root, l10n)
        plant_cap = extract_plant_storage(root)
        if plant_cap <= 0:
            plant_cap = round(sum(p.storage_capacity for p in lines), 2)
        thr = round(sum(p.throughput for p in lines), 2)        # л готового продукта в час
        cph = round(sum(p.cycles_per_hour for p in lines), 2)
        out_am = round(sum(p.output_amount for p in lines), 2)
        in_am = round(sum(p.input_amount for p in lines), 2)
        cm = round(sum(p.costs_per_active_month for p in lines), 2)
        # extract_placeable_data уже привёл costsPerActiveMonth к часам (cm/24) —
        # вторично складывать нельзя: расходы попадали в цену дважды.
        prod_hour = prod
        # «сколько товаров принимает» считаем только у точек продажи — там это и есть ценность
        goods = count_accepted_goods(root) if sg == "selling" else 0
        gv = pf((patch or {}).get("goods_count"), 0.0)
        if gv > 0:
            goods = int(gv)

        country, flag, k_country, is_retro, review, reason, source_kind = detect_country_and_retro(
            brand, title, rel_path, mod_name, cfg, get_learned())
        if brand in ("", "GENERIC", "-"):
            country, flag, k_country, is_retro = "—", "🏗", 1.0, False
            review, reason = False, i18n_t("src.brand_fix", lang)
        if sg == "selling" and goods <= 0:
            review = True
            reason = (reason + " · " if reason else "") + i18n_t("src.no_goods", lang)

        k_retro_eff = float(cfg.k_retro) if (is_retro and cfg.retro_enabled) else 1.0
        steps: List[Dict[str, Any]] = []
        manual_price = None
        if overrides and ukey in overrides:
            new_xml = int(overrides[ukey])
            manual_price = new_xml
            base_eur = new_xml / max(k_country * k_retro_eff * xm, 1e-9)
        else:
            base_eur, steps = calc_placeable_price_ex(
                cat_key, title, rel_path, cap, slots, prod_hour, cfg.k_placeable,
                cfg.global_difficulty_scale, prod_throughput=thr, goods_count=goods,
                storage_capacity=plant_cap, lang=lang, prod_input=in_am, prod_output=out_am)
            priced, k_country, k_retro_eff = apply_item_multipliers(
                base_eur, k_country, is_retro, cfg)
            new_xml = clean_round(priced * xm)

        new_rub = rub_from_xml(new_xml, cfg)
        chain = finish_chain(steps, base_eur, k_country, k_retro_eff, is_retro, xm,
                             new_xml, new_rub, lang, manual=manual_price is not None)
        cheat_values = {"item_type": "placeable", "hp": 0.0, "max_speed": 0.0, "working_width": 0.0,
             "capacity": max(cap, plant_cap), "needed_hp": 0.0, "prod_cycles": cph,
             "prod_input": in_am, "prod_output": out_am, "prod_month_cost": cm,
             "old_price": old_price, "new_price": new_xml}
        verdict = cheat_evaluate(cheat_values, cfg,
            assess_specs(brand, title, rel_path, mod_name, cheat_values, cfg))
        changed = False
        if write:
            changed = _set_num(price_el, new_xml)
            upkeep = sd.find("dailyUpkeep")
            if upkeep is not None:
                changed = _set_num(upkeep, max(1, int(round(new_xml * 0.002)))) or changed
            if original_specs is not None:
                changed = ET.tostring(root) != original_specs

        return ItemSpec(
            mod_name=mod_name, xml_rel_path=rel_path, item_type="placeable",
            spec_fields=present_fields(root, kind),
            title=title, brand=brand, category=cat_key,
            category_label=cat_lbl, country=country, country_flag=flag,
            is_retro=is_retro, old_price=old_price, manual_price=manual_price,
            new_price=new_xml, new_price_rub=new_rub,
            base_price=clean_round(base_eur * xm),
            capacity=cap, slots=slots, production_cost=prod_hour, size_label=size_lbl,
            ai_reason=reason, source_kind=source_kind, brand_mult=cfg.k_placeable,
            country_mult=k_country, retro_mult=k_retro_eff, needs_review=review,
            wear_mult=wear_for_item(is_retro, cfg),
            subgroup=sg, productions=lines, prod_cycles=cph, prod_output=out_am,
            prod_input=in_am, prod_cost_month=cm, storage_capacity=plant_cap,
            goods_count=goods, price_chain=chain, ui_lang=lang, needs_write=changed,
            is_cheat=verdict["is_cheat"], cheat_reason=verdict["cheat_reason"],
            cheat_by=verdict["cheat_by"],
        )

    # ── ТЕХНИКА ──
    if category in VEHICLE_IGNORED_CATS:
        return None
    if any(kw in f"{rel_path} {category}".lower() for kw in VEHICLE_IGNORED_FN):
        return None

    has_motor = root.find(".//motorConfigurations/motorConfiguration") is not None
    has_fill = root.find(".//fillUnitConfigurations/fillUnitConfiguration") is not None
    has_work = root.find(".//workAreas/workArea") is not None
    has_att = root.find(".//attacherJoints") is not None
    is_tool = any(k in category for k in ("handtool", "chainsaw", "tool"))
    if not (has_motor or has_fill or has_work or has_att or is_tool) and category in ("misc", "tools"):
        return None

    ss = sd.find("specs")
    ww = pf(ss.findtext("workingWidth")) if ss is not None else 0.0
    nhp = pf(ss.findtext("neededPower")) if ss is not None else 0.0
    if ww <= 0 and has_work:
        ww = 3.5

    base_hp, max_spd, motors = extract_motor(root)
    base_cap, _fu_cfgs = extract_caps(root)

    country, flag, k_country, is_retro, review, reason, source_kind = detect_country_and_retro(
        brand, title, rel_path, mod_name, cfg, get_learned())

    k_retro_eff = float(cfg.k_retro) if (is_retro and cfg.retro_enabled) else 1.0
    wear = wear_for_item(is_retro, cfg)

    steps: List[Dict[str, Any]] = []
    manual_price = None
    if overrides and ukey in overrides:
        new_xml = int(overrides[ukey])
        manual_price = new_xml
        base_eur = new_xml / max(k_country * k_retro_eff * xm, 1e-9)
    else:
        raw_eur = calc_vehicle_price(category, base_hp, max_spd, base_cap, ww, nhp, 1.0, 1.0)
        eur_raw = calc_vehicle_price(category, base_hp, max_spd, base_cap, ww, nhp,
                                     1.0, cfg.global_difficulty_scale)
        steps = [chain_step(i18n_t("bd.base", lang),
                            i18n_category(category, lang, category), raw_eur, "", raw_eur)]
        if abs(cfg.global_difficulty_scale - 1.0) > 1e-6:
            steps.append(chain_step(i18n_t("bd.diff", lang), "scale",
                                    cfg.global_difficulty_scale, "x", eur_raw))
        base_eur = eur_raw
        priced, k_country, k_retro_eff = apply_item_multipliers(
            eur_raw, k_country, is_retro, cfg)
        new_xml = clean_round(priced * xm)

    new_rub = rub_from_xml(new_xml, cfg)
    chain = finish_chain(steps, base_eur, k_country, k_retro_eff, is_retro, xm,
                         new_xml, new_rub, lang, manual=manual_price is not None)
    cheat_values = {"item_type": "vehicle", "hp": base_hp, "max_speed": max_spd, "working_width": ww,
         "capacity": base_cap, "needed_hp": nhp, "prod_cycles": 0.0,
         "old_price": old_price, "new_price": new_xml}
    verdict = cheat_evaluate(cheat_values, cfg,
        assess_specs(brand, title, rel_path, mod_name, cheat_values, cfg))
    changed = False

    if write:
        changed = _set_num(price_el, new_xml)
        upkeep = sd.find("dailyUpkeep")
        if upkeep is not None:
            changed = _set_num(upkeep, max(5, int(round(new_xml * 0.0025 * wear)))) or changed
        if original_specs is not None:
            changed = ET.tostring(root) != original_specs

    # ── Комплектации (несколько двигателей) ──
    motor_specs: List[MotorSpec] = []
    motor_prices: List[Dict[str, Any]] = []
    cnt = 0
    for i, (mc, hp_i, spd_i, tq_i) in enumerate(motors):
        motor_patch = (patch or {}).get("_motors", {}).get(str(i), {})
        if motor_patch:
            hp_i = float(motor_patch.get("hp", hp_i))
            if write:
                changed = _set_attr_num(mc, "hp", hp_i) or changed
        label = mc.get("name") or f"Комплектация {chr(65 + i)}"
        delta = max(0.0, hp_i - base_hp)
        if i == 0:
            delta_price = 0
            if write and mc.get("price") not in (None, "0"):
                mc.set("price", "0")
                changed = True
        else:
            delta_price = motor_price_for_delta(base_eur, delta, k_country, xm,
                                                is_retro, cfg)
            if write:
                want = str(int(delta_price))
                if mc.get("price") != want:      # не пишем то, что уже стоит в файле
                    mc.set("price", want)
                    changed = True
            cnt += 1
        if "price_delta" in motor_patch:
            delta_price = int(motor_patch["price_delta"])
            if write:
                changed = _set_attr_num(mc, "price", delta_price) or changed

        motor_specs.append(MotorSpec(label=label, hp=hp_i, max_speed=spd_i,
                                     torque=tq_i, price_delta=delta_price, index=i))
        total = clean_round(new_xml + delta_price)
        motor_prices.append({"index": i, "label": label, "hp": hp_i,
                             "speed": spd_i, "delta": delta_price, "total": total})
    if write and original_specs is not None:
        changed = ET.tostring(root) != original_specs

    return ItemSpec(
        mod_name=mod_name, xml_rel_path=rel_path, item_type="vehicle",
        spec_fields=present_fields(root, kind),
        title=title, brand=brand, category=category,
        category_label=i18n_category(category, lang, category),
        country=country, country_flag=flag,
        is_retro=is_retro, manual_price=manual_price,
        price_chain=chain, ui_lang=lang, needs_write=changed, is_cheat=verdict["is_cheat"],
        cheat_reason=verdict["cheat_reason"], cheat_by=verdict["cheat_by"],
        old_price=old_price, new_price=new_xml, new_price_rub=new_rub,
        base_price=clean_round(base_eur * xm), hp=base_hp, max_speed=max_spd,
        capacity=base_cap, working_width=ww, needed_hp=nhp,
        configs_updated=cnt, needs_review=review, brand_mult=1.0,
        country_mult=k_country, retro_mult=k_retro_eff, wear_mult=wear,
        ai_reason=reason, source_kind=source_kind, motors=motor_specs, motor_prices=motor_prices,
    )

# ── Обработка мода (папка или zip) — алгоритм v13 ─────────────────────────────


# ── Быстрая и безопасная запись в моды ────────────────────────────────────────
# FS25-мод — это zip на сотни мегабайт, из которого меняется 2–3 маленьких XML.
# Старый путь (read → inflate → deflate → write) жал все байты архива дважды.
# Здесь неизменные записи копируются как ЕСТЕСТВЕННЫЕ СЖАТЫЕ БЛОКИ, архив остаётся
# каноническим (по одной записи на файл), а проверка CRC выборок защищает от порчи.

_RAW_VER = {zipfile.ZIP_STORED: 10, zipfile.ZIP_DEFLATED: 20,
            zipfile.ZIP_BZIP2: 46, zipfile.ZIP_LZMA: 63}
_LOCAL_SIG = 0x04034b50
_ZIP64_MARK = 0xFFFFFFFF


def _name_bytes(name: str) -> Tuple[bytes, int]:
    """Кодировка имени ровно такая, как у zipfile в центральном каталоге:
    ASCII без флага, иначе UTF-8 + флаг 0x800. Локальный заголовок обязан совпасть."""
    try:
        return name.encode("ascii"), 0
    except UnicodeEncodeError:
        return name.encode("utf-8"), 0x800


def _raw_copyable(item: zipfile.ZipInfo) -> bool:
    if item.flag_bits & 0x1:                                        # зашифровано
        return False
    if item.compress_type not in _RAW_VER:
        return False
    if max(int(item.file_size), int(item.compress_size)) > _ZIP64_MARK:
        return False                                                # не влезет в 32-битные поля
    return True


def _entry_data_off(src_fh, item: zipfile.ZipInfo) -> int:
    src_fh.seek(int(item.header_offset))
    hdr = src_fh.read(30)
    if len(hdr) != 30 or hdr[:4] != b"PK\x03\x04":
        raise ValueError("битый локальный заголовок у " + item.filename)
    nlen, elen = struct.unpack("<HH", hdr[26:30])
    return int(item.header_offset) + 30 + nlen + elen


def _copy_raw_entry(src_fh, out_fh, zo: zipfile.ZipFile, item: zipfile.ZipInfo) -> None:
    data_off = _entry_data_off(src_fh, item)
    nb, flags = _name_bytes(item.filename)
    ver = _RAW_VER[item.compress_type]
    dt = item.date_time
    dosdate = (dt[0] - 1980) << 9 | dt[1] << 5 | dt[2]
    dostime = dt[3] << 11 | dt[4] << 5 | (dt[5] // 2)
    item.header_offset = out_fh.tell()
    out_fh.write(struct.pack("<IHHHHHIIIHH", _LOCAL_SIG, ver, flags, item.compress_type,
                             dostime, dosdate, item.CRC, item.compress_size,
                             item.file_size, len(nb), 0))
    out_fh.write(nb)
    DISK.add("zip_head", 30 + len(nb))
    src_fh.seek(data_off)
    left = int(item.compress_size)
    while left > 0:
        buf = src_fh.read(min(1 << 21, left))
        if not buf:
            raise IOError("запись обрезана: " + item.filename)
        out_fh.write(buf)
        DISK.add("zip_copy", len(buf))
        left -= len(buf)
    item.flag_bits = flags
    item.extra = b""            # локальный и центральный extra должны совпадать
    zo.filelist.append(item)
    zo.NameToInfo[item.filename] = item
    zo.start_dir = out_fh.tell()


def _replace_with_retry(src: str, dst: str) -> None:
    last: Optional[BaseException] = None
    for i in range(4):
        try:
            os.replace(src, dst)
            return
        except OSError as e:                  # антивирус/игра могла держать файл
            last = e
            time.sleep(0.25 * (i + 1))
    raise last if last else RuntimeError("os.replace не удался")


def _atomic_write(path: str, data: bytes) -> None:
    """Никогда не пишем в файл на месте: иначе жёсткая ссылка в бэкапе потеряет оригинал."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    DISK.add("xml", len(data))
    _replace_with_retry(tmp, path)


def _backup_file_bytes(data: bytes, dst: str) -> None:
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(dst):
        return
    _atomic_write(dst, data)


def restore_mod_backup(mod_path: str, backup_root: str) -> int:
    """Возвращает мод к исходным ценам из резервных копий.

    Папка-мод: файлы копируются обратно атомарно. Zip-мод: исходные XML
    записываются точечно (in-place), сотни мегабайт ассетов не трогаются.
    Возвращает число восстановленных файлов.
    """
    mod_name = os.path.basename(mod_path)
    src_root = os.path.join(backup_root, mod_name)
    if not os.path.isdir(src_root) and mod_path.lower().endswith(".zip"):
        src_root = os.path.join(backup_root, os.path.splitext(mod_name)[0])
    if not os.path.isdir(src_root):
        return 0
    done = 0
    if mod_path.lower().endswith(".zip"):
        modified: Dict[str, bytes] = {}
        for root, _dirs, files in os.walk(src_root):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src_root).replace(os.sep, "/")
                with open(full, "rb") as f:
                    modified[rel] = f.read()
        if modified:
            rebuild_mod_zip(mod_path, modified)
            done += len(modified)
        return done
    for root, _dirs, files in os.walk(src_root):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_root)
            dst = os.path.join(mod_path, rel)
            with open(full, "rb") as f:
                data = f.read()
            if os.path.isfile(dst):
                with open(dst, "rb") as current:
                    if current.read() == data:
                        continue
            _atomic_write(dst, data)
            done += 1
    return done


def _backup_file(src: str, dst: str) -> None:
    """Один файл → один бэкап. Жёсткая ссылка: ноль байт записи и доли секунды."""
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)                     # NTFS: доли секунды и 0 байт лишнего места
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
        DISK.add("backup", os.path.getsize(dst))


def _migrate_legacy_mod_backup(backup_dir: Optional[str], mod_name: str) -> None:
    """v13 хранил бэкап целым zip мода, v16 — папкой с XML: переименовываем коллизию."""
    if not backup_dir:
        return
    target = os.path.join(backup_dir, mod_name)
    if os.path.isfile(target):
        os.replace(target, target + ".legacy")


def _backup_tree(src_dir: str, dst_dir: str) -> None:
    if os.path.isdir(dst_dir):
        return
    _migrate_legacy_mod_backup(os.path.dirname(dst_dir), os.path.basename(dst_dir))
    try:
        for root, dirs, files in os.walk(src_dir):
            rel = os.path.relpath(root, src_dir)
            base = dst_dir if rel == "." else os.path.join(dst_dir, rel)
            os.makedirs(base, exist_ok=True)
            for fn in files:
                s = os.path.join(root, fn)
                d = os.path.join(base, fn)
                if os.path.exists(d):
                    continue
                try:
                    os.link(s, d)
                except (OSError, NotImplementedError):
                    shutil.copy2(s, d)
    except Exception:
        shutil.rmtree(dst_dir, ignore_errors=True)
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)


def _verify_zip(tmp_path: str, src_path: str, modified: Dict[str, bytes]) -> None:
    """Проверяет до замены: число записей, CRC/размеры и байты выборки."""
    with zipfile.ZipFile(tmp_path) as zn, zipfile.ZipFile(src_path) as zs:
        ni = zn.infolist()
        if len(ni) != len(zs.infolist()):
            raise ValueError("архив потерял файлы: %d вместо %d" % (len(ni), len(zs.infolist())))
        for name, data in modified.items():
            if zn.read(name) != data:
                raise ValueError("расхождение содержимого " + name)
        step = max(1, len(ni) // 8)
        for it in ni[::step][:8]:
            if it.filename in modified:
                continue
            ref = zs.getinfo(it.filename)
            if it.CRC != ref.CRC or it.file_size != ref.file_size:
                raise ValueError("расхождение метаданных " + it.filename)
            if zn.read(it.filename) != zs.read(it.filename):
                raise ValueError("расхождение байтов " + it.filename)


# ── Счётчик реально записанных байтов (пользователь видит износ диска) ─────────

class _DiskMeter:
    """Байты, переданные файловой системе; аппаратные записи SSD не измеряются."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.written = 0
        self.read = 0
        self.by_kind: Dict[str, int] = {}

    def reset(self) -> None:
        with self._lock:
            self.written = 0
            self.read = 0
            self.by_kind = {}

    def add(self, kind: str, n: int) -> None:
        with self._lock:
            self.written += int(n)
            self.by_kind[kind] = self.by_kind.get(kind, 0) + int(n)

    def payload(self) -> Dict[str, Any]:
        with self._lock:
            return {"written": self.written, "read": self.read,
                    "by_kind": dict(self.by_kind)}


DISK = _DiskMeter()


def reset_disk_meter() -> None:
    DISK.reset()


def disk_payload() -> Dict[str, Any]:
    return DISK.payload()


def _write_out(fh, data: bytes, kind: str) -> None:
    fh.write(data)
    DISK.add(kind, len(data))


def _deflate_raw(data: bytes, level: int = 6) -> bytes:
    """RAW-deflate как в zip-контейнере (без zlib-заголовка)."""
    co = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
    return co.compress(data) + co.flush()


# ── Минимальная правка архива: дописали только новые XML + переписали оглавление ──

_JOURNAL_HEADER = struct.Struct("<8sQQI")
_JOURNAL_MAGIC = b"FS25ZIP1"


class _MeteredFile:
    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, data):
        written = self.stream.write(data)
        DISK.add("zip", written)
        return written


def _lock_journal(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def recover_mod_zip(mod_path: str) -> bool:
    journal_path = mod_path + ".fs25txn"
    if not os.path.isfile(journal_path):
        return False
    with open(journal_path, "r+b") as journal:
        _lock_journal(journal)
        header = journal.read(_JOURNAL_HEADER.size)
        if len(header) != _JOURNAL_HEADER.size:
            raise ValueError("Неполный журнал ZIP: " + journal_path)
        magic, offset, original_size, checksum = _JOURNAL_HEADER.unpack(header)
        tail = journal.read()
        if (magic != _JOURNAL_MAGIC or original_size != offset + len(tail)
                or zlib.crc32(tail) != checksum):
            raise ValueError("Повреждён журнал ZIP: " + journal_path)
        with open(mod_path, "r+b") as target:
            if os.fstat(target.fileno()).st_size < offset:
                raise ValueError("Архив не соответствует журналу восстановления")
            target.seek(offset)
            _write_out(target, tail, "recovery")
            target.truncate(original_size)
            target.flush()
            os.fsync(target.fileno())
    os.remove(journal_path)
    return True


def _update_zip_inplace(mod_path: str, modified: Dict[str, bytes]) -> None:
    """Пишет XML и каталог ZIP. Журнал хранит только заменяемый хвост архива."""
    with zipfile.ZipFile(mod_path, "r") as z:
        entries = z.infolist()
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError("В архиве есть повторяющиеся имена файлов")
        if not set(z.namelist()).issuperset(modified):
            raise ValueError("в архиве нет ожидаемых записей")
        offset = z.start_dir
        comment = z.comment
        originals = {name: copy.copy(z.getinfo(name)) for name in modified}
    with open(mod_path, "rb") as source:
        source.seek(offset)
        tail = source.read()
        original_size = source.tell()
    journal_path = mod_path + ".fs25txn"
    journal = open(journal_path, "x+b")
    try:
        _write_out(journal, _JOURNAL_HEADER.pack(
            _JOURNAL_MAGIC, offset, original_size, zlib.crc32(tail)), "journal")
        _write_out(journal, tail, "journal")
        journal.flush()
        _lock_journal(journal)
        os.fsync(journal.fileno())
        try:
            with open(mod_path, "r+b") as stream:
                with zipfile.ZipFile(_MeteredFile(stream), "a") as target:
                    target.filelist[:] = [entry for entry in target.filelist
                                          if entry.filename not in modified]
                    for name, data in modified.items():
                        target.NameToInfo.pop(name, None)
                        target.writestr(originals[name], data)
                stream.flush()
                os.fsync(stream.fileno())
            _verify_inplace(mod_path, modified, len(entries), comment)
        except BaseException:
            with open(mod_path, "r+b") as stream:
                stream.seek(offset)
                _write_out(stream, tail, "recovery")
                stream.truncate(original_size)
                stream.flush()
                os.fsync(stream.fileno())
            raise
    finally:
        journal.close()
    os.remove(journal_path)


def _verify_inplace(path: str, modified: Dict[str, bytes], count: int,
                    comment: bytes) -> None:
    with zipfile.ZipFile(path) as z:
        if len(z.infolist()) != count:
            raise ValueError("оглавление потеряло записи: %d вместо %d"
                             % (len(z.infolist()), count))
        if (z.comment or b"") != comment:
            raise ValueError("пропал комментарий архива")
        for name, data in modified.items():
            if z.read(name) != data:
                raise ValueError("в архиве лежит не то, что записывали: " + name)
        if len(set(z.namelist())) != count:
            raise ValueError("дубли записей в оглавлении")


def _rebuild_zip_fast(mod_path: str, modified: Dict[str, bytes]) -> None:
    tmp = mod_path + ".tmp"
    try:
        with open(mod_path, "rb") as src_fh, open(tmp, "wb") as out_fh:
            with zipfile.ZipFile(src_fh) as zi, zipfile.ZipFile(out_fh, "w") as zo:
                zo._didModify = True
                for item in zi.infolist():
                    data = modified.get(item.filename)
                    if data is not None:
                        zo.writestr(item, data)          # маленький XML: жмём как обычно
                    elif _raw_copyable(item):
                        _copy_raw_entry(src_fh, out_fh, zo, item)
                    else:
                        zo.writestr(item, zi.read(item.filename))
        _verify_zip(tmp, mod_path, modified)
        _replace_with_retry(tmp, mod_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _rebuild_zip_safe(mod_path: str, modified: Dict[str, bytes]) -> None:
    """Полное пережатие: только для архивов, которые нельзя править точечно."""
    tmp = mod_path + ".tmp"
    try:
        with zipfile.ZipFile(mod_path, "r") as zi, \
             zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for item in zi.infolist():
                if item.filename in modified:
                    zo.writestr(item, modified[item.filename])
                else:
                    zo.writestr(item, zi.read(item.filename))
        _replace_with_retry(tmp, mod_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def rebuild_mod_zip(mod_path: str, modified: Dict[str, bytes]) -> str:
    """Возвращает применённую стратегию: skip | inplace | rebuild | safe.

    inplace — основной путь: пишет только изменённые XML и оглавление архива.
    rebuild — raw-копия всего архива без пережатия (если оглавление не в хвосте
    или архив с zip64/комментарием). safe — полное пережатие, крайний случай.
    """
    if not modified:
        return "skip"
    recover_mod_zip(mod_path)
    with zipfile.ZipFile(mod_path, "r") as archive:
        modified = {name: data for name, data in modified.items()
                    if archive.read(name) != data}
    if not modified:
        return "skip"
    _update_zip_inplace(mod_path, modified)
    return "inplace"



def process_mod(mod_path: str, cfg: BalancerConfig, apply: bool = False,
                backup_dir: Optional[str] = None,
                overrides: Optional[Dict[str, int]] = None,
                stop: Optional[Any] = None) -> List[ItemSpec]:
    results: List[ItemSpec] = []
    mod_name = os.path.basename(mod_path)

    if stop and stop.is_set():
        return results

    if os.path.isdir(mod_path):
        if mod_name.startswith("_backup"):
            return results
        _migrate_legacy_mod_backup(backup_dir, mod_name)
        md_p = os.path.join(mod_path, "modDesc.xml")
        if not os.path.isfile(md_p):
            return results
        try:
            with open(md_p, "rb") as f:
                sfiles, l10n = parse_moddesc(f.read())
        except Exception:
            return results

        for sf in sfiles:
            if stop and stop.is_set():
                break
            fp = os.path.join(mod_path, sf)
            if not os.path.isfile(fp):
                continue
            try:
                tree = ET.parse(fp)
                spec = process_xml_root(tree.getroot(), sf, mod_name, l10n, cfg,
                                        overrides, write=apply)
                if spec:
                    if apply and spec.needs_write:
                        # бэкапим ТОЛЬКО тот XML, который сейчас перепишем
                        if cfg.create_backups and backup_dir:
                            _backup_file(fp, os.path.join(backup_dir, mod_name, sf))
                        _atomic_write(fp, ET.tostring(tree.getroot(), encoding="utf-8",
                                                      xml_declaration=True))
                    results.append(spec)
            except OSError:
                if apply:
                    raise
                continue
            except Exception:
                continue
        return results

    if not mod_path.lower().endswith(".zip"):
        return results

    recover_mod_zip(mod_path)
    modified: Dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(mod_path, "r") as zf:
            nmap = {n.replace("\\", "/").lstrip("/").lower(): n for n in zf.namelist()}
            if "moddesc.xml" not in nmap:
                return results

            sfiles, l10n = parse_moddesc(zf.read(nmap["moddesc.xml"]))
            if not sfiles:
                return results

            for sf in sfiles:
                if stop and stop.is_set():
                    break
                sk = sf.replace("\\", "/").lstrip("/").lower()
                real = nmap.get(sk)
                if not real:
                    continue
                try:
                    raw = zf.read(real)
                    root = ET.fromstring(raw)
                    spec = process_xml_root(root, sf, mod_name, l10n, cfg,
                                            overrides, write=apply)
                    if spec:
                        results.append(spec)
                        if apply and spec.needs_write:
                            modified[real] = ET.tostring(root, encoding="utf-8",
                                                          xml_declaration=True)
                except OSError:
                    if apply:
                        raise
                    continue
                except Exception:
                    continue

        if apply and modified and not (stop and stop.is_set()):
            _migrate_legacy_mod_backup(backup_dir, mod_name)
            if cfg.create_backups and backup_dir:
                # бэкапим только те XML, которые сейчас перепишем: из архива
                # вытаскиваются исходные версии (килобайты), а не весь мод
                with zipfile.ZipFile(mod_path, "r") as zf:
                    for name in modified:
                        dst = os.path.join(backup_dir, mod_name, name.replace("/", os.sep))
                        if os.path.exists(dst):
                            continue
                        _backup_file_bytes(zf.read(name), dst)
            rebuild_mod_zip(mod_path, modified)

    except Exception as e:
        if apply:
            raise
        print(f"[Skip] {mod_name}: {e}")

    return results


def apply_prepared_mod(mod_path: str, specs: List[ItemSpec], cfg: BalancerConfig,
                       backup_dir: str, stop: Optional[Any] = None) -> List[ItemSpec]:
    """Записывает подтверждённый результат без распознавания бренда и повторного расчёта."""
    grouped: Dict[str, List[ItemSpec]] = {}
    for spec in specs:
        grouped.setdefault(spec.xml_rel_path, []).append(spec)
        spec.needs_write = False
    if mod_path.lower().endswith(".zip"):
        recover_mod_zip(mod_path)
        with zipfile.ZipFile(mod_path) as archive:
            names = {name.replace("\\", "/").lower(): name for name in archive.namelist()}
            originals = {names[path.replace("\\", "/").lower()]: archive.read(names[path.replace("\\", "/").lower()])
                         for path in grouped}
        actual = {path: names[path.replace("\\", "/").lower()] for path in grouped}
    else:
        originals = {}
        actual = {}
        base = os.path.realpath(mod_path)
        for path in grouped:
            destination = os.path.realpath(os.path.join(base, path.replace("\\", "/")))
            if os.path.commonpath([base, destination]) != base:
                raise ValueError("XML находится вне папки мода")
            actual[path] = destination
            with open(destination, "rb") as source:
                originals[destination] = source.read()
    modified = {}
    changed_specs = []
    for path, items in grouped.items():
        if stop and stop.is_set():
            return specs
        root = ET.fromstring(originals[actual[path]])
        before = ET.tostring(root)
        spec = items[0]
        patch = get_spec_patches().get(spec.unique_key, {})
        if patch:
            apply_patch(root, patch, spec.item_type)
        data = root.find("storeData")
        if data is None or data.find("price") is None:
            raise ValueError("Не найден storeData/price: " + path)
        _set_num(data.find("price"), spec.new_price)
        upkeep = data.find("dailyUpkeep")
        if upkeep is not None and spec.item_type != "field":
            factor = 0.0025 * wear_for_item(spec.is_retro, cfg) if spec.item_type == "vehicle" else 0.002
            _set_num(upkeep, max(5 if spec.item_type == "vehicle" else 1,
                                  int(round(spec.new_price * factor))))
        configurations = root.findall(".//motorConfigurations/motorConfiguration")
        for motor in spec.motors:
            if motor.index < len(configurations):
                configuration = configurations[motor.index]
                _set_attr_num(configuration, "price", motor.price_delta)
                if str(motor.index) in patch.get("_motors", {}):
                    original_hp = pf(configuration.get("hp"))
                    engine = configuration.find("motor")
                    torque = pf(engine.get("torqueScale")) if engine is not None else 0.0
                    if engine is not None and original_hp > 0 and torque > 0:
                        _set_attr_num(engine, "torqueScale", torque * motor.hp / original_hp)
                    _set_attr_num(configuration, "hp", motor.hp)
        if ET.tostring(root) == before:
            continue
        modified[actual[path]] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        changed_specs.extend(items)
    if not modified:
        return specs
    if cfg.create_backups:
        _migrate_legacy_mod_backup(backup_dir, os.path.basename(mod_path))
        for name in modified:
            relative = name if mod_path.lower().endswith(".zip") else os.path.relpath(name, mod_path)
            if os.path.isabs(relative) or ".." in relative.replace("\\", "/").split("/"):
                raise ValueError("Небезопасный путь XML в архиве")
            destination = os.path.join(backup_dir, os.path.basename(mod_path), relative.replace("/", os.sep))
            _backup_file_bytes(originals[name], destination)
    if mod_path.lower().endswith(".zip"):
        rebuild_mod_zip(mod_path, modified)
    else:
        for name, content in modified.items():
            _atomic_write(name, content)
    for spec in changed_specs:
        spec.needs_write = True
    return specs


def finalize_spec(s: ItemSpec, cfg: BalancerConfig, steps: List[Dict[str, Any]],
                  base_eur: float, k_country: float, k_retro: float,
                  manual: bool = False) -> ItemSpec:
    """Достраивает разбор цены (видно всегда) и вердикт «читерный» для позиции."""
    lang = norm_lang(getattr(cfg, "ui_lang", "ru"))
    s.ui_lang = lang
    s.price_chain = finish_chain(steps, base_eur, k_country, k_retro, s.is_retro,
                                 cfg.xml_factor, s.new_price, s.new_price_rub, lang,
                                 manual=manual)
    hint = ai_cheat_hint(s.brand, s.title, s.xml_rel_path, s.mod_name)
    v = cheat_evaluate({
        "item_type": s.item_type, "hp": s.hp, "max_speed": s.max_speed,
        "working_width": s.working_width, "needed_hp": s.needed_hp,
        "capacity": max(s.capacity, s.storage_capacity) if s.item_type == "placeable" else s.capacity,
        "prod_cycles": s.prod_cycles, "old_price": s.old_price, "new_price": s.new_price,
    }, cfg, hint)
    s.is_cheat, s.cheat_reason, s.cheat_by = v["is_cheat"], v["cheat_reason"], v["cheat_by"]
    return s


def vehicle_chain_steps(s: ItemSpec, cfg: BalancerConfig, cat: str, raw: Dict[str, Any],
                        lang: str) -> List[Dict[str, Any]]:
    """Шаги разбора для техники: база по классу + общий масштаб сложности."""
    raw_eur = calc_vehicle_price(cat, raw.get("hp", 0.0), raw.get("spd", 0.0),
                                raw.get("cap", 0.0), raw.get("ww", 0.0),
                                raw.get("nhp", 0.0), 1.0, 1.0)
    steps = [chain_step(i18n_t("bd.base", lang), i18n_category(cat, lang, cat),
                        raw_eur, "", raw_eur)]
    if abs(float(cfg.global_difficulty_scale) - 1.0) > 1e-6:
        steps.append(chain_step(i18n_t("bd.diff", lang), "scale",
                                cfg.global_difficulty_scale, "x",
                                raw_eur * cfg.global_difficulty_scale))
    return steps


def recalc_specs(specs: List[ItemSpec], cfg: BalancerConfig,
                 overrides: Dict[str, int], raw_cache: Dict[str, Dict[str, Any]]
                 ) -> List[ItemSpec]:
    """Пересчёт БЕЗ повторного сканирования: использует кэш извлечённых ТТХ."""
    out: List[ItemSpec] = []
    xm = cfg.xml_factor

    for s in specs:
        c = raw_cache.get(s.unique_key)
        if not c:
            out.append(s)
            continue

        if s.item_type == "field":
            area = s.field_area if s.field_area > 0 else c.get("area", 0.0)
            dist = None if s.field_distance < 0 else s.field_distance
            base_eur = field_price(area, dist, cfg)
            s.base_price = clean_round(field_price(area, None, cfg) * xm)
            s.new_price = int(overrides.get(s.unique_key, clean_round(base_eur * xm)))
            s.new_price_rub = rub_from_xml(s.new_price, cfg)
            s.country_mult = cfg.k_field
            if s.field_manual:
                s.needs_review = s.field_area <= 0 or (cfg.adjust_field_prices
                                                       and s.field_distance < 0)
            lang = norm_lang(cfg.ui_lang)
            fsteps = [chain_step(i18n_t("bd.field_area", lang),
                                 "{0:g} га".format(area), max(1500.0, area * 4800.0),
                                 "+base", area * 4800.0)]
            if cfg.adjust_field_prices and dist is not None:
                plain = field_price(area, None, cfg)
                fsteps.append(chain_step(i18n_t("bd.field_dist", lang),
                                         "{0:g} км".format(dist),
                                         (base_eur / plain) if plain else 1.0, "x", base_eur))
            if abs(cfg.k_field - 1.0) > 1e-6:
                fsteps.append(chain_step(i18n_t("bd.k_field", lang), "", cfg.k_field, "x",
                                         base_eur))
            finalize_spec(s, cfg, fsteps, base_eur, 1.0, 1.0,
                          manual=s.unique_key in overrides)
            out.append(s)
            continue

        if s.item_type == "placeable":
            lang = norm_lang(cfg.ui_lang)
            cat = c.get("category", "misc")
            goods = int(s.goods_count or c.get("goods", 0) or 0)
            base_eur, psteps = calc_placeable_price_ex(
                cat, s.title, s.xml_rel_path, c.get("cap", 0.0), c.get("slots", 0),
                c.get("prod", 0.0), cfg.k_placeable, cfg.global_difficulty_scale,
                prod_throughput=c.get("thr", 0.0), goods_count=goods,
                storage_capacity=c.get("scap", 0.0), lang=lang,
                prod_input=c.get("in", 0.0), prod_output=c.get("out", 0.0))
            k_c = cfg.multiplier_for(s.country) if s.country in _known_countries() else 1.0
            priced, k_c, k_r = apply_item_multipliers(base_eur, k_c, s.is_retro, cfg)
            s.base_price = clean_round(base_eur * xm)
            s.country_mult, s.retro_mult = k_c, k_r
            s.wear_mult = wear_for_item(s.is_retro, cfg)
            s.new_price = int(overrides.get(s.unique_key, clean_round(priced * xm)))
            s.new_price_rub = rub_from_xml(s.new_price, cfg)
            finalize_spec(s, cfg, psteps, base_eur, k_c, k_r,
                          manual=s.unique_key in overrides)
            out.append(s)
            continue

        # техника
        base_eur = calc_vehicle_price(c.get("category", "misc"), c.get("hp", 0.0),
                                      c.get("spd", 0.0), c.get("cap", 0.0),
                                      c.get("ww", 0.0), c.get("nhp", 0.0),
                                      1.0, cfg.global_difficulty_scale)
        k_country = cfg.multiplier_for(s.country) if s.country in _known_countries() else 1.0
        priced, k_country, k_retro = apply_item_multipliers(base_eur, k_country,
                                                            s.is_retro, cfg)
        s.country_mult, s.retro_mult = k_country, k_retro
        s.wear_mult = wear_for_item(s.is_retro, cfg)
        s.base_price = clean_round(base_eur * xm)

        if s.unique_key in overrides:
            s.new_price = int(overrides[s.unique_key])
        else:
            s.new_price = clean_round(priced * xm)
        s.new_price_rub = rub_from_xml(s.new_price, cfg)

        finalize_spec(s, cfg,
                      vehicle_chain_steps(s, cfg, c.get("category", "misc"), c,
                                          norm_lang(cfg.ui_lang)),
                      base_eur, k_country, k_retro, manual=s.unique_key in overrides)

        cnt = 0
        s.motor_prices = []
        for i, m in enumerate(s.motors):
            motor_patch = get_spec_patches().get(s.unique_key, {}).get("_motors", {}).get(str(m.index), {})
            if i == 0:
                m.price_delta = 0
            else:
                m.price_delta = motor_price_for_delta(base_eur,
                                                      max(0.0, m.hp - c.get("hp", 0.0)),
                                                      k_country, xm, s.is_retro, cfg)
                cnt += 1
            if "price_delta" in motor_patch:
                m.price_delta = int(motor_patch["price_delta"])
            s.motor_prices.append({"index": i, "label": m.label, "hp": m.hp,
                                   "speed": m.max_speed, "delta": m.price_delta,
                                   "total": clean_round(s.new_price + m.price_delta)})
        s.configs_updated = cnt
        out.append(s)

    return out


def _known_countries() -> set:
    from core.countries import ALL_COUNTRIES
    return set(ALL_COUNTRIES.keys())
