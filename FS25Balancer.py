#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FS25 — Автобалансировщик цен v15.0 (Premium Web Edition)
========================================================
Все страны мира + СССР • Ретро-техника • Комплектации двигателей
Поля с зависимостью от расстояния • PRO-режим по странам
UI: PyWebView (HTML5/CSS3/JS, glassmorphism, анимации)
Логика парсинга и расчётов v13/v14 сохранена полностью.
"""

import os, re, sys, math, json, shutil, zipfile, tempfile, threading, time
import queue, webbrowser
import urllib.request, urllib.error, urllib.parse
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum, auto
from collections import defaultdict, OrderedDict

APP_VERSION = "15.0"
APP_NAME = "FS25Balancer"

# ==============================================================================
# 1. ХРАНИЛИЩЕ (настройки, кэши, память ИИ)
# ==============================================================================

SETTINGS_FILE = "app_settings.json"
PRO_FILE = "pro_settings.json"
LEARNED_BRANDS_FILE = "learned_brands.json"
CACHE_FILE = "mods_cache_index.json"
PLACEABLES_FILE = "learned_placeables.json"
COUNTRIES_FILE = "selected_countries.json"
LAST_SCAN_FILE = "last_scan.json"


def data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config")
        path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = os.path.abspath(".")
    return path


def _path(name: str) -> str:
    return os.path.join(data_dir(), name)


def _legacy(name: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def load_json(name: str, default: Optional[Any] = None) -> Any:
    if default is None:
        default = {}
    p = _path(name)
    if not os.path.isfile(p):
        legacy = _legacy(name)
        if os.path.isfile(legacy):
            try:
                shutil.copy2(legacy, p)
            except Exception:
                pass
        else:
            return default() if callable(default) else default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default() if callable(default) else default


def save_json(name: str, data: Any) -> bool:
    p = _path(name)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ==============================================================================
# 2. ВСЕ СТРАНЫ МИРА + СССР
# ==============================================================================

# (имя, ISO2, дефолтный коэффициент, группа)
_RAW_COUNTRIES: List[Tuple[str, str, float, str]] = [
    # СНГ
    ("Россия", "RU", 0.42, "CIS"), ("СССР", "SU", 0.42, "CIS"),
    ("Беларусь", "BY", 0.42, "CIS"), ("Украина", "UA", 0.42, "CIS"),
    ("Казахстан", "KZ", 0.42, "CIS"), ("Узбекистан", "UZ", 0.40, "CIS"),
    ("Кыргызстан", "KG", 0.38, "CIS"), ("Таджикистан", "TJ", 0.36, "CIS"),
    ("Туркменистан", "TM", 0.40, "CIS"), ("Азербайджан", "AZ", 0.45, "CIS"),
    ("Армения", "AM", 0.42, "CIS"), ("Грузия", "GE", 0.45, "CIS"),
    ("Молдова", "MD", 0.45, "CIS"),
    # Европа / Запад
    ("Германия", "DE", 1.00, "WEST"), ("Франция", "FR", 1.00, "WEST"),
    ("Италия", "IT", 1.00, "WEST"), ("Испания", "ES", 0.95, "WEST"),
    ("Португалия", "PT", 0.90, "WEST"), ("Великобритания", "GB", 1.00, "WEST"),
    ("Ирландия", "IE", 1.00, "WEST"), ("Нидерланды", "NL", 1.00, "WEST"),
    ("Бельгия", "BE", 1.00, "WEST"), ("Люксембург", "LU", 1.05, "WEST"),
    ("Австрия", "AT", 1.00, "WEST"), ("Швейцария", "CH", 1.10, "WEST"),
    ("Польша", "PL", 0.55, "WEST"), ("Чехия", "CZ", 0.65, "WEST"),
    ("Словакия", "SK", 0.65, "WEST"), ("Венгрия", "HU", 0.70, "WEST"),
    ("Словения", "SI", 0.80, "WEST"), ("Хорватия", "HR", 0.65, "WEST"),
    ("Босния и Герцеговина", "BA", 0.55, "WEST"), ("Сербия", "RS", 0.55, "WEST"),
    ("Черногория", "ME", 0.55, "WEST"), ("Северная Македония", "MK", 0.50, "WEST"),
    ("Албания", "AL", 0.48, "WEST"), ("Греция", "GR", 0.75, "WEST"),
    ("Болгария", "BG", 0.55, "WEST"), ("Румыния", "RO", 0.60, "WEST"),
    ("Литва", "LT", 0.65, "WEST"), ("Латвия", "LV", 0.65, "WEST"),
    ("Эстония", "EE", 0.70, "WEST"), ("Швеция", "SE", 1.05, "WEST"),
    ("Норвегия", "NO", 1.10, "WEST"), ("Финляндия", "FI", 1.05, "WEST"),
    ("Дания", "DK", 1.00, "WEST"), ("Исландия", "IS", 1.05, "WEST"),
    ("Мальта", "MT", 0.85, "WEST"), ("Кипр", "CY", 0.80, "WEST"),
    ("Турция", "TR", 0.65, "WEST"), ("Андорра", "AD", 0.90, "WEST"),
    ("Монако", "MC", 1.05, "WEST"), ("Сан-Марино", "SM", 0.95, "WEST"),
    ("Лихтенштейн", "LI", 1.05, "WEST"),
    # Америка
    ("США", "US", 1.00, "WEST"), ("Канада", "CA", 1.00, "WEST"),
    ("Мексика", "MX", 0.70, "WEST"), ("Гватемала", "GT", 0.50, "LATAM"),
    ("Куба", "CU", 0.40, "LATAM"), ("Ямайка", "JM", 0.50, "LATAM"),
    ("Гаити", "HT", 0.35, "LATAM"), ("Доминиканская Республика", "DO", 0.55, "LATAM"),
    ("Багамы", "BS", 0.85, "LATAM"), ("Барбадос", "BB", 0.80, "LATAM"),
    ("Тринидад и Тобаго", "TT", 0.70, "LATAM"),
    ("Колумбия", "CO", 0.60, "LATAM"), ("Венесуэла", "VE", 0.40, "LATAM"),
    ("Эквадор", "EC", 0.50, "LATAM"), ("Перу", "PE", 0.55, "LATAM"),
    ("Боливия", "BO", 0.45, "LATAM"), ("Парагвай", "PY", 0.50, "LATAM"),
    ("Уругвай", "UY", 0.70, "LATAM"), ("Бразилия", "BR", 0.70, "LATAM"),
    ("Аргентина", "AR", 0.65, "LATAM"), ("Чили", "CL", 0.75, "LATAM"),
    ("Коста-Рика", "CR", 0.60, "LATAM"), ("Панама", "PA", 0.65, "LATAM"),
    ("Никарагуа", "NI", 0.42, "LATAM"), ("Гондурас", "HN", 0.42, "LATAM"),
    ("Сальвадор", "SV", 0.50, "LATAM"), ("Белиз", "BZ", 0.50, "LATAM"),
    ("Суринам", "SR", 0.48, "LATAM"), ("Гайана", "GY", 0.52, "LATAM"),
    # Азия и Ближний Восток
    ("Китай", "CN", 0.65, "ASIA"), ("Япония", "JP", 1.05, "ASIA"),
    ("Южная Корея", "KR", 0.95, "ASIA"), ("Тайвань", "TW", 0.95, "ASIA"),
    ("Монголия", "MN", 0.40, "ASIA"), ("Индия", "IN", 0.55, "ASIA"),
    ("Пакистан", "PK", 0.50, "ASIA"), ("Бангладеш", "BD", 0.45, "ASIA"),
    ("Шри-Ланка", "LK", 0.48, "ASIA"), ("Непал", "NP", 0.42, "ASIA"),
    ("Бутан", "BT", 0.40, "ASIA"), ("Таиланд", "TH", 0.60, "ASIA"),
    ("Вьетнам", "VN", 0.55, "ASIA"), ("Индонезия", "ID", 0.55, "ASIA"),
    ("Малайзия", "MY", 0.60, "ASIA"), ("Филиппины", "PH", 0.55, "ASIA"),
    ("Сингапур", "SG", 1.05, "ASIA"), ("Бруней", "BN", 0.85, "ASIA"),
    ("Мьянма", "MM", 0.40, "ASIA"), ("Камбоджа", "KH", 0.42, "ASIA"),
    ("Лаос", "LA", 0.40, "ASIA"), ("Восточный Тимор", "TL", 0.36, "ASIA"),
    ("Израиль", "IL", 1.00, "WEST"), ("Палестина", "PS", 0.42, "ASIA"),
    ("Иран", "IR", 0.55, "ASIA"), ("Ирак", "IQ", 0.50, "ASIA"),
    ("Саудовская Аравия", "SA", 0.90, "ASIA"), ("ОАЭ", "AE", 1.00, "ASIA"),
    ("Катар", "QA", 1.00, "ASIA"), ("Кувейт", "KW", 0.90, "ASIA"),
    ("Бахрейн", "BH", 0.85, "ASIA"), ("Оман", "OM", 0.85, "ASIA"),
    ("Иордания", "JO", 0.55, "ASIA"), ("Ливан", "LB", 0.50, "ASIA"),
    ("Сирия", "SY", 0.38, "ASIA"), ("Йемен", "YE", 0.35, "ASIA"),
    ("Афганистан", "AF", 0.32, "ASIA"), ("Мальдивы", "MV", 0.60, "ASIA"),
    # Африка
    ("Египет", "EG", 0.55, "AFRICA"), ("Ливия", "LY", 0.55, "AFRICA"),
    ("Тунис", "TN", 0.50, "AFRICA"), ("Алжир", "DZ", 0.50, "AFRICA"),
    ("Марокко", "MA", 0.55, "AFRICA"), ("Эфиопия", "ET", 0.40, "AFRICA"),
    ("Кения", "KE", 0.45, "AFRICA"), ("Танзания", "TZ", 0.40, "AFRICA"),
    ("Уганда", "UG", 0.40, "AFRICA"), ("Нигерия", "NG", 0.50, "AFRICA"),
    ("Гана", "GH", 0.48, "AFRICA"), ("Сенегал", "SN", 0.45, "AFRICA"),
    ("Кот-д’Ивуар", "CI", 0.45, "AFRICA"), ("Камерун", "CM", 0.42, "AFRICA"),
    ("ДР Конго", "CD", 0.35, "AFRICA"), ("Республика Конго", "CG", 0.45, "AFRICA"),
    ("Ангола", "AO", 0.45, "AFRICA"), ("Габон", "GA", 0.55, "AFRICA"),
    ("Замбия", "ZM", 0.42, "AFRICA"), ("Зимбабве", "ZW", 0.40, "AFRICA"),
    ("ЮАР", "ZA", 0.65, "AFRICA"), ("Мозамбик", "MZ", 0.38, "AFRICA"),
    ("Мадагаскар", "MG", 0.38, "AFRICA"), ("Буркина-Фасо", "BF", 0.38, "AFRICA"),
    ("Мали", "ML", 0.40, "AFRICA"), ("Нигер", "NE", 0.36, "AFRICA"),
    ("Чад", "TD", 0.36, "AFRICA"), ("Судан", "SD", 0.40, "AFRICA"),
    ("Южный Судан", "SS", 0.34, "AFRICA"), ("Эритрея", "ER", 0.36, "AFRICA"),
    ("Сомали", "SO", 0.34, "AFRICA"), ("Джибути", "DJ", 0.45, "AFRICA"),
    ("Руанда", "RW", 0.40, "AFRICA"), ("Бурунди", "BI", 0.34, "AFRICA"),
    ("Сьерра-Леоне", "SL", 0.36, "AFRICA"), ("Либерия", "LR", 0.36, "AFRICA"),
    ("Гвинея", "GN", 0.40, "AFRICA"), ("Гамбия", "GM", 0.38, "AFRICA"),
    ("Того", "TG", 0.38, "AFRICA"), ("Бенин", "BJ", 0.40, "AFRICA"),
    ("Мавритания", "MR", 0.42, "AFRICA"), ("Ботсвана", "BW", 0.60, "AFRICA"),
    ("Намибия", "NA", 0.55, "AFRICA"), ("Сейшелы", "SC", 0.75, "AFRICA"),
    ("Маврикий", "MU", 0.65, "AFRICA"), ("Кабо-Верде", "CV", 0.50, "AFRICA"),
    ("Эсватини", "SZ", 0.45, "AFRICA"), ("Лесото", "LS", 0.40, "AFRICA"),
    # Океания
    ("Австралия", "AU", 1.00, "WEST"), ("Новая Зеландия", "NZ", 1.00, "WEST"),
    ("Фиджи", "FJ", 0.55, "OCEANIA"), ("Папуа — Новая Гвинея", "PG", 0.42, "OCEANIA"),
    ("Соломоновы Острова", "SB", 0.42, "OCEANIA"), ("Вануату", "VU", 0.45, "OCEANIA"),
    ("Самоа", "WS", 0.50, "OCEANIA"), ("Тонга", "TO", 0.48, "OCEANIA"),
]

GROUP_LABELS = {
    "CIS": "СНГ / Восток", "WEST": "Запад и Европа", "ASIA": "Азия и Б. Восток",
    "LATAM": "Латинская Америка", "AFRICA": "Африка", "OCEANIA": "Океания",
}


def flag_of(iso2: str) -> str:
    """Emoji-флаг из ISO2 через региональные индикаторы; СССР — серп и молот."""
    if iso2 == "SU":
        return "☭"
    base = 0x1F1E6
    return "".join(chr(base + ord(c) - ord("A")) for c in iso2.upper())


def _build_countries() -> "OrderedDict[str, Dict[str, Any]]":
    out: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for name, iso2, k, group in _RAW_COUNTRIES:
        if name not in out:
            out[name] = {"flag": flag_of(iso2), "iso2": iso2, "k": k, "group": group}
    return out


ALL_COUNTRIES: Dict[str, Dict[str, Any]] = _build_countries()

DEFAULT_SELECTED_COUNTRIES = [
    "Россия", "СССР", "Беларусь", "Украина", "Казахстан",
    "Германия", "США", "Франция", "Польша", "Китай", "Япония", "Швеция",
]


def countries_payload() -> List[Dict[str, Any]]:
    return [
        {"name": n, "flag": i["flag"], "iso2": i["iso2"], "k": i["k"],
         "group": i["group"], "groupLabel": GROUP_LABELS.get(i["group"], i["group"])}
        for n, i in ALL_COUNTRIES.items()
    ]


def country_info(name: str) -> Dict[str, Any]:
    return ALL_COUNTRIES.get(name, {"flag": "🏳", "iso2": "??", "k": 1.0, "group": "OTHER"})


# Глобальные хранилища состояния (загружаются при старте)
LEARNED_BRANDS: Dict[str, str] = {}
MODS_CACHE: Dict[str, str] = {}
PLACEABLE_MEMORY: Dict[str, dict] = {}
SELECTED_COUNTRIES: List[str] = []
APP_SETTINGS: Dict[str, Any] = {}
PRO_DATA: Dict[str, Any] = {}
