#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FS25 — Автобалансировщик цен v14.0 (World Edition)
=====================================================
Все страны мира (вкл. СССР) • Ретро техника • Комплектации двигателей
Поля с учётом расстояния • Современный UI с анимациями
"""

import os, re, sys, math, json, shutil, zipfile, tempfile, threading, time
import urllib.request, urllib.error, urllib.parse
import subprocess, webbrowser, hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Any
from enum import Enum, auto
from collections import defaultdict, OrderedDict

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False


# ==============================================================================
# 1. ПАЛИТРА, АНИМАЦИИ, СТИЛИ
# ==============================================================================

BG_OBSIDIAN    = "#0b0d11"
BG_CARD        = "#14161e"
BG_INPUT       = "#1c1e2a"
BG_HOVER       = "#252838"
FG_TEXT         = "#f0f2f8"
FG_MUTED       = "#7a819b"
FG_DIM         = "#4a4f6a"
ACCENT_INDIGO  = "#6366f1"
ACCENT_HOVER   = "#4f46e5"
ACCENT_GREEN   = "#22c55e"
ACCENT_EMERALD = "#10b981"
ACCENT_AMBER   = "#f59e0b"
ACCENT_RED     = "#ef4444"
ACCENT_CYAN    = "#06b6d4"
ACCENT_PURPLE  = "#a855f7"
ACCENT_ROSE    = "#f43f5e"
BORDER_SUBTLE  = "#2a2d3e"
GRADIENT_START = "#1e1b4b"
GRADIENT_END   = "#0f172a"

ANIM_PULSE_COLORS = ["#6366f1", "#818cf8", "#a5b4fc", "#818cf8", "#6366f1"]
ANIM_SCAN_FRAMES  = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AnimationEngine:
    """Движок анимаций для визуализации процессов"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._pulse_jobs: Dict[str, str] = {}
        self._spinner_jobs: Dict[str, str] = {}
        self._progress_jobs: Dict[str, str] = {}

    def pulse_label(self, label, key: str = "default", idx: int = 0):
        if key in self._pulse_jobs:
            color = ANIM_PULSE_COLORS[idx % len(ANIM_PULSE_COLORS)]
            try:
                label.configure(foreground=color)
            except tk.TclError:
                return
            job = self.root.after(180, self.pulse_label, label, key, idx + 1)
            self._pulse_jobs[key] = job

    def start_pulse(self, label, key: str = "default"):
        self._pulse_jobs[key] = ""
        self.pulse_label(label, key, 0)

    def stop_pulse(self, key: str = "default"):
        if key in self._pulse_jobs:
            job = self._pulse_jobs.pop(key)
            if job:
                self.root.after_cancel(job)

    def spinner_label(self, label, key: str = "spin", prefix: str = "", idx: int = 0):
        if key in self._spinner_jobs:
            frame = ANIM_SCAN_FRAMES[idx % len(ANIM_SCAN_FRAMES)]
            try:
                label.configure(text=f"{frame} {prefix}")
            except tk.TclError:
                return
            job = self.root.after(100, self.spinner_label, label, key, prefix, idx + 1)
            self._spinner_jobs[key] = job

    def start_spinner(self, label, key: str = "spin", prefix: str = ""):
        self._spinner_jobs[key] = ""
        self.spinner_label(label, key, prefix, 0)

    def stop_spinner(self, key: str = "spin"):
        if key in self._spinner_jobs:
            job = self._spinner_jobs.pop(key)
            if job:
                self.root.after_cancel(job)

    def animate_counter(self, label, target: int, current: int = 0,
                        prefix: str = "", suffix: str = "", step: int = 1):
        if current >= target:
            try:
                label.configure(text=f"{prefix}{target:,}{suffix}".replace(",", " "))
            except tk.TclError:
                pass
            return
        inc = max(1, (target - current) // 15)
        nxt = min(current + inc, target)
        try:
            label.configure(text=f"{prefix}{nxt:,}{suffix}".replace(",", " "))
        except tk.TclError:
            return
        self.root.after(30, self.animate_counter, label, target, nxt, prefix, suffix, step)

    def flash_widget(self, widget, color: str, original_color: str, times: int = 3, idx: int = 0):
        if idx >= times * 2:
            try:
                widget.configure(foreground=original_color)
            except tk.TclError:
                pass
            return
        c = color if idx % 2 == 0 else original_color
        try:
            widget.configure(foreground=c)
        except tk.TclError:
            return
        self.root.after(200, self.flash_widget, widget, color, original_color, times, idx + 1)

    def stop_all(self):
        for key in list(self._pulse_jobs.keys()):
            self.stop_pulse(key)
        for key in list(self._spinner_jobs.keys()):
            self.stop_spinner(key)


class SplashScreen(tk.Toplevel):
    """Красивая анимация при запуске приложения"""

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=BG_OBSIDIAN)

        w, h = 540, 320
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.canvas = tk.Canvas(self, width=w, height=h, bg=BG_OBSIDIAN, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Декоративные линии
        for i in range(5):
            y_off = 20 + i * 65
            alpha_hex = format(max(20, 60 - i * 10), '02x')
            line_color = f"#6366f1{alpha_hex}" if len(f"#6366f1") == 7 else ACCENT_INDIGO
            self.canvas.create_line(30, y_off, w - 30, y_off,
                                     fill=BORDER_SUBTLE, width=1, dash=(4, 8))

        # Иконка
        self.icon_lbl = tk.Label(self.canvas, text="⚙️",
                                  font=("Segoe UI Emoji", 48),
                                  bg=BG_OBSIDIAN, fg=ACCENT_INDIGO)
        self.canvas.create_window(w // 2, h // 3 - 20, window=self.icon_lbl)

        # Заголовок
        self.title_lbl = tk.Label(self.canvas, text="FS25 Балансировщик",
                                   font=("Segoe UI", 24, "bold"),
                                   bg=BG_OBSIDIAN, fg=ACCENT_INDIGO)
        self.canvas.create_window(w // 2, h // 3 + 30, window=self.title_lbl)

        # Подзаголовок
        self.sub_lbl = tk.Label(self.canvas, text="v14.0 World Edition",
                                font=("Segoe UI", 12), bg=BG_OBSIDIAN, fg=FG_MUTED)
        self.canvas.create_window(w // 2, h // 3 + 65, window=self.sub_lbl)

        # Прогресс
        self.progress_lbl = tk.Label(self.canvas, text="Инициализация...",
                                     font=("Segoe UI", 9), bg=BG_OBSIDIAN, fg=ACCENT_CYAN)
        self.canvas.create_window(w // 2, h - 80, window=self.progress_lbl)

        self.progress = ttk.Progressbar(self.canvas, length=350, mode="determinate")
        self.canvas.create_window(w // 2, h - 50, window=self.progress)

        self.pulse_idx = 0
        self._anim_running = True
        self.animate_pulse()

    def animate_pulse(self):
        if not self._anim_running:
            return
        colors = ANIM_PULSE_COLORS
        color = colors[self.pulse_idx % len(colors)]
        try:
            self.title_lbl.configure(fg=color)
            self.icon_lbl.configure(fg=color)
        except tk.TclError:
            return
        self.pulse_idx += 1
        self.after(250, self.animate_pulse)

    def update_progress(self, value, text):
        try:
            self.progress["value"] = value
            self.progress_lbl.configure(text=text)
            self.update()
        except tk.TclError:
            pass

    def close(self):
        self._anim_running = False
        try:
            self.destroy()
        except tk.TclError:
            pass


# ==============================================================================
# 2. ВСЕ СТРАНЫ МИРА И РЕГИОНЫ
# ==============================================================================

ALL_COUNTRIES = OrderedDict([
    ("Россия",       {"flag": "🇷🇺", "k": 0.42, "group": "CIS"}),
    ("СССР",         {"flag": "☭",  "k": 0.42, "group": "CIS"}),
    ("Беларусь",     {"flag": "🇧🇾", "k": 0.42, "group": "CIS"}),
    ("Украина",      {"flag": "🇺🇦", "k": 0.42, "group": "CIS"}),
    ("Казахстан",    {"flag": "🇰🇿", "k": 0.42, "group": "CIS"}),
    ("Узбекистан",   {"flag": "🇺🇿", "k": 0.42, "group": "CIS"}),
    ("Грузия",       {"flag": "🇬🇪", "k": 0.42, "group": "CIS"}),
    ("Польша",       {"flag": "🇵🇱", "k": 0.55, "group": "CIS"}),
    ("Чехия",        {"flag": "🇨🇿", "k": 0.65, "group": "WEST"}),
    ("Словакия",     {"flag": "🇸🇰", "k": 0.65, "group": "WEST"}),
    ("Германия",     {"flag": "🇩🇪", "k": 1.00, "group": "WEST"}),
    ("Франция",      {"flag": "🇫🇷", "k": 1.00, "group": "WEST"}),
    ("Италия",       {"flag": "🇮🇹", "k": 1.00, "group": "WEST"}),
    ("Испания",      {"flag": "🇪🇸", "k": 0.95, "group": "WEST"}),
    ("Великобритания", {"flag": "🇬🇧", "k": 1.00, "group": "WEST"}),
    ("Швеция",       {"flag": "🇸🇪", "k": 1.05, "group": "WEST"}),
    ("Норвегия",     {"flag": "🇳🇴", "k": 1.05, "group": "WEST"}),
    ("Финляндия",    {"flag": "🇫🇮", "k": 1.05, "group": "WEST"}),
    ("Дания",        {"flag": "🇩🇰", "k": 1.00, "group": "WEST"}),
    ("Нидерланды",   {"flag": "🇳🇱", "k": 1.00, "group": "WEST"}),
    ("Бельгия",      {"flag": "🇧🇪", "k": 1.00, "group": "WEST"}),
    ("Австрия",      {"flag": "🇦🇹", "k": 1.00, "group": "WEST"}),
    ("Швейцария",    {"flag": "🇨🇭", "k": 1.10, "group": "WEST"}),
    ("Венгрия",      {"flag": "🇭🇺", "k": 0.70, "group": "WEST"}),
    ("Румыния",      {"flag": "🇷🇴", "k": 0.60, "group": "WEST"}),
    ("Болгария",     {"flag": "🇧🇬", "k": 0.55, "group": "WEST"}),
    ("Сербия",       {"flag": "🇷🇸", "k": 0.55, "group": "WEST"}),
    ("Хорватия",     {"flag": "🇭🇷", "k": 0.65, "group": "WEST"}),
    ("Турция",       {"flag": "🇹🇷", "k": 0.65, "group": "WEST"}),
    ("США",          {"flag": "🇺🇸", "k": 1.00, "group": "WEST"}),
    ("Канада",       {"flag": "🇨🇦", "k": 1.00, "group": "WEST"}),
    ("Мексика",      {"flag": "🇲🇽", "k": 0.70, "group": "WEST"}),
    ("Бразилия",     {"flag": "🇧🇷", "k": 0.70, "group": "WEST"}),
    ("Аргентина",    {"flag": "🇦🇷", "k": 0.65, "group": "WEST"}),
    ("Чили",         {"flag": "🇨🇱", "k": 0.65, "group": "WEST"}),
    ("Колумбия",     {"flag": "🇨🇴", "k": 0.60, "group": "WEST"}),
    ("Австралия",    {"flag": "🇦🇺", "k": 1.00, "group": "WEST"}),
    ("Новая Зеландия", {"flag": "🇳🇿", "k": 1.00, "group": "WEST"}),
    ("Китай",        {"flag": "🇨🇳", "k": 0.65, "group": "ASIA"}),
    ("Япония",       {"flag": "🇯🇵", "k": 1.05, "group": "ASIA"}),
    ("Южная Корея",  {"flag": "🇰🇷", "k": 0.95, "group": "ASIA"}),
    ("Индия",        {"flag": "🇮🇳", "k": 0.55, "group": "ASIA"}),
    ("Таиланд",      {"flag": "🇹🇭", "k": 0.60, "group": "ASIA"}),
    ("Вьетнам",      {"flag": "🇻🇳", "k": 0.55, "group": "ASIA"}),
    ("Индонезия",    {"flag": "🇮🇩", "k": 0.55, "group": "ASIA"}),
    ("Малайзия",     {"flag": "🇲🇾", "k": 0.60, "group": "ASIA"}),
    ("Филиппины",    {"flag": "🇵🇭", "k": 0.55, "group": "ASIA"}),
    ("Пакистан",     {"flag": "🇵🇰", "k": 0.50, "group": "ASIA"}),
    ("Иран",         {"flag": "🇮🇷", "k": 0.55, "group": "ASIA"}),
    ("Ирак",         {"flag": "🇮🇶", "k": 0.50, "group": "ASIA"}),
    ("Египет",       {"flag": "🇪🇬", "k": 0.55, "group": "ASIA"}),
    ("ЮАР",          {"flag": "🇿🇦", "k": 0.65, "group": "ASIA"}),
    ("Нигерия",      {"flag": "🇳🇬", "k": 0.50, "group": "ASIA"}),
    ("Израиль",      {"flag": "🇮🇱", "k": 1.00, "group": "WEST"}),
])

DEFAULT_SELECTED_COUNTRIES = ["Россия", "СССР", "Беларусь", "Германия", "США", "Китай"]

DEFAULT_AI_PROMPT = (
    "Expert FS25 mod classifier. Classify the country/region for this equipment:\n"
    "Mod: {mod_name} | File: {filename} | Brand: {brand} | Title: {title}\n\n"
    "Available countries: {countries}\n\n"
    "Also determine if this is RETRO/VINTAGE equipment (old Soviet, classic models).\n\n"
    "Reply in format: COUNTRY_NAME|RETRO or COUNTRY_NAME|MODERN\n"
    "Example: Россия|RETRO or Германия|MODERN\n"
    "Reply with ONLY ONE LINE:"
)


# ==============================================================================
# 3. ФАЙЛЫ ПАМЯТИ И НАСТРОЙКИ
# ==============================================================================

LEARNED_BRANDS_FILE  = "learned_brands.json"
CACHE_INDEX_FILE     = "mods_cache_index.json"
SETTINGS_FILE        = "app_settings.json"
PRO_SETTINGS_FILE    = "pro_settings.json"
LEARNED_PLACEABLES   = "learned_placeables.json"
COUNTRIES_FILE       = "selected_countries.json"


def load_json(path: str, default=None):
    if default is None:
        default = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default if not callable(default) else default()


def save_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


LEARNED_BRANDS: Dict[str, str]       = load_json(LEARNED_BRANDS_FILE, {})
MODS_CACHE: Dict[str, str]           = load_json(CACHE_INDEX_FILE, {})
APP_SETTINGS: Dict[str, Any]         = load_json(SETTINGS_FILE, {"show_tutorial": True, "show_startup_guide": True})
PLACEABLE_MEMORY: Dict[str, dict]    = load_json(LEARNED_PLACEABLES, {})
SELECTED_COUNTRIES: List[str]        = load_json(COUNTRIES_FILE, DEFAULT_SELECTED_COUNTRIES)

# Гарантируем что выбранные страны существуют
SELECTED_COUNTRIES = [c for c in SELECTED_COUNTRIES if c in ALL_COUNTRIES]
if not SELECTED_COUNTRIES:
    SELECTED_COUNTRIES = list(DEFAULT_SELECTED_COUNTRIES)


# ==============================================================================
# 4. БАЗЫ БРЕНДОВ ПО СТРАНАМ (ПРО-режим)
# ==============================================================================

DEFAULT_COUNTRY_BRANDS = {
    "Россия": [
        "gaz", "kamaz", "maz", "zil", "ural", "kraz", "uaz", "paz", "liaz", "kavz",
        "mtz", "belarus", "kirovets", "ptz", "k700", "k701", "k744", "k525",
        "htz", "t150", "dt75", "vtz", "umz", "t40", "t25", "t16", "chtz",
        "agromash", "terrion", "amkodor", "rostselmash", "rsm", "acros", "torum",
        "vector", "nova", "don", "sk5", "yenisei", "gomselmash", "palesse",
        "nefaz", "szap", "tonar", "pts", "2pts", "pim", "prt", "pku", "bdm",
        "veles", "bobruisk", "lidselmash", "voronezh", "belama", "arzamas", "oztp",
        "salskselmash", "chervona", "kuban", "moroz", "rubarz", "fmz", "orkanz"
    ],
    "СССР": [
        "zil-130", "zil130", "zil-131", "zil131", "zil-157", "gaz-52", "gaz-53",
        "gaz53", "gaz-66", "gaz66", "gaz-69", "uaz-469", "uaz469", "uaz-452",
        "mtz-50", "mtz50", "mtz-80", "mtz80", "umz-6", "umz6", "dt-75", "dt75",
        "t-40", "t40", "t-25", "t25", "t-16", "t16", "t-150k", "t150k",
        "k-700", "k700", "k-701", "k701", "sk-5", "sk5", "don-1500", "don1500",
        "kraz-255", "kraz255", "maz-500", "kamaz-5320", "kamaz5320", "2pts-4"
    ],
    "Беларусь": ["mtz", "belarus", "gomselmash", "palesse", "amkodor", "belaz", "mzkt", "volat"],
    "Украина": ["htz", "kraz", "laz", "bogdan"],
    "Казахстан": [],
    "Германия": [
        "claas", "fendt", "deutz-fahr", "man", "mercedes", "krone", "grimme",
        "ropa", "holmer", "lemken", "kuhn", "amazone", "cramer", "wiedenmann"
    ],
    "США": [
        "johndeere", "john deere", "case", "case ih", "international",
        "international harvester", "cat", "caterpillar", "mack", "peterbilt",
        "kenworth", "jcb", "bell", "allischalmers", "canam"
    ],
    "Франция": ["manitou", "renault", "peugeot", "citroen"],
    "Италия": ["laverda", "goldoni", "pasquali", "valpadana", "antonio carraro"],
    "Великобритания": ["jcb", "massey ferguson", "marshall"],
    "Швеция": ["volvo", "scania", "valtra", "ponsse", "rottne"],
    "Финляндия": ["valtra", "ponsse", "jukka"],
    "Нидерланды": ["kuhn", "vicon", "rauch"],
    "Австрия": ["steyr", "poettinger"],
    "Швейцария": ["bucher"],
    "Япония": [
        "kubota", "iseki", "yanmar", "toyota", "mitsubishi", "komatsu",
        "hitachi", "sumitomo", "kobelco"
    ],
    "Южная Корея": ["ls", "kioti", "tym", "branson", "daedong", "hyundai", "doosan"],
    "Китай": [
        "shacman", "shaanxi", "faw", "howo", "sinotruk", "dongfeng", "foton",
        "jac", "sitrak", "lovol", "yto", "zoomlion", "xcmg", "liugong", "sdlg",
        "shantui", "chery", "haval", "geely", "changan", "greatwall", "baic",
        "mahindra", "changfa", "changzhou", "shifeng"
    ],
    "Индия": ["mahindra", "swaraj", "sonalika", "escort", "new holland india"],
    "Бразилия": ["massey brasil", "valtra brasil"],
    "Турция": ["tumosan", "hars", "erkunt"],
    "Польша": ["unia", "bomet", "sipma", "metalfach", "polsrem", "rolmako",
               "krukowiak", "agrotom", "agrozet", "biardzki"],
    "Чехия": ["zetor", "brantner"],
}

PRO_DATA = load_json(PRO_SETTINGS_FILE, {
    "custom_prompt": DEFAULT_AI_PROMPT,
    "country_brands": DEFAULT_COUNTRY_BRANDS
})

# Merge defaults with saved
for country, brands in DEFAULT_COUNTRY_BRANDS.items():
    if country not in PRO_DATA.get("country_brands", {}):
        PRO_DATA["country_brands"][country] = brands



# ==============================================================================
# 5. УТИЛИТЫ И СТРУКТУРЫ ДАННЫХ
# ==============================================================================

class ScanTarget(Enum):
    VEHICLES   = auto()
    PLACEABLES = auto()
    FIELDS     = auto()
    ALL        = auto()


SCAN_TARGET_LABELS = {
    ScanTarget.VEHICLES:   "🚜 Техника",
    ScanTarget.PLACEABLES: "🏗️ Здания и объекты",
    ScanTarget.FIELDS:     "🌾 Поля",
    ScanTarget.ALL:        "📦 Всё (техника + здания + поля)",
}


@dataclass
class BalancerConfig:
    use_additional_currencies: bool = True
    exchange_rate: float = 100.0
    country_multipliers: Dict[str, float] = field(default_factory=dict)
    k_placeable: float = 1.0
    k_field: float = 1.0
    k_retro: float = 0.65
    retro_wear: float = 0.15
    global_difficulty_scale: float = 1.0
    create_backups: bool = True
    use_local_ai: bool = True
    ai_model_name: str = "phi3"
    scan_target: ScanTarget = ScanTarget.ALL
    adjust_field_prices: bool = False
    shop_coordinates: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    selected_countries: List[str] = field(default_factory=list)


@dataclass
class MotorSpec:
    """Спецификация двигателя"""
    hp: float = 0.0
    max_speed: float = 0.0
    torque: float = 0.0
    price_delta: int = 0


@dataclass
class ItemSpec:
    """Универсальная спецификация для техники, зданий, полей и т.д."""
    mod_name: str
    xml_rel_path: str
    item_type: str = "vehicle"   # vehicle | placeable | field
    title: str = "Unknown"
    brand: str = "GENERIC"
    category: str = "misc"
    country: str = "Россия"
    country_flag: str = "🇷🇺"
    is_retro: bool = False
    old_price: int = 0
    new_price: int = 0
    new_price_rub: int = 0
    hp: float = 0.0
    max_speed: float = 0.0
    capacity: float = 0.0
    working_width: float = 0.0
    needed_hp: float = 0.0
    configs_updated: int = 0
    needs_review: bool = False
    brand_mult: float = 1.0
    ai_reason: str = "Словари"
    slots: int = 0
    production_cost: float = 0.0
    size_label: str = ""
    motors: List[MotorSpec] = field(default_factory=list)
    field_area: float = 0.0
    field_distance: float = 0.0

    @property
    def unique_key(self) -> str:
        return f"{self.mod_name}::{self.xml_rel_path}"

    @property
    def type_icon(self) -> str:
        icons = {"vehicle": "🚜", "placeable": "🏗️", "field": "🌾"}
        return icons.get(self.item_type, "📦")

    @property
    def specs_str(self) -> str:
        parts = []
        if self.item_type == "vehicle":
            if self.hp > 0:
                parts.append(f"{int(self.hp)} л.с.")
            if self.capacity > 0:
                parts.append(f"{int(self.capacity)} л")
            if self.max_speed > 0:
                parts.append(f"{int(self.max_speed)} км/ч")
            if self.working_width > 0:
                parts.append(f"{self.working_width:g} м")
            if self.is_retro:
                parts.append("🕰️ Ретро")
        elif self.item_type == "field":
            if self.field_area > 0:
                parts.append(f"{self.field_area:g} га")
            if self.field_distance > 0:
                parts.append(f"{self.field_distance:g} км до магазина")
        else:
            if self.slots > 0:
                parts.append(f"{self.slots} слотов")
            if self.capacity > 0:
                parts.append(f"{int(self.capacity)} л")
            if self.production_cost > 0:
                parts.append(f"Произв.: {int(self.production_cost)}")
            if self.size_label:
                parts.append(self.size_label)
        return " | ".join(parts) if parts else "—"


# ==============================================================================
# 6. УТИЛИТЫ
# ==============================================================================

def clean_round(val: float) -> int:
    val = max(50.0, float(val))
    if val < 500:       return int(round(val / 10) * 10)
    if val < 2500:      return int(round(val / 50) * 50)
    if val < 15000:     return int(round(val / 100) * 100)
    if val < 100000:    return int(round(val / 500) * 500)
    if val < 1000000:   return int(round(val / 1000) * 1000)
    return int(round(val / 5000) * 5000)


def pf(val: Optional[str], default: float = 0.0) -> float:
    if not val:
        return default
    try:
        m = re.search(r"[-+]?\d*\.?\d+", str(val).replace(",", "."))
        return float(m.group(0)) if m else default
    except Exception:
        return default


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


def calculate_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Расчёт расстояния между двумя точками (в км, упрощённо)"""
    dx = coord1[0] - coord2[0]
    dy = coord1[1] - coord2[1]
    return math.sqrt(dx * dx + dy * dy) / 1000.0



# ==============================================================================
# 7. УПРАВЛЕНИЕ ИИ (OLLAMA)
# ==============================================================================

def get_ollama_exe() -> Optional[str]:
    p = shutil.which("ollama")
    if not p:
        win = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if os.path.isfile(win):
            p = win
    return p


def check_ollama() -> Tuple[bool, List[str]]:
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as r:
            if r.status == 200:
                data = json.loads(r.read().decode("utf-8"))
                return True, [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return False, []


def start_ollama(cb) -> bool:
    ok, _ = check_ollama()
    if ok:
        return True
    exe = get_ollama_exe()
    if not exe:
        cb("Ollama не найдена.")
        return False
    try:
        env = os.environ.copy()
        env["OLLAMA_NUM_PARALLEL"] = "2"
        kw = {"env": env}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen([exe, "serve"], **kw)
        for _ in range(15):
            ok, _ = check_ollama()
            if ok:
                return True
            time.sleep(1.0)
    except Exception:
        pass
    return False


def stop_ollama(cb):
    try:
        if os.name == "nt":
            for p in ("ollama.exe", "ollama_llama_server.exe"):
                subprocess.run(["taskkill", "/f", "/im", p],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.run(["pkill", "ollama"], capture_output=True)
        cb("Служба ИИ остановлена.")
    except Exception:
        pass


def download_model(name: str, prog_cb, done_cb):
    exe = get_ollama_exe()
    if not exe:
        done_cb("Сначала скачайте Ollama!")
        return
    if not start_ollama(prog_cb):
        done_cb("Не удалось запустить Ollama.")
        return
    try:
        kw = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
              "text": True, "encoding": "utf-8", "errors": "ignore"}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen([exe, "pull", name], **kw)
        for line in proc.stdout:
            s = line.strip()
            if s:
                prog_cb(f"⬇ [{name}]: {s}")
        rc = proc.wait()
        done_cb(f"✅ Модель '{name}' загружена!" if rc == 0 else f"Ошибка: код {rc}")
    except Exception as e:
        done_cb(f"Ошибка: {e}")


def delete_model(name: str, cb, done_cb):
    exe = get_ollama_exe()
    if not exe:
        done_cb("Ollama не найдена.")
        return
    try:
        kw = {"check": True}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run([exe, "rm", name], **kw)
        done_cb(f"Модель '{name}' удалена.")
    except Exception as e:
        done_cb(f"Ошибка: {e}")


def install_ollama_app(status_cb, done_cb):
    url = "https://ollama.com/download/OllamaSetup.exe"
    status_cb("Скачивание Ollama...")
    try:
        tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        urllib.request.urlretrieve(url, tmp)
        subprocess.Popen([tmp], shell=True)
        done_cb("Инсталлятор Ollama запущен. Завершите установку.")
    except Exception as e:
        done_cb(f"Ошибка скачивания: {e}")


AI_BRAND_CACHE: Dict[str, str] = {}


def ask_ai_classification(brand: str, title: str, filename: str, mod_name: str,
                          model: str, countries: List[str]) -> Tuple[Optional[str], bool, str]:
    """Запрос к ИИ для определения страны и ретро-статуса"""
    key = f"{model}_{brand}_{title}_{filename}_{mod_name}".lower()
    if key in AI_BRAND_CACHE:
        cached = AI_BRAND_CACHE[key]
        parts = cached.split("|")
        country = parts[0] if parts else None
        is_retro = len(parts) > 1 and "RETRO" in parts[1].upper()
        return country, is_retro, "Из кэша ИИ"

    ok, models = check_ollama()
    if not ok:
        return None, False, "Служба не запущена"
    if not any(model in m for m in models):
        return None, False, f"Модель {model} не найдена"

    countries_str = ", ".join(countries) if countries else "Любая страна"
    prompt_tpl = PRO_DATA.get("custom_prompt", DEFAULT_AI_PROMPT)
    prompt = prompt_tpl.format(
        mod_name=mod_name, filename=filename, brand=brand, 
        title=title, countries=countries_str)

    data = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 30}
    }).encode("utf-8")

    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            ans = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
            parts = ans.split("|")
            country = parts[0].strip() if parts else None
            is_retro = len(parts) > 1 and "RETRO" in parts[1].upper()
            
            if country and country in ALL_COUNTRIES:
                AI_BRAND_CACHE[key] = f"{country}|{'RETRO' if is_retro else 'MODERN'}"
                return country, is_retro, "ИИ-классификация"
            return None, False, f"Ответ ИИ: {ans[:50]}"
    except Exception as e:
        return None, False, str(e)[:60]



# ==============================================================================
# 8. БАЗЫ ДАННЫХ ЗДАНИЙ И ПОЛЕЙ
# ==============================================================================

PLACEABLE_CATEGORIES = {
    "silos":           {"label": "Силос / Хранилище",     "base": 18000,  "mult": 1.0},
    "storages":        {"label": "Склад",                  "base": 12000,  "mult": 0.9},
    "liquidstorages":  {"label": "Ёмкость для жидкостей",  "base": 8000,   "mult": 0.8},
    "productions":        {"label": "Производство",        "base": 45000,  "mult": 1.3},
    "productionpoints":   {"label": "Производственная точка", "base": 35000, "mult": 1.2},
    "animalpens":      {"label": "Загон для животных",     "base": 28000,  "mult": 1.1},
    "animals":         {"label": "Животноводство",         "base": 22000,  "mult": 1.0},
    "farmhouses":      {"label": "Фермерский дом",         "base": 55000,  "mult": 1.2},
    "sheds":           {"label": "Ангар / Навес",          "base": 15000,  "mult": 0.85},
    "buildings":       {"label": "Строение",               "base": 20000,  "mult": 1.0},
    "decorations":     {"label": "Декорации",              "base": 800,    "mult": 0.5},
    "fences":          {"label": "Ограждения",             "base": 400,    "mult": 0.3},
    "lights":          {"label": "Освещение",              "base": 500,    "mult": 0.4},
    "sellingpoints":   {"label": "Точка продажи",          "base": 30000,  "mult": 1.0},
    "greenhouses":     {"label": "Теплица",                "base": 18000,  "mult": 0.95},
    "beehives":        {"label": "Пасека / Ульи",          "base": 5000,   "mult": 0.6},
    "placeables":      {"label": "Размещаемый объект",     "base": 10000,  "mult": 0.8},
    "misc":            {"label": "Прочее",                 "base": 5000,   "mult": 0.7},
}

PLACEABLE_SIZE_KEYWORDS = {
    "small": 0.6, "medium": 1.0, "large": 1.6, "xl": 2.2, "xxl": 3.0,
    "big": 1.5, "huge": 2.5, "tiny": 0.4, "mega": 3.5,
}

FUEL_FILL_TYPES = {
    "diesel", "def", "adblue", "electriccharge", "methane", "air",
    "oil", "coolant", "unknown"
}

VEHICLE_IGNORED_CATS = {
    "placeables", "farmhouses", "sheds", "silos", "productions",
    "animals", "greenhouses", "tools_placeables", "decorations", "lights",
    "storages", "sellingpoints", "pallets", "fences", "buildings",
    "productionpoints", "beehives", "animalpens"
}

VEHICLE_IGNORED_FN = {
    "storage", "trigger", "fence", "gate", "building", "placeable",
    "house", "silo", "tank", "water", "sell", "buy", "pallet", "bag",
    "bale", "object", "decor", "light", "sign", "generator", "workshop",
    "construction", "foundation", "greenhouse", "stable", "shed",
    "production", "bee", "hive", "animal", "pen"
}


# ==============================================================================
# 9. ДЕТЕКЦИЯ СТРАНЫ И РЕТРО-СТАТУСА
# ==============================================================================

def detect_country_and_retro(brand: str, title: str, filename: str, mod_name: str,
                                cfg: BalancerConfig) -> Tuple[str, str, float, bool, bool, str]:
    """Возвращает: (country, flag, multiplier, is_retro, needs_review, reason)"""
    cb = brand.strip().lower()
    selected = cfg.selected_countries or SELECTED_COUNTRIES

    # 1. Память (обученные бренды)
    if cb in LEARNED_BRANDS and cb not in ("lizard", "none", "generic", ""):
        cached = LEARNED_BRANDS[cb]
        parts = cached.split("|") if "|" in cached else [cached, "MODERN"]
        country = parts[0]
        is_retro = len(parts) > 1 and "RETRO" in parts[1].upper()
        if country in ALL_COUNTRIES:
            info = ALL_COUNTRIES[country]
            mult = cfg.country_multipliers.get(country, info["k"])
            return country, info["flag"], mult, is_retro, False, "Память"

    combined = f"{brand} {title} {filename} {mod_name}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", combined))

    # 2. Проверка по брендам из PRO_DATA
    country_brands = PRO_DATA.get("country_brands", {})
    for country, brands_list in country_brands.items():
        if country not in selected:
            continue
        brand_set = set(b.lower() for b in brands_list)
        if tokens & brand_set or any(b in combined for b in brands_list):
            info = ALL_COUNTRIES.get(country, {"flag": "🏳", "k": 1.0})
            mult = cfg.country_multipliers.get(country, info["k"])
            # Проверка на ретро
            is_retro = _check_retro_keywords(combined)
            return country, info["flag"], mult, is_retro, False, f"Бренд ({country})"

    # 3. ИИ-классификация
    if cfg.use_local_ai:
        country, is_retro, reason = ask_ai_classification(
            brand, title, filename, mod_name, cfg.ai_model_name, selected)
        if country and country in selected:
            info = ALL_COUNTRIES.get(country, {"flag": "🏳", "k": 1.0})
            mult = cfg.country_multipliers.get(country, info["k"])
            return country, info["flag"], mult, is_retro, False, reason
        return "⚠️ Проверить", "❓", 1.0, False, True, f"ИИ: {reason}"

    # 4. По умолчанию — первая выбранная страна
    if selected:
        country = selected[0]
        info = ALL_COUNTRIES.get(country, {"flag": "🏳", "k": 1.0})
        mult = cfg.country_multipliers.get(country, info["k"])
        return country, info["flag"], mult, False, True, "По умолчанию"

    return "Неизвестно", "❓", 1.0, False, True, "Нет стран"


def _check_retro_keywords(text: str) -> bool:
    """Проверка текста на ключевые слова ретро-техники"""
    retro_kw = [
        "zil-130", "zil130", "zil-131", "gaz-52", "gaz-53", "gaz-66", "gaz66",
        "gaz-69", "uaz-469", "uaz469", "uaz-452", "mtz-50", "mtz50",
        "mtz-80", "dt-75", "dt75", "t-40", "t40", "t-25", "t25", "t-16", "t16",
        "t-150", "k-700", "k700", "sk-5", "sk5", "don-1500", "don1500",
        "kraz-255", "maz-500", "kamaz-5320", "retro", "vintage", "classic",
        "old", "советск", "старый"
    ]
    return any(kw in text for kw in retro_kw)
# TEST_MARKER_123
