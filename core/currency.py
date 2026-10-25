# -*- coding: utf-8 -*-
"""Поиск мода Additional Currencies и его рублёвого курса прямо в папке mods.

Формат currencies.xml подтверждён по файлам самого мода (FS25_additionalCurrencies.zip):
  <currencies euroFactor="1" dolarFactor="1.06" poundFactor="0.83">
    <currency text="$l10n_unit_russianRuble" symbol="руб" factor="112.66" .../>
  </currencies>
Мод меняет только ОТОБРАЖЕНИЕ денег (g_i18n:formatMoney домножает число на factor,
когда опция «конвертер» включена), поэтому内部 цена в игре остаётся в EUR.
"""

import os
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, Optional

AC_NAME_HINTS = ("additionalcurrenc", "additional_currenc", "currenc", "waluta", "currency")


def _ruble_factor(xml_bytes: bytes) -> Optional[float]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    for cur in root.findall("currency"):
        blob = ((cur.get("text") or "") + " " + (cur.get("symbol") or "")).lower()
        if "ruble" in blob or "руб" in blob:
            try:
                f = float(cur.get("factor"))
            except (TypeError, ValueError):
                return None
            return f if 0.01 <= f <= 100000 else None
    return None


def _read_currencies_xml(path: str) -> Optional[bytes]:
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                for n in zf.namelist():
                    if n.replace("\\", "/").lower().endswith("currencies.xml"):
                        return zf.read(n)
        except (OSError, zipfile.BadZipFile):
            return None
        return None
    fp = os.path.join(path, "currencies.xml")
    if os.path.isfile(fp):
        try:
            with open(fp, "rb") as f:
                return f.read()
        except OSError:
            return None
    return None


def detect(mods_dir: str) -> Dict[str, Any]:
    """Ищет мод доп. валют в mods_dir и возвращает его рублёвый курс, если найден."""
    out: Dict[str, Any] = {"found": False, "mod": "", "rate": None, "mods_dir": mods_dir or ""}
    if not mods_dir or not os.path.isdir(mods_dir):
        return out
    try:
        names = sorted(os.listdir(mods_dir))
    except OSError:
        return out
    for name in names:
        if name.startswith("_backup"):
            continue
        p = os.path.join(mods_dir, name)
        is_zip = name.lower().endswith(".zip")
        if not (is_zip or os.path.isdir(p)):
            continue
        norm = name.lower().replace("_", "").replace(" ", "")
        if not any(h.replace("_", "") in norm for h in AC_NAME_HINTS):
            continue
        out["found"] = True
        out["mod"] = name
        data = _read_currencies_xml(p)
        if data:
            out["rate"] = _ruble_factor(data)
        return out
    return out
