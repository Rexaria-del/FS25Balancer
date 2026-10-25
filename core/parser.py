# -*- coding: utf-8 -*-
"""Парсинг модов FS25: modDesc, XML техники/зданий/полей, запись цен.

Алгоритмы extract_*/calc_* перенесены из v13 без изменений.
Добавлено: ретро-множитель, несколько комплектаций двигателя, поля.
"""

import hashlib, math, os, re, shutil, zipfile
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.ai import detect_country_and_retro
from core.ai_state import get_learned
from core.models import BalancerConfig, ItemSpec, MotorSpec, ScanTarget
from core.pricing import (
    FUEL_FILL_TYPES, PLACEABLE_CATEGORIES, VEHICLE_IGNORED_CATS, VEHICLE_IGNORED_FN,
    apply_item_multipliers, calc_placeable_price, calc_vehicle_price, clean_round,
    detect_placeable_size, field_price, motor_price_for_delta, wear_for_item,
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

    prod = 0.0
    for pp in root.findall(".//productions/production"):
        c = pf(pp.get("costsPerActiveHour"))
        if c > 0:
            prod += c
        c2 = pf(pp.get("costsPerActiveMonth"))
        if c2 > 0:
            prod += c2 / 24.0

    return cap, slots, prod


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

    xm = 1.0 if cfg.use_additional_currencies else cfg.exchange_rate
    dm = cfg.exchange_rate if cfg.use_additional_currencies else 1.0

    is_field = is_field_xml(root, category, rel_path)
    is_place = is_placeable_xml(root, category, rel_path)

    if cfg.scan_target == ScanTarget.VEHICLES and (is_field or is_place):
        return None
    if cfg.scan_target == ScanTarget.PLACEABLES and (is_field or not is_place):
        return None
    if cfg.scan_target == ScanTarget.FIELDS and not is_field:
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
            reasons.append("площадь не определена")
        if cfg.adjust_field_prices and dist is None:
            reasons.append("нет координат магазина/поля")

        if overrides and ukey in overrides:
            new_xml = int(overrides[ukey])
            base_eur = new_xml / xm
        else:
            base_eur = field_price(area if area_ok else 0.0, dist, cfg)
            new_xml = clean_round(base_eur * xm)

        new_rub = clean_round(base_eur * dm)
        if write:
            price_el.text = str(new_xml)

        return ItemSpec(
            mod_name=mod_name, xml_rel_path=rel_path, item_type="field",
            title=title, brand=brand, category="field",
            category_label="Поле", country="—", country_flag="🌾",
            old_price=old_price, new_price=new_xml, new_price_rub=new_rub,
            base_price=clean_round(base_eur * xm),
            field_area=area if area_ok else 0.0,
            field_distance=(dist if dist is not None else -1.0),
            field_coord=coord, needs_review=bool(reasons),
            ai_reason=("Поле: " + ", ".join(reasons)) if reasons else "Поле",
            country_mult=cfg.k_field,
        )

    # ── ЗДАНИЕ / ОБЪЕКТ ──
    if is_place:
        cap, slots, prod = extract_placeable_data(root)
        size_lbl, _ = detect_placeable_size(title, rel_path)
        cat_info = PLACEABLE_CATEGORIES.get(category, PLACEABLE_CATEGORIES["misc"])

        country, flag, k_country, is_retro, review, reason = detect_country_and_retro(
            brand, title, rel_path, mod_name, cfg, get_learned())
        if brand in ("", "GENERIC", "-"):
            country, flag, k_country, is_retro = "—", "🏗", 1.0, False
            review, reason = False, "Здание: бренд не указан"

        k_retro_eff = float(cfg.k_retro) if is_retro else 1.0
        if overrides and ukey in overrides:
            new_xml = int(overrides[ukey])
            base_eur = new_xml / (k_country * k_retro_eff * xm)
        else:
            base_eur = calc_placeable_price(category, title, rel_path, cap, slots,
                                            prod, cfg.k_placeable,
                                            cfg.global_difficulty_scale)
            priced, k_country, k_retro_eff = apply_item_multipliers(
                base_eur, k_country, is_retro, cfg)
            new_xml = clean_round(priced * xm)

        new_rub = clean_round(base_eur * k_country * k_retro_eff * dm)
        if write:
            price_el.text = str(new_xml)
            upkeep = sd.find("dailyUpkeep")
            if upkeep is not None:
                upkeep.text = str(max(1, int(round(new_xml * 0.002))))

        return ItemSpec(
            mod_name=mod_name, xml_rel_path=rel_path, item_type="placeable",
            title=title, brand=brand, category=category,
            category_label=cat_info["label"], country=country, country_flag=flag,
            is_retro=is_retro, old_price=old_price,
            new_price=new_xml, new_price_rub=new_rub,
            base_price=clean_round(base_eur * xm),
            capacity=cap, slots=slots, production_cost=prod, size_label=size_lbl,
            ai_reason=reason, brand_mult=cfg.k_placeable,
            country_mult=k_country, retro_mult=k_retro_eff, needs_review=review,
            wear_mult=wear_for_item(is_retro, cfg),
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

    country, flag, k_country, is_retro, review, reason = detect_country_and_retro(
        brand, title, rel_path, mod_name, cfg, get_learned())

    k_retro_eff = float(cfg.k_retro) if is_retro else 1.0
    wear = wear_for_item(is_retro, cfg)

    if overrides and ukey in overrides:
        new_xml = int(overrides[ukey])
        base_eur = new_xml / (k_country * k_retro_eff * xm)
    else:
        eur_raw = calc_vehicle_price(category, base_hp, max_spd, base_cap, ww, nhp,
                                     1.0, cfg.global_difficulty_scale)
        base_eur = eur_raw
        priced, k_country, k_retro_eff = apply_item_multipliers(
            eur_raw, k_country, is_retro, cfg)
        new_xml = clean_round(priced * xm)

    new_rub = clean_round(new_xml / xm * dm)

    if write:
        price_el.text = str(new_xml)
        upkeep = sd.find("dailyUpkeep")
        if upkeep is not None:
            upkeep.text = str(max(5, int(round(new_xml * 0.0025 * wear))))

    # ── Комплектации (несколько двигателей) ──
    motor_specs: List[MotorSpec] = []
    motor_prices: List[Dict[str, Any]] = []
    cnt = 0
    for i, (mc, hp_i, spd_i, tq_i) in enumerate(motors):
        label = mc.get("name") or f"Комплектация {chr(65 + i)}"
        delta = max(0.0, hp_i - base_hp)
        if i == 0:
            delta_price = 0
            if write and mc.get("price") not in (None, "0"):
                mc.set("price", "0")
        else:
            delta_price = motor_price_for_delta(base_eur, delta, k_country, xm,
                                                is_retro, cfg)
            if write:
                mc.set("price", str(delta_price))
            cnt += 1

        motor_specs.append(MotorSpec(label=label, hp=hp_i, max_speed=spd_i,
                                     torque=tq_i, price_delta=delta_price, index=i))
        total = clean_round(new_xml + delta_price)
        motor_prices.append({"index": i, "label": label, "hp": hp_i,
                             "speed": spd_i, "delta": delta_price, "total": total})

    return ItemSpec(
        mod_name=mod_name, xml_rel_path=rel_path, item_type="vehicle",
        title=title, brand=brand, category=category,
        category_label=category, country=country, country_flag=flag,
        is_retro=is_retro, manual_price=(int(overrides[ukey]) if overrides and ukey in overrides else None),
        old_price=old_price, new_price=new_xml, new_price_rub=new_rub,
        base_price=clean_round(base_eur * xm), hp=base_hp, max_speed=max_spd,
        capacity=base_cap, working_width=ww, needed_hp=nhp,
        configs_updated=cnt, needs_review=review, brand_mult=1.0,
        country_mult=k_country, retro_mult=k_retro_eff, wear_mult=wear,
        ai_reason=reason, motors=motor_specs, motor_prices=motor_prices,
    )

# ── Обработка мода (папка или zip) — алгоритм v13 ─────────────────────────────

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
                    if apply:
                        tree.write(fp, encoding="utf-8", xml_declaration=True)
                    results.append(spec)
            except Exception:
                continue
        return results

    if not mod_path.lower().endswith(".zip"):
        return results

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
                        if apply:
                            modified[real] = ET.tostring(root, encoding="utf-8",
                                                          xml_declaration=True)
                except Exception:
                    continue

        if apply and modified and not (stop and stop.is_set()):
            if cfg.create_backups and backup_dir:
                os.makedirs(backup_dir, exist_ok=True)
                bp = os.path.join(backup_dir, mod_name)
                if not os.path.exists(bp):
                    shutil.copy2(mod_path, bp)

            tmp = mod_path + ".tmp"
            with zipfile.ZipFile(mod_path, "r") as zi, \
                 zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
                for item in zi.infolist():
                    if item.filename in modified:
                        zo.writestr(item, modified[item.filename])
                    else:
                        zo.writestr(item, zi.read(item.filename))
            shutil.move(tmp, mod_path)

    except Exception as e:
        print(f"[Skip] {mod_name}: {e}")

    return results


def recalc_specs(specs: List[ItemSpec], cfg: BalancerConfig,
                 overrides: Dict[str, int], raw_cache: Dict[str, Dict[str, Any]]
                 ) -> List[ItemSpec]:
    """Пересчёт БЕЗ повторного сканирования: использует кэш извлечённых ТТХ."""
    out: List[ItemSpec] = []
    xm = 1.0 if cfg.use_additional_currencies else cfg.exchange_rate
    dm = cfg.exchange_rate if cfg.use_additional_currencies else 1.0

    for s in specs:
        c = raw_cache.get(s.unique_key)
        if not c:
            out.append(s)
            continue

        if s.item_type == "field":
            area = s.field_area if s.field_area > 0 else c.get("area", 0.0)
            dist = None if s.field_distance < 0 else s.field_distance
            base_eur = field_price(area, dist, cfg)
            s.base_price = clean_round(base_eur * xm)
            s.new_price = int(overrides.get(s.unique_key, s.base_price))
            s.new_price_rub = clean_round(base_eur * dm)
            s.country_mult = cfg.k_field
            if s.field_manual:
                s.needs_review = s.field_area <= 0 or (cfg.adjust_field_prices
                                                       and s.field_distance < 0)
            out.append(s)
            continue

        if s.item_type == "placeable":
            base_eur = calc_placeable_price(
                c.get("category", "misc"), s.title, s.xml_rel_path,
                c.get("cap", 0.0), c.get("slots", 0), c.get("prod", 0.0),
                cfg.k_placeable, cfg.global_difficulty_scale)
            k_c = cfg.multiplier_for(s.country) if s.country in _known_countries() else 1.0
            priced, k_c, k_r = apply_item_multipliers(base_eur, k_c, s.is_retro, cfg)
            s.base_price = clean_round(base_eur * xm)
            s.country_mult, s.retro_mult = k_c, k_r
            s.wear_mult = wear_for_item(s.is_retro, cfg)
            s.new_price = int(overrides.get(s.unique_key, clean_round(priced * xm)))
            s.new_price_rub = clean_round(priced * dm)
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
        s.new_price_rub = clean_round(s.new_price / xm * dm) if xm else s.new_price

        cnt = 0
        s.motor_prices = []
        for i, m in enumerate(s.motors):
            if i == 0:
                m.price_delta = 0
            else:
                m.price_delta = motor_price_for_delta(base_eur,
                                                      max(0.0, m.hp - c.get("hp", 0.0)),
                                                      k_country, xm, s.is_retro, cfg)
                cnt += 1
            s.motor_prices.append({"index": i, "label": m.label, "hp": m.hp,
                                   "speed": m.max_speed, "delta": m.price_delta,
                                   "total": clean_round(s.new_price + m.price_delta)})
        s.configs_updated = cnt
        out.append(s)

    return out


def _known_countries() -> set:
    from core.countries import ALL_COUNTRIES
    return set(ALL_COUNTRIES.keys())
