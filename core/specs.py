# -*- coding: utf-8 -*-
"""Класс-зависимые правки ТТХ прямо в XML мода.

Поля описаны декларативно: редактор показывает только то, что реально есть
в XML данной позиции (техника / здание / прицеп / орудие), и пишет значения
в те же атрибуты и элементы, из которых их читает parser.py.
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from core.i18n import t as _t

FUEL_FILL_TYPES = {"diesel", "def", "electriccharge", "pigfood", "chickenfeed"}

# key -> метаданные поля для UI и валидации.
# label/unit — ключи i18n (см. core/i18n.py), подписи меняются вместе с языком.
SPEC_FIELDS: Dict[str, Dict[str, Any]] = {
    "hp": {"label": "hp", "unit": "hp", "min": 0, "max": 3000, "step": 1,
           "kinds": ("vehicle",), "readonly": False},
    "max_speed": {"label": "max_speed", "unit": "kmh", "min": 0, "max": 200, "step": 1,
                  "kinds": ("vehicle",), "readonly": False},
    "capacity": {"label": "capacity", "unit": "liter", "min": 0, "max": 500000, "step": 50,
                 "kinds": ("vehicle", "placeable"), "readonly": False},
    "working_width": {"label": "working_width", "unit": "meter", "min": 0, "max": 60, "step": 0.1,
                      "kinds": ("vehicle",), "readonly": False},
    "needed_hp": {"label": "needed_hp", "unit": "hp", "min": 0, "max": 3000, "step": 1,
                  "kinds": ("vehicle",), "readonly": False},
    "production_cost": {"label": "production_cost", "unit": "rub_hour", "min": 0, "max": 100000,
                        "step": 10, "kinds": ("placeable",), "readonly": False},
    "slots": {"label": "slots", "unit": "pcs", "min": 0, "max": 512, "step": 1,
              "kinds": ("placeable",), "readonly": True},
    # ── производства и точки продажи (v16) ──
    "prod_cycles": {"label": "prod_cycles", "unit": "cph", "min": 0, "max": 200, "step": 0.1,
                    "kinds": ("placeable",), "readonly": False},
    "prod_output": {"label": "prod_output", "unit": "percycle", "min": 0, "max": 5000000, "step": 50,
                    "kinds": ("placeable",), "readonly": False},
    "prod_input": {"label": "prod_input", "unit": "percycle", "min": 0, "max": 5000000, "step": 50,
                   "kinds": ("placeable",), "readonly": False},
    "prod_cost_month": {"label": "prod_cost_month", "unit": "rub_month", "min": 0, "max": 5000000,
                        "step": 50, "kinds": ("placeable",), "readonly": False},
    "storage_capacity": {"label": "storage_capacity", "unit": "liter", "min": 0, "max": 20000000,
                         "step": 500, "kinds": ("placeable",), "readonly": False},
    # goods_count в XML не записывается: это ручная поправка к автоподсчёту товаров
    "goods_count": {"label": "goods_count", "unit": "pcs", "min": 0, "max": 512, "step": 1,
                    "kinds": ("placeable",), "readonly": False, "meta_only": True},
}

EDITABLE_KEYS = ("hp", "max_speed", "capacity", "working_width", "needed_hp",
                 "production_cost", "prod_cycles", "prod_output", "prod_input",
                 "prod_cost_month", "storage_capacity", "goods_count")


def field_label(key: str, lang: Optional[str] = "ru") -> str:
    return _t("spec." + str(key), lang)


def field_unit(key: str, lang: Optional[str] = "ru") -> str:
    meta = SPEC_FIELDS.get(str(key)) or {}
    return _t("unit." + str(meta.get("unit", "")), lang)


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return f


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else ("%g" % v)


def _ensure_specs(sd: ET.Element) -> ET.Element:
    ss = sd.find("specs")
    if ss is None:
        ss = ET.SubElement(sd, "specs")
        children = list(sd)
        sd.remove(ss)
        idx = 0
        for i, ch in enumerate(children):
            if ch.tag in ("price", "dailyUpkeep", "category"):
                idx = i + 1
        sd.insert(min(idx, len(sd)), ss)
    return ss


def _set_child(sd: ET.Element, name: str, value: float) -> None:
    ss = _ensure_specs(sd)
    el = ss.find(name)
    if el is None:
        el = ET.SubElement(ss, name)
    el.text = _fmt(value)


def _is_fuel_only(fu: ET.Element) -> bool:
    ft = (fu.get("fillTypes") or "").lower().split()
    if ft and all(f in FUEL_FILL_TYPES for f in ft):
        return True
    fc = (fu.get("fillTypeCategories") or "").lower().split()
    if "slurrytank" not in fc and ft and ("diesel" in ft or "def" in ft) and len(ft) <= 2:
        return True
    return False


def present_fields(root: ET.Element, item_type: str) -> List[str]:
    """Какие ТТХ есть у этого XML — только их и показываем в редакторе."""
    sd = root.find("storeData")
    if sd is None:
        return []
    ss = sd.find("specs")
    out: List[str] = []
    has_mc = root.findall(".//motorConfigurations/motorConfiguration")
    if item_type == "vehicle":
        if (ss is not None and ss.find("power") is not None) or has_mc:
            out.append("hp")
        if (ss is not None and ss.find("maxSpeed") is not None) or \
           any(m.find("motor") is not None and m.find("motor").get("maxForwardSpeed") for m in has_mc):
            out.append("max_speed")
        if (root.findall(".//fillUnitConfigurations/fillUnitConfiguration") or
                (ss is not None and ss.find("capacity") is not None)):
            out.append("capacity")
        if (ss is not None and ss.find("workingWidth") is not None) or \
                root.findall(".//workAreas/workArea"):
            out.append("working_width")
        if ss is not None and ss.find("neededPower") is not None:
            out.append("needed_hp")
    else:
        if root.findall(".//storages/storage/node") or root.findall(".//fillUnit") or \
                (ss is not None and ss.find("capacity") is not None):
            out.append("capacity")
        if root.findall(".//slots/slot") or root.findall(".//stalls/stall"):
            out.append("slots")
        if root.findall(".//productions/production"):
            out.extend(("prod_cycles", "prod_output",
                        "prod_input", "prod_cost_month"))
        if root.findall(".//storage"):
            out.append("storage_capacity")
        if root.find(".//sellingStation") is not None:
            out.append("goods_count")
    return [k for k in out if k in SPEC_FIELDS]


def _patch_hp(root: ET.Element, sd: ET.Element, v: float) -> None:
    _set_child(sd, "power", v)
    configs = root.findall(".//motorConfigurations/motorConfiguration")
    if not configs:
        return
    olds = [_num(c.get("hp")) for c in configs]
    base = next((o for o in olds if o > 0), v)
    delta = v - base
    for c, old in zip(configs, olds):
        if old <= 0:
            continue
        c.set("hp", _fmt(max(0.0, old + delta)))
        motor = c.find("motor")
        torque = _num(motor.get("torqueScale")) if motor is not None else 0.0
        if motor is not None and old > 0 and torque > 0:
            motor.set("torqueScale", _fmt(torque * max(0.0, old + delta) / old))


def _patch_speed(root: ET.Element, sd: ET.Element, v: float) -> None:
    _set_child(sd, "maxSpeed", v)
    for motor in root.findall(".//motorConfiguration/motor"):
        motor.set("maxForwardSpeed", _fmt(v))


def _patch_capacity(root: ET.Element, sd: ET.Element, v: float, item_type: str) -> int:
    if item_type == "vehicle":
        cfgs = root.findall(".//fillUnitConfigurations/fillUnitConfiguration")
        targets: List[ET.Element] = []
        if cfgs:
            targets = [fu for fu in cfgs[0].findall(".//fillUnit") if not _is_fuel_only(fu)]
        if not targets:
            targets = [fu for fu in root.findall(".//fillUnit") if not _is_fuel_only(fu)]
        if targets:
            each = v / len(targets)
            for fu in targets:
                fu.set("capacity", _fmt(round(each, 2)))
            return len(targets)
        _set_child(sd, "capacity", v)
        return 1
    nodes = [n for n in root.findall(".//storages/storage/node") if _num(n.get("capacity")) > 0]
    if nodes:
        each = v / len(nodes)
        for n in nodes:
            n.set("capacity", _fmt(round(each, 2)))
        return len(nodes)
    fus = root.findall(".//fillUnit")
    if fus:
        each = v / len(fus)
        for fu in fus:
            fu.set("capacity", _fmt(round(each, 2)))
        return len(fus)
    _set_child(sd, "capacity", v)
    return 1


def _patch_production(root: ET.Element, v: float) -> int:
    prods = root.findall(".//productions/production")
    if not prods:
        return 0
    each = v / len(prods)
    known = ("costsPerActiveHour", "costsPerActiveMonth", "costPerActiveHour", "costPerActiveMonth")
    for p in prods:
        present = [k for k in known if p.get(k) is not None]
        if not present:
            p.set("costsPerActiveHour", _fmt(round(each, 2)))
            continue
        # держим все уже имеющиеся атрибуты стоимости согласованными: иначе мод
        # с опечаткой (costPerActiveHour) начнёт показывать старую цифру
        for k in present:
            mult = 24.0 if "Month" in k else 1.0
            p.set(k, _fmt(round(each * mult, 2)))
    return len(prods)


def _prod_nodes(root: ET.Element) -> List[ET.Element]:
    return root.findall(".//productions/production")


def _line_children(root: ET.Element, tag: str) -> List[ET.Element]:
    return root.findall("./" + tag) + root.findall("./" + tag + "s/" + tag)


def _scale_attr(nodes: List[ET.Element], attribute: str, total: float) -> int:
    if not nodes:
        return 0
    current = sum(_num(node.get(attribute)) for node in nodes)
    for node in nodes:
        value = total * _num(node.get(attribute)) / current if current > 0 else total / len(nodes)
        node.set(attribute, _fmt(round(value, 6)))
    return len(nodes)


def _patch_cycles(root: ET.Element, value: float) -> int:
    return _scale_attr(_prod_nodes(root), "cyclesPerHour", value)


def _patch_month_cost(root: ET.Element, value: float) -> int:
    return _scale_attr(_prod_nodes(root), "costsPerActiveMonth", value)


def _patch_storage_cap(root: ET.Element, value: float) -> int:
    targets = []
    for storage in root.findall(".//storage"):
        capacities = storage.findall("./capacity")
        if capacities:
            targets.extend(capacities)
        elif storage.get("capacity") is not None:
            targets.append(storage)
        else:
            targets.extend(storage.findall("./node"))
    return _scale_attr(targets, "capacity", value)


def apply_patch(root: ET.Element, patch: Dict[str, Any], item_type: str) -> Tuple[List[str], List[str]]:
    """Пишет патч в дерево XML (в памяти). Возвращает (применённые поля, предупреждения)."""
    sd = root.find("storeData")
    done: List[str] = []
    warns: List[str] = []
    if sd is None:
        return done, ["нет storeData — правки невозможны"]
    for key in EDITABLE_KEYS:
        if key not in (patch or {}):
            continue
        meta = SPEC_FIELDS[key]
        raw = _num(patch[key])
        if meta.get("meta_only"):
            continue          # goods_count: влияет только на расчёт, XML не правим
        val = min(float(meta["max"]), max(float(meta["min"]), raw))
        if val != raw:
            warns.append("%s: %s–%s" % (meta["label"], meta["min"], meta["max"]))
        n = 0
        if key == "hp":
            _patch_hp(root, sd, val)
        elif key == "max_speed":
            _patch_speed(root, sd, val)
        elif key == "capacity":
            n = _patch_capacity(root, sd, val, item_type)
        elif key == "working_width":
            _set_child(sd, "workingWidth", val)
        elif key == "needed_hp":
            _set_child(sd, "neededPower", val)
        elif key == "production_cost":
            n = _patch_production(root, val)
        elif key == "prod_cycles":
            n = _patch_cycles(root, val)
        elif key in ("prod_output", "prod_input"):
            tag = "output" if key == "prod_output" else "input"
            nodes = _prod_nodes(root)
            n = _scale_attr([child for line in nodes for child in _line_children(line, tag)], "amount", val)
        elif key == "prod_cost_month":
            n = _patch_month_cost(root, val)
        elif key == "storage_capacity":
            n = _patch_storage_cap(root, val)
        if n > 1 and key not in ("capacity", "production_cost"):
            warns.append("%s: значение распределено на %d узлов" % (meta["label"], n))
        done.append(key)
    if "slots" in (patch or {}):
        warns.append("slots")
    return done, warns
