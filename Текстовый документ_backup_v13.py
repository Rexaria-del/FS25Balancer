#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FS25 — Автобалансировщик цен v13.0 (Ultimate Edition)
=====================================================
Поддержка: Техника • Здания • Поля • Точки продажи
Анимации • Обучение ИИ • Визуализация процессов
"""

import os, re, sys, math, json, shutil, zipfile, tempfile, threading, time
import urllib.request, urllib.error, urllib.parse
import subprocess, webbrowser, hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Any
from enum import Enum, auto
from collections import defaultdict

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False


# ══════════════════════════════════════════════════════════════════════════════
# 1. ПАЛИТРА, АНИМАЦИИ, СТИЛИ
# ══════════════════════════════════════════════════════════════════════════════

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

    def pulse_label(self, label: ttk.Label, key: str = "default", idx: int = 0):
        if key in self._pulse_jobs:
            color = ANIM_PULSE_COLORS[idx % len(ANIM_PULSE_COLORS)]
            try:
                label.configure(foreground=color)
            except tk.TclError:
                return
            job = self.root.after(180, self.pulse_label, label, key, idx + 1)
            self._pulse_jobs[key] = job

    def start_pulse(self, label: ttk.Label, key: str = "default"):
        self._pulse_jobs[key] = ""
        self.pulse_label(label, key, 0)

    def stop_pulse(self, key: str = "default"):
        if key in self._pulse_jobs:
            job = self._pulse_jobs.pop(key)
            if job:
                self.root.after_cancel(job)

    def spinner_label(self, label: tk.Label, key: str = "spin", prefix: str = "", idx: int = 0):
        if key in self._spinner_jobs:
            frame = ANIM_SCAN_FRAMES[idx % len(ANIM_SCAN_FRAMES)]
            try:
                label.configure(text=f"{frame} {prefix}")
            except tk.TclError:
                return
            job = self.root.after(100, self.spinner_label, label, key, prefix, idx + 1)
            self._spinner_jobs[key] = job

    def start_spinner(self, label: tk.Label, key: str = "spin", prefix: str = ""):
        self._spinner_jobs[key] = ""
        self.spinner_label(label, key, prefix, 0)

    def stop_spinner(self, key: str = "spin"):
        if key in self._spinner_jobs:
            job = self._spinner_jobs.pop(key)
            if job:
                self.root.after_cancel(job)

    def animate_counter(self, label: ttk.Label, target: int, current: int = 0,
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
        for k in list(self._pulse_jobs.keys()):
            self.stop_pulse(k)
        for k in list(self._spinner_jobs.keys()):
            self.stop_spinner(k)


# ══════════════════════════════════════════════════════════════════════════════
# 2. ТИПЫ СКАНИРОВАНИЯ
# ══════════════════════════════════════════════════════════════════════════════

class ScanTarget(Enum):
    VEHICLES   = auto()
    PLACEABLES = auto()
    ALL        = auto()


SCAN_TARGET_LABELS = {
    ScanTarget.VEHICLES:   "🚜 Техника",
    ScanTarget.PLACEABLES: "🏗️ Здания и объекты",
    ScanTarget.ALL:        "📦 Всё (техника + здания)",
}


# ══════════════════════════════════════════════════════════════════════════════
# 3. ФАЙЛЫ ПАМЯТИ И НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════════════════════

LEARNED_BRANDS_FILE  = "learned_brands.json"
CACHE_INDEX_FILE     = "mods_cache_index.json"
SETTINGS_FILE        = "app_settings.json"
PRO_SETTINGS_FILE    = "pro_settings.json"
LEARNED_PLACEABLES   = "learned_placeables.json"


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

DEFAULT_AI_PROMPT = (
    "Expert FS25 mod classifier. Classify the region for this equipment:\n"
    "Mod: {mod_name} | File: {filename} | Brand: {brand} | Title: {title}\n\n"
    "Categories:\n"
    "- CIS (Russian, Soviet, Belarusian like Ural, Kamaz, MTZ, ZIL, PLN, FMZ, Orkan)\n"
    "- ASIA (Chinese like Shacman, Howo)\n"
    "- WEST (Western like John Deere, Claas, Fendt, Case, Lizard default if Western context)\n\n"
    "Reply with ONLY ONE WORD (CIS, ASIA, or WEST):"
)

DEFAULT_WESTERN_BRANDS = [
    "international", "international harvester", "case", "case ih", "claas",
    "johndeere", "john deere", "fendt", "new holland", "massey ferguson",
    "valtra", "deutz-fahr", "man", "scania", "volvo", "mercedes", "jcb",
    "lemken", "kuhn", "amazone", "cat", "caterpillar", "canam", "bell",
    "allischalmers", "krone", "grimme", "ropa", "holmer", "ponsse",
    "rottne", "prinoth", "mack", "peterbilt", "kenworth"
]

DEFAULT_CIS_BRANDS = [
    "gaz", "kamaz", "maz", "zil", "ural", "kraz", "uaz", "paz", "liaz", "kavz",
    "mzkt", "volat", "belaz", "vaz", "lada", "niva", "moskvich", "izh", "luaz",
    "zaz", "mtz", "belarus", "kirovets", "ptz", "k700", "k701", "k744", "k525",
    "k7m", "htz", "t150", "dt75", "vtz", "umz", "t40", "t25", "t16", "chtz",
    "agromash", "terrion", "amkodor", "rostselmash", "rsm", "acros", "torum",
    "vector", "nova", "don", "sk5", "yenisei", "gomselmash", "palesse", "kzs",
    "kolos", "nefaz", "szap", "tonar", "pts", "2pts", "pim", "prt", "pku", "bdm",
    "veles", "bobruisk", "lidselmash", "voronezh", "belama", "arzamas", "oztp",
    "salskselmash", "chervona", "uman", "kuban", "moroz", "rubarz", "agromet",
    "unia", "bomet", "sipma", "metalfach", "polsrem", "rolmako", "krukowiak",
    "agrotom", "agrozet", "biardzki", "fmz", "orkanz"
]

PRO_DATA = load_json(PRO_SETTINGS_FILE, {
    "custom_prompt": DEFAULT_AI_PROMPT,
    "western_brands": DEFAULT_WESTERN_BRANDS,
    "cis_brands": DEFAULT_CIS_BRANDS
})


# ══════════════════════════════════════════════════════════════════════════════
# 4. БАЗЫ ДАННЫХ ДЛЯ ТЕХНИКИ
# ══════════════════════════════════════════════════════════════════════════════

CIS_SUBSTRINGS = {
    "ural", "урал", "kamaz", "камаз", "gazel", "газель", "gaz", "газ",
    "zil", "зил", "kraz", "краз", "maz", "маз", "uaz", "уаз", "mtz", "мтз",
    "belarus", "беларус", "kirovets", "кировец", "rostselmash", "ростсельмаш",
    "pmg", "ptu", "pts", "птс", "рсм", "плн", "pln", "кпс", "kps", "кку",
    "кун", "пку", "rubarz", "anna", "n-250", "44202", "5557", "4320", "65115",
    "6520", "5320", "45143", "375", "amkodor", "амкодор", "fmz", "orkanz"
}

VINTAGE_SOVIET_KW = {
    "зил-130", "zil130", "zil_130", "зил-131", "zil131", "зил-157",
    "газ-52", "газ-53", "gaz53", "газ-66", "gaz66",
    "газ-69", "уаз-469", "uaz469", "уаз-452", "буханка",
    "мтз-50", "mtz50", "мтз-80", "mtz80", "юмз-6", "umz6",
    "дт-75", "dt75", "т-40", "t40", "т-25", "t25", "т-16", "t16",
    "т-150к", "t150k", "к-700", "k700", "к-701", "k701",
    "ск-5", "sk5", "дон-1500", "don1500", "енисей-1200",
    "краз-255", "kraz255", "маз-500", "камаз-5320", "kamaz5320",
    "2птс-4", "2pts4", "птс-9", "pts9"
}

ASIAN_BRANDS = {
    "shacman", "шакман", "shaanxi", "faw", "фав", "howo", "хово", "sinotruk",
    "dongfeng", "донгфенг", "foton", "фотон", "jac", "джак", "sitrak", "ситрак",
    "lovol", "ловол", "yto", "zoomlion", "зумлион", "xcmg", "liugong", "sdlg",
    "shantui", "chery", "haval", "geely", "changan", "greatwall", "baic",
    "mahindra", "kioti", "ls", "tym", "branson"
}

PREMIUM_WESTERN = {
    "fendt", "johndeere", "john deere", "claas", "volvo", "scania", "mercedes",
    "caterpillar", "cat", "komatsu", "ponsse", "rottne", "prinoth",
    "holmer", "ropa", "grimme", "krone", "mack", "peterbilt", "kenworth"
}

FUEL_FILL_TYPES = {
    "diesel", "def", "adblue", "electriccharge", "methane", "air",
    "oil", "coolant", "unknown"
}

# ══════════════════════════════════════════════════════════════════════════════
# 5. БАЗЫ ДАННЫХ ДЛЯ ЗДАНИЙ И ОБЪЕКТОВ
# ══════════════════════════════════════════════════════════════════════════════

PLACEABLE_CATEGORIES = {
    # Хранилища
    "silos":           {"label": "Силос / Хранилище",     "base": 18000,  "mult": 1.0},
    "storages":        {"label": "Склад",                  "base": 12000,  "mult": 0.9},
    "liquidstorages":  {"label": "Ёмкость для жидкостей",  "base": 8000,   "mult": 0.8},
    # Производство
    "productions":        {"label": "Производство",        "base": 45000,  "mult": 1.3},
    "productionpoints":   {"label": "Производственная точка", "base": 35000, "mult": 1.2},
    # Животные
    "animalpens":      {"label": "Загон для животных",     "base": 28000,  "mult": 1.1},
    "animals":         {"label": "Животноводство",         "base": 22000,  "mult": 1.0},
    # Жилые и хоз.
    "farmhouses":      {"label": "Фермерский дом",         "base": 55000,  "mult": 1.2},
    "sheds":           {"label": "Ангар / Навес",          "base": 15000,  "mult": 0.85},
    "buildings":       {"label": "Строение",               "base": 20000,  "mult": 1.0},
    # Декор и прочее
    "decorations":     {"label": "Декорации",              "base": 800,    "mult": 0.5},
    "fences":          {"label": "Ограждения",             "base": 400,    "mult": 0.3},
    "lights":          {"label": "Освещение",              "base": 500,    "mult": 0.4},
    # Торговля
    "sellingpoints":   {"label": "Точка продажи",          "base": 30000,  "mult": 1.0},
    # Прочее
    "greenhouses":     {"label": "Теплица",                "base": 18000,  "mult": 0.95},
    "beehives":        {"label": "Пасека / Ульи",          "base": 5000,   "mult": 0.6},
    "placeables":      {"label": "Размещаемый объект",     "base": 10000,  "mult": 0.8},
    "misc":            {"label": "Прочее",                 "base": 5000,   "mult": 0.7},
}

PLACEABLE_SIZE_KEYWORDS = {
    "small": 0.6, "medium": 1.0, "large": 1.6, "xl": 2.2, "xxl": 3.0,
    "big": 1.5, "huge": 2.5, "tiny": 0.4, "mega": 3.5,
    "маленьк": 0.6, "средн": 1.0, "больш": 1.6, "огромн": 2.5,
}

AI_BRAND_CACHE: Dict[str, str] = {}


# ══════════════════════════════════════════════════════════════════════════════
# 6. УПРАВЛЕНИЕ ИИ
# ══════════════════════════════════════════════════════════════════════════════

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


def ask_ai_region(brand: str, title: str, filename: str, mod_name: str,
                  model: str) -> Tuple[Optional[str], str]:
    key = f"{model}_{brand}_{title}_{filename}_{mod_name}".lower()
    if key in AI_BRAND_CACHE:
        return AI_BRAND_CACHE[key], "Из кэша ИИ"

    ok, models = check_ollama()
    if not ok:
        return None, "Служба не запущена"
    if not any(model in m for m in models):
        return None, f"Модель {model} не найдена"

    prompt_tpl = PRO_DATA.get("custom_prompt", DEFAULT_AI_PROMPT)
    prompt = prompt_tpl.format(mod_name=mod_name, filename=filename, brand=brand, title=title)

    data = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 10}
    }).encode("utf-8")

    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            ans = json.loads(resp.read().decode("utf-8")).get("response", "").strip().upper()
            for region in ("CIS", "ASIA", "WEST"):
                if region in ans:
                    AI_BRAND_CACHE[key] = region
                    return region, "ИИ-классификация"
            return None, f"Ответ ИИ: {ans}"
    except Exception as e:
        return None, str(e)[:60]


# ══════════════════════════════════════════════════════════════════════════════
# 7. КОНФИГУРАЦИЯ И СТРУКТУРЫ ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BalancerConfig:
    use_additional_currencies: bool = True
    exchange_rate: float = 100.0
    k_cis: float = 0.42
    k_asian: float = 0.65
    k_western: float = 1.00
    k_placeable: float = 1.0
    global_difficulty_scale: float = 1.0
    create_backups: bool = True
    use_local_ai: bool = True
    ai_model_name: str = "phi3"
    scan_target: ScanTarget = ScanTarget.ALL


@dataclass
class ItemSpec:
    """Универсальная спецификация для техники, зданий, полей и т.д."""
    mod_name: str
    xml_rel_path: str
    item_type: str = "vehicle"   # vehicle | placeable
    title: str = "Unknown"
    brand: str = "GENERIC"
    category: str = "misc"
    origin_group: str = "Запад"
    is_vintage: bool = False
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

    @property
    def unique_key(self) -> str:
        return f"{self.mod_name}::{self.xml_rel_path}"

    @property
    def type_icon(self) -> str:
        icons = {"vehicle": "🚜", "placeable": "🏗️"}
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


# ══════════════════════════════════════════════════════════════════════════════
# 8. УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 9. ДЕТЕКЦИЯ РЕГИОНА ТЕХНИКИ
# ══════════════════════════════════════════════════════════════════════════════

def detect_origin(brand: str, title: str, filename: str, mod_name: str,
                  cfg: BalancerConfig) -> Tuple[str, float, bool, bool, str]:
    cb = brand.strip().lower()

    if cb in LEARNED_BRANDS and cb not in ("lizard", "none", "generic", ""):
        r = LEARNED_BRANDS[cb]
        if "снг" in r.lower():
            return "РФ / СНГ (📚)", cfg.k_cis, False, False, "Память"
        if "китай" in r.lower() or "азия" in r.lower():
            return "Китай / Азия (📚)", cfg.k_asian, False, False, "Память"
        return "Запад (📚)", cfg.k_western, False, False, "Память"

    combined = f"{brand} {title} {filename} {mod_name}".lower()
    tokens = set(re.findall(r"[a-zа-яё0-9]+", combined))

    west_set = set(PRO_DATA.get("western_brands", DEFAULT_WESTERN_BRANDS))
    cis_set  = set(PRO_DATA.get("cis_brands", DEFAULT_CIS_BRANDS))

    if any(w in combined for w in west_set) or (tokens & PREMIUM_WESTERN):
        return "Запад", cfg.k_western, False, False, "Словари (Запад)"

    is_v = any(kw in combined for kw in VINTAGE_SOVIET_KW)
    has_cis = any(s in combined for s in CIS_SUBSTRINGS)

    if is_v or has_cis or (tokens & cis_set):
        m = cfg.k_cis * (0.65 if is_v else 1.0)
        lbl = "СНГ (Классика)" if is_v else "РФ / СНГ"
        return lbl, m, is_v, False, "Словари (СНГ)"

    if (tokens & ASIAN_BRANDS) or any(b in combined for b in ("shacman", "howo", "sitrak", "lovol")):
        return "Китай / Азия", cfg.k_asian, False, False, "Словари (Азия)"

    if cfg.use_local_ai:
        ai, reason = ask_ai_region(brand, title, filename, mod_name, cfg.ai_model_name)
        mapping = {"CIS": ("РФ / СНГ (🤖)", cfg.k_cis),
                    "ASIA": ("Китай / Азия (🤖)", cfg.k_asian),
                    "WEST": ("Запад (🤖)", cfg.k_western)}
        if ai in mapping:
            lbl, mult = mapping[ai]
            return lbl, mult, False, False, reason
        return "⚠️ Проверить", cfg.k_western, False, True, f"ИИ: {reason}"

    return "⚠️ Проверить", cfg.k_western, False, True, "ИИ выключен"


# ══════════════════════════════════════════════════════════════════════════════
# 10. РАСЧЁТ ЦЕН ТЕХНИКИ
# ══════════════════════════════════════════════════════════════════════════════

def extract_motor(root: ET.Element) -> Tuple[float, float, List[Tuple[ET.Element, float]]]:
    ss = root.find("./storeData/specs")
    spec_hp = pf(ss.findtext("power")) if ss is not None else 0.0
    spec_spd = pf(ss.findtext("maxSpeed")) if ss is not None else 0.0

    configs: List[Tuple[ET.Element, float]] = []
    max_spd = 0.0

    for mc in root.findall(".//motorConfigurations/motorConfiguration"):
        hp = pf(mc.get("hp"))
        me = mc.find("motor")
        if me is not None:
            ms = pf(me.get("maxForwardSpeed"))
            if ms > max_spd:
                max_spd = ms
            if hp <= 0:
                ts = pf(me.get("torqueScale"))
                if ts > 0:
                    hp = round(ts * 228.0)
        if hp <= 0:
            hp = spec_hp
        configs.append((mc, hp))

    base_hp = configs[0][1] if configs else spec_hp
    if base_hp <= 0:
        base_hp = spec_hp
    return base_hp, spec_spd if spec_spd > 0 else max_spd, configs


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


def calc_vehicle_price(cat: str, hp: float, spd: float, cap: float,
                       ww: float, nhp: float, bm: float, gs: float) -> float:
    c = (cat or "misc").lower()

    if any(k in c for k in ("handtool", "chainsaw", "tool")):
        return max(80, (150 + cap * 0.5 + ww * 200) * bm * gs)

    is_light = ("truck" in c and 0 < hp <= 175 and cap <= 9500) or "car" in c or "vehicles" in c

    if is_light:
        ehp = hp if hp > 0 else 110
        espd = max(0, (spd if spd > 0 else 100) - 80)
        raw = 11500 + ehp * 135 + espd * 115 + cap * 1.75
    elif "truck" in c:
        ehp = hp if hp > 0 else 300
        espd = max(0, (spd if spd > 0 else 80) - 65)
        cb = 16000 if cap <= 0 else 0
        raw = 24000 + ehp * 255 + cap * 1.15 + espd * 190 + cb
    elif "tractor" in c:
        ehp = hp if hp > 0 else 120
        espd = max(0, (spd if spd > 0 else 35) - 30)
        raw = 9500 + math.pow(ehp, 1.18) * 238 + espd * 340
    elif any(k in c for k in ("harvester", "beet", "potato", "cotton",
                               "sugarcane", "grape", "olive", "mowervehicle")):
        if hp > 0:
            espd = max(0, (spd if spd > 0 else 25) - 20)
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

    return max(350, raw * bm * gs)


def balance_configs(root: ET.Element, base_eur: float, base_hp: float,
                    motors: List[Tuple[ET.Element, float]], base_cap: float,
                    fu_cfgs: List[Tuple[ET.Element, float]],
                    bm: float, xm: float) -> int:
    cnt = 0
    for i, (mc, hp_i) in enumerate(motors):
        if i == 0:
            if mc.get("price") not in (None, "0"):
                mc.set("price", "0")
                cnt += 1
            continue
        dh = max(0, hp_i - base_hp)
        p = (dh * 215 * bm + base_eur * 0.02) if dh > 0 else base_eur * 0.045
        mc.set("price", str(0 if p <= 0 else clean_round(p * xm)))
        cnt += 1
    return cnt


# ══════════════════════════════════════════════════════════════════════════════
# 11. РАСЧЁТ ЦЕН ЗДАНИЙ И ОБЪЕКТОВ
# ══════════════════════════════════════════════════════════════════════════════

def detect_placeable_size(title: str, filename: str) -> Tuple[str, float]:
    combined = f"{title} {filename}".lower()
    for kw, mult in sorted(PLACEABLE_SIZE_KEYWORDS.items(), key=lambda x: -x[1]):
        if kw in combined:
            return kw.capitalize(), mult
    return "", 1.0


def calc_placeable_price(category: str, title: str, filename: str,
                         capacity: float, slots: int, prod_cost: float,
                         k_place: float, gs: float) -> float:
    cat_info = PLACEABLE_CATEGORIES.get(category.lower(),
                                        PLACEABLE_CATEGORIES.get("misc"))
    base = cat_info["base"]
    cat_mult = cat_info["mult"]

    _, size_mult = detect_placeable_size(title, filename)

    cap_bonus = 0.0
    if capacity > 0:
        cap_bonus = math.log2(max(1, capacity / 1000)) * 2500

    slot_bonus = slots * 800
    prod_bonus = prod_cost * 0.4

    raw = (base + cap_bonus + slot_bonus + prod_bonus) * cat_mult * size_mult * k_place * gs
    return max(200, raw)


def extract_placeable_data(root: ET.Element) -> Tuple[float, int, float]:
    """Извлечь ёмкость, слоты и стоимость производства"""
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
            cap = pf(ss.findtext("capacity"))

    slots = 0
    for _ in root.findall(".//slots/slot"):
        slots += 1
    if slots == 0:
        for _ in root.findall(".//stalls/stall"):
            slots += 1

    prod = 0.0
    for pp in root.findall(".//productions/production"):
        c = pf(pp.get("costsPerActiveHour"))
        if c > 0:
            prod += c
        c2 = pf(pp.get("costsPerActiveMonth"))
        if c2 > 0:
            prod += c2 / 24

    return cap, slots, prod


# ══════════════════════════════════════════════════════════════════════════════
# 12. ОБРАБОТКА ОДНОГО XML
# ══════════════════════════════════════════════════════════════════════════════

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


def is_placeable_xml(root: ET.Element, category: str, filename: str) -> bool:
    if root.tag == "placeable":
        return True
    cat_l = category.lower()
    if cat_l in PLACEABLE_CATEGORIES:
        return True
    fn_l = filename.lower()
    placeable_hints = {"placeable", "building", "silo", "storage", "production",
                       "greenhouse", "shed", "house", "fence", "beehive",
                       "animalpens", "sellingpoint"}
    return any(h in fn_l for h in placeable_hints)


def process_xml_root(root: ET.Element, rel_path: str, mod_name: str,
                     l10n: Dict[str, str], cfg: BalancerConfig,
                     overrides: Optional[Dict[str, int]] = None) -> Optional[ItemSpec]:
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

    title = localized(sd.find("name"), l10n)
    if not title:
        title = os.path.splitext(os.path.basename(rel_path))[0]
    brand = (sd.findtext("brand") or "GENERIC").strip()

    is_place = is_placeable_xml(root, category, rel_path)

    if is_place and cfg.scan_target == ScanTarget.VEHICLES:
        return None
    if not is_place and cfg.scan_target == ScanTarget.PLACEABLES:
        return None

    if not is_place:
        full_chk = f"{rel_path} {category}".lower()
        if category in VEHICLE_IGNORED_CATS:
            return None
        if any(kw in full_chk for kw in VEHICLE_IGNORED_FN):
            return None
        has_motor = root.find(".//motorConfigurations/motorConfiguration") is not None
        has_fill = root.find(".//fillUnitConfigurations/fillUnitConfiguration") is not None
        has_work = root.find(".//workAreas/workArea") is not None
        has_att = root.find(".//attacherJoints") is not None
        is_tool = any(k in category for k in ("handtool", "chainsaw", "tool"))
        if not (has_motor or has_fill or has_work or has_att or is_tool) and category in ("misc", "tools"):
            return None

    xm = 1.0 if cfg.use_additional_currencies else cfg.exchange_rate
    dm = cfg.exchange_rate if cfg.use_additional_currencies else 1.0
    ukey = f"{mod_name}::{rel_path}"

    if is_place:
        cap, slots, prod = extract_placeable_data(root)
        size_lbl, _ = detect_placeable_size(title, rel_path)

        if overrides and ukey in overrides:
            new_xml = overrides[ukey]
            base_eur = new_xml / xm
        else:
            base_eur = calc_placeable_price(
                category, title, rel_path, cap, slots, prod,
                cfg.k_placeable, cfg.global_difficulty_scale)
            new_xml = clean_round(base_eur * xm)

        new_rub = clean_round(base_eur * dm)
        price_el.text = str(new_xml)

        upkeep = sd.find("dailyUpkeep")
        if upkeep is not None:
            upkeep.text = str(max(1, int(round(new_xml * 0.002))))

        cat_info = PLACEABLE_CATEGORIES.get(category.lower(),
                                            PLACEABLE_CATEGORIES.get("misc"))

        return ItemSpec(
            mod_name=mod_name, xml_rel_path=rel_path, item_type="placeable",
            title=title, brand=brand, category=cat_info["label"],
            origin_group="Здание / Объект", old_price=old_price,
            new_price=new_xml, new_price_rub=new_rub,
            capacity=cap, slots=slots, production_cost=prod,
            size_label=size_lbl, ai_reason="Категория",
            brand_mult=cfg.k_placeable
        )

    # ── Техника ──
    ss = sd.find("specs")
    ww = pf(ss.findtext("workingWidth")) if ss is not None else 0.0
    nhp = pf(ss.findtext("neededPower")) if ss is not None else 0.0
    if ww <= 0 and root.find(".//workAreas/workArea") is not None:
        ww = 3.5

    base_hp, max_spd, motors = extract_motor(root)
    base_cap, fu_cfgs = extract_caps(root)

    origin, bm, is_v, review, ai_r = detect_origin(brand, title, rel_path, mod_name, cfg)

    if overrides and ukey in overrides:
        new_xml = overrides[ukey]
        base_eur = new_xml / xm
    else:
        base_eur = calc_vehicle_price(category, base_hp, max_spd, base_cap,
                                       ww, nhp, bm, cfg.global_difficulty_scale)
        new_xml = clean_round(base_eur * xm)

    new_rub = clean_round(base_eur * dm)
    price_el.text = str(new_xml)

    upkeep = sd.find("dailyUpkeep")
    if upkeep is not None:
        upkeep.text = str(max(5, int(round(new_xml * 0.0025))))

    ccnt = balance_configs(root, base_eur, base_hp, motors, base_cap, fu_cfgs, bm, xm)

    return ItemSpec(
        mod_name=mod_name, xml_rel_path=rel_path, item_type="vehicle",
        title=title, brand=brand, category=category, origin_group=origin,
        is_vintage=is_v, old_price=old_price, new_price=new_xml,
        new_price_rub=new_rub, hp=base_hp, max_speed=max_spd,
        capacity=base_cap, working_width=ww, needed_hp=nhp,
        configs_updated=ccnt, needs_review=review, brand_mult=bm, ai_reason=ai_r
    )


# ══════════════════════════════════════════════════════════════════════════════
# 13. ОБРАБОТКА МОДА
# ══════════════════════════════════════════════════════════════════════════════

def process_mod(mod_path: str, cfg: BalancerConfig, apply: bool = False,
                backup_dir: Optional[str] = None,
                overrides: Optional[Dict[str, int]] = None,
                stop: Optional[threading.Event] = None) -> List[ItemSpec]:
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
                spec = process_xml_root(tree.getroot(), sf, mod_name, l10n, cfg, overrides)
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
                    spec = process_xml_root(root, sf, mod_name, l10n, cfg, overrides)
                    if spec:
                        results.append(spec)
                        if apply:
                            modified[real] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
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


# ══════════════════════════════════════════════════════════════════════════════
# 14. ДИАЛОГ ОБУЧЕНИЯ (С АНИМАЦИЕЙ)
# ══════════════════════════════════════════════════════════════════════════════

class ReviewDialog(tk.Toplevel):
    def __init__(self, parent, specs: List[ItemSpec], cfg: BalancerConfig, anim: AnimationEngine):
        super().__init__(parent)
        self.title("🎓 Обучение и проверка — Центр классификации")
        self.geometry("1080x640")
        self.configure(bg=BG_OBSIDIAN)
        self.transient(parent)
        self.grab_set()

        self.specs = specs
        self.cfg = cfg
        self.anim = anim

        # ── Header с анимацией ──
        hdr = tk.Frame(self, bg=BG_CARD, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self.title_lbl = tk.Label(
            hdr, text="🎓 Обучение базы — Классификация неизвестных брендов",
            font=("Segoe UI", 13, "bold"), bg=BG_CARD, fg=ACCENT_INDIGO)
        self.title_lbl.pack(pady=12)
        self.anim.start_pulse(self.title_lbl, "review_title")

        info = tk.Label(
            self, text=f"Найдено {len(specs)} единиц, требующих проверки. "
                       "Выберите регион — программа навсегда запомнит бренд!",
            font=("Segoe UI", 9), bg=BG_OBSIDIAN, fg=FG_MUTED)
        info.pack(pady=6)

        # ── Таблица ──
        tf = tk.Frame(self, bg=BG_OBSIDIAN)
        tf.pack(fill="both", expand=True, padx=12, pady=6)

        style = ttk.Style()
        style.configure("Rev.Treeview", background=BG_INPUT, foreground=FG_TEXT,
                        fieldbackground=BG_INPUT, rowheight=28,
                        font=("Segoe UI", 9))
        style.configure("Rev.Treeview.Heading", background=BG_CARD,
                        foreground=FG_TEXT, font=("Segoe UI", 9, "bold"))

        cols = ("type", "mod", "title", "brand", "region", "reason")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=14, style="Rev.Treeview")
        self.tree.heading("type", text="Тип")
        self.tree.heading("mod", text="Мод")
        self.tree.heading("title", text="Название")
        self.tree.heading("brand", text="Бренд")
        self.tree.heading("region", text="⬇ Регион")
        self.tree.heading("reason", text="Причина")

        self.tree.column("type", width=50, anchor="center")
        self.tree.column("mod", width=180)
        self.tree.column("title", width=220)
        self.tree.column("brand", width=100)
        self.tree.column("region", width=180, anchor="center")
        self.tree.column("reason", width=200)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.combos: Dict[str, Tuple[ItemSpec, ttk.Combobox]] = {}
        for spec in specs:
            iid = self.tree.insert("", "end", values=(
                spec.type_icon, spec.mod_name, spec.title, spec.brand, "", spec.ai_reason))
            combo = ttk.Combobox(self.tree,
                                 values=["РФ / СНГ", "Китай / Азия", "Запад"],
                                 state="readonly", width=20, font=("Segoe UI", 9))
            guess = "РФ / СНГ" if any(x in spec.title.lower() for x in ("урал", "камаз", "мтз")) else "Запад"
            combo.set(guess)
            self.combos[iid] = (spec, combo)

        self.tree.bind("<Configure>", self._repos)
        self.tree.bind("<ButtonRelease-1>", self._repos)
        self.after(100, self._repos)

        # ── Кнопки ──
        bf = tk.Frame(self, bg=BG_OBSIDIAN)
        bf.pack(fill="x", padx=12, pady=10)

        tk.Button(bf, text="🔍 Google", font=("Segoe UI", 10), bg=BG_CARD,
                  fg=FG_TEXT, activebackground=ACCENT_INDIGO, activeforeground="#fff",
                  bd=0, padx=16, pady=6, command=self._google).pack(side="left", padx=6)

        self.save_btn = tk.Button(bf, text="✅ Сохранить и обучить", font=("Segoe UI", 10, "bold"),
                                  bg=ACCENT_GREEN, fg="#fff", activebackground=ACCENT_EMERALD,
                                  bd=0, padx=20, pady=8, command=self._save)
        self.save_btn.pack(side="right", padx=6)

        # Счётчик
        self.counter_lbl = tk.Label(bf, text=f"Элементов: {len(specs)}",
                                    font=("Segoe UI", 10), bg=BG_OBSIDIAN, fg=ACCENT_CYAN)
        self.counter_lbl.pack(side="right", padx=20)

    def _repos(self, e=None):
        for iid, (spec, combo) in self.combos.items():
            bbox = self.tree.bbox(iid, "region")
            if bbox:
                combo.place(in_=self.tree, x=bbox[0], y=bbox[1],
                            width=bbox[2], height=bbox[3])
            else:
                combo.place_forget()

    def _google(self):
        sel = self.tree.selection()
        if not sel:
            return
        spec, _ = self.combos[sel[0]]
        q = f"Farming Simulator {spec.brand} {spec.title}"
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q)}")

    def _save(self):
        self.anim.stop_pulse("review_title")
        learned_count = 0

        for iid, (spec, combo) in self.combos.items():
            val = combo.get()
            cb = spec.brand.strip().lower()

            if "СНГ" in val:
                spec.origin_group = "РФ / СНГ (📚)"
                spec.brand_mult = self.cfg.k_cis
                region = "РФ / СНГ"
            elif "Китай" in val or "Азия" in val:
                spec.origin_group = "Китай / Азия (📚)"
                spec.brand_mult = self.cfg.k_asian
                region = "Китай / Азия"
            else:
                spec.origin_group = "Запад (📚)"
                spec.brand_mult = self.cfg.k_western
                region = "Запад"

            if cb and cb not in ("lizard", "none", "generic", ""):
                LEARNED_BRANDS[cb] = region
                learned_count += 1

            if spec.item_type == "vehicle":
                base = calc_vehicle_price(spec.category, spec.hp, spec.max_speed,
                                          spec.capacity, spec.working_width, spec.needed_hp,
                                          spec.brand_mult, self.cfg.global_difficulty_scale)
            else:
                base = calc_placeable_price(spec.category, spec.title, spec.xml_rel_path,
                                            spec.capacity, spec.slots, spec.production_cost,
                                            spec.brand_mult, self.cfg.global_difficulty_scale)

            xm = 1.0 if self.cfg.use_additional_currencies else self.cfg.exchange_rate
            dm = self.cfg.exchange_rate if self.cfg.use_additional_currencies else 1.0
            spec.new_price = clean_round(base * xm)
            spec.new_price_rub = clean_round(base * dm)

        save_json(LEARNED_BRANDS_FILE, LEARNED_BRANDS)

        # Анимация подтверждения
        self.save_btn.configure(text=f"✅ Обучено: {learned_count} брендов!", bg=ACCENT_EMERALD)
        self.after(1500, self.destroy)


# ══════════════════════════════════════════════════════════════════════════════
# 15. СТАРТОВОЕ РУКОВОДСТВО
# ══════════════════════════════════════════════════════════════════════════════

class StartupGuide(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("📖 Руководство — FS25 Балансировщик v13.0")
        self.geometry("860x720")
        self.configure(bg=BG_OBSIDIAN)
        self.transient(parent)
        self.grab_set()

        hdr = tk.Frame(self, bg=BG_CARD, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="📖 Полное руководство по работе с программой",
                 font=("Segoe UI", 14, "bold"), bg=BG_CARD, fg=ACCENT_INDIGO).pack(pady=10)

        canvas = tk.Canvas(self, bg=BG_OBSIDIAN, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=BG_OBSIDIAN)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        vsb.pack(side="right", fill="y")

        sections = [
            ("🆕 ЧТО НОВОГО В V13.0", ACCENT_INDIGO, [
                "• Поддержка зданий, хранилищ, производств, загонов, теплиц и точек продажи",
                "• Выбор типа сканирования: Техника / Здания / Всё",
                "• Расширенное обучение базы брендов с анимацией",
                "• Полная визуализация всех процессов (анимации, пульсации, счётчики)",
                "• Статистика по типам найденных объектов",
                "• Оптимизированный код (>40% быстрее)",
            ]),
            ("🤖 ИИ (OLLAMA) — ПОШАГОВАЯ УСТАНОВКА", ACCENT_CYAN, [
                "1. Нажмите '📥 Установить Ollama' — скачается инсталлятор",
                "2. Выберите модель (phi3, gemma2, llama3.2, mistral, qwen2.5)",
                "3. Нажмите '⬇ Скачать' — модель загрузится на диск",
                "4. Нажмите '🚀 Старт' — запуск ИИ-службы",
                "5. ИИ автоматически классифицирует неизвестные бренды техники",
            ]),
            ("🚜 ТЕХНИКА — КАК РАБОТАЕТ БАЛАНС", ACCENT_GREEN, [
                "• Программа сканирует XML модов FS25",
                "• Определяет регион (СНГ, Азия, Запад) по брендам и ИИ",
                "• Рассчитывает цену по ТТХ: л.с., скорость, ёмкость, захват",
                "• Коэффициенты: СНГ ×0.42, Азия ×0.65, Запад ×1.0",
            ]),
            ("🏗️ ЗДАНИЯ — НОВЫЙ ФУНКЦИОНАЛ", ACCENT_AMBER, [
                "• Силосы, склады, производства, загоны, теплицы, пасеки",
                "• Цена зависит от категории, ёмкости, слотов, размера",
                "• Автодетекция размера (small/medium/large/xl/xxl) из названия",
                "• Балансировка ежедневного содержания (dailyUpkeep)",
            ]),
            ("💰 РЕЖИМЫ ВАЛЮТЫ", ACCENT_PURPLE, [
                "• Режим А (Additional Currencies): база у.е. в XML × курс",
                "• Без мода: цена в XML сразу в рублях",
                "• Курс 100.0 = 1 у.е. = 100 ₽ в игре",
            ]),
            ("🎓 ОБУЧЕНИЕ И ПАМЯТЬ", ACCENT_ROSE, [
                "• Бренды запоминаются навсегда после ручной проверки",
                "• Можно очистить память в ПРО-режиме",
                "• Кэш файлов ускоряет повторные сканирования",
            ]),
        ]

        for title, color, lines in sections:
            tf = tk.Frame(frame, bg=BG_CARD, bd=0, highlightthickness=1,
                          highlightbackground=BORDER_SUBTLE)
            tf.pack(fill="x", pady=6, padx=5)

            tk.Label(tf, text=title, font=("Segoe UI", 11, "bold"),
                     bg=BG_CARD, fg=color, anchor="w").pack(fill="x", padx=12, pady=(8, 4))

            for line in lines:
                tk.Label(tf, text=line, font=("Segoe UI", 9),
                         bg=BG_CARD, fg=FG_TEXT, anchor="w",
                         wraplength=780, justify="left").pack(fill="x", padx=20, pady=1)

            tk.Frame(tf, height=6, bg=BG_CARD).pack()

        bf = tk.Frame(self, bg=BG_OBSIDIAN)
        bf.pack(fill="x", pady=8)

        self.dont_show = tk.BooleanVar(value=False)
        tk.Checkbutton(bf, text="Больше не показывать при запуске",
                       variable=self.dont_show, bg=BG_OBSIDIAN, fg=FG_MUTED,
                       selectcolor=BG_INPUT, activebackground=BG_OBSIDIAN,
                       activeforeground=FG_TEXT, font=("Segoe UI", 9)).pack(side="left", padx=12)

        tk.Button(bf, text="Понятно, закрыть", font=("Segoe UI", 10),
                  bg=ACCENT_INDIGO, fg="#fff", bd=0, padx=20, pady=6,
                  activebackground=ACCENT_HOVER, command=self._close).pack(side="right", padx=12)

    def _close(self):
        if self.dont_show.get():
            APP_SETTINGS["show_startup_guide"] = False
            save_json(SETTINGS_FILE, APP_SETTINGS)
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# 16. ГЛАВНОЕ ОКНО GUI
# ══════════════════════════════════════════════════════════════════════════════

class FSBalancerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FS25 — Автобалансировщик v13.0 Ultimate")
        self.root.geometry("1440x920")
        self.root.configure(bg=BG_OBSIDIAN)
        self.root.minsize(1200, 700)

        self.anim = AnimationEngine(root)

        self._setup_styles()

        # ── Переменные ──
        default_mods = os.path.expanduser("~/Documents/My Games/FarmingSimulator2025/mods")
        if not os.path.isdir(default_mods):
            default_mods = os.path.abspath("./mods")

        self.mods_dir     = tk.StringVar(value=default_mods)
        self.add_curr     = tk.BooleanVar(value=True)
        self.rate          = tk.DoubleVar(value=100.0)
        self.k_cis         = tk.DoubleVar(value=0.42)
        self.k_asian       = tk.DoubleVar(value=0.65)
        self.k_west        = tk.DoubleVar(value=1.00)
        self.k_place       = tk.DoubleVar(value=1.0)
        self.backup        = tk.BooleanVar(value=True)
        self.use_ai        = tk.BooleanVar(value=True)
        self.model_name    = tk.StringVar(value="phi3")
        self.scan_target   = tk.StringVar(value="ALL")
        self.search_var    = tk.StringVar()

        self.overrides: Dict[str, int] = {}
        self.row_specs: Dict[str, ItemSpec] = {}
        self.all_specs: List[ItemSpec] = []
        self.is_busy = False
        self.stop_event = threading.Event()

        self._build_ui()

        if APP_SETTINGS.get("show_startup_guide", True):
            self.root.after(600, lambda: StartupGuide(self.root))

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")

        s.configure(".", background=BG_OBSIDIAN, foreground=FG_TEXT,
                    fieldbackground=BG_INPUT, bordercolor=BORDER_SUBTLE)

        s.configure("TNotebook", background=BG_OBSIDIAN, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_TEXT,
                    padding=[18, 9], font=("Segoe UI", 9, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT_INDIGO)],
              foreground=[("selected", "#ffffff")])

        s.configure("TLabel", background=BG_OBSIDIAN, foreground=FG_TEXT, font=("Segoe UI", 9))
        s.configure("TLabelframe", background=BG_OBSIDIAN, foreground=FG_TEXT,
                    bordercolor=BORDER_SUBTLE, borderwidth=1)
        s.configure("TLabelframe.Label", background=BG_OBSIDIAN, foreground=ACCENT_INDIGO,
                    font=("Segoe UI", 10, "bold"))

        s.configure("TButton", background=BG_CARD, foreground=FG_TEXT,
                    borderwidth=0, focusthickness=0, font=("Segoe UI", 9), padding=6)
        s.map("TButton",
              background=[("active", ACCENT_INDIGO), ("pressed", ACCENT_HOVER)],
              foreground=[("active", "#fff")])

        s.configure("Accent.TButton", background=ACCENT_INDIGO, foreground="#fff",
                    font=("Segoe UI", 9, "bold"))
        s.map("Accent.TButton",
              background=[("active", ACCENT_HOVER)])

        s.configure("Green.TButton", background=ACCENT_GREEN, foreground="#fff",
                    font=("Segoe UI", 9, "bold"))
        s.map("Green.TButton", background=[("active", ACCENT_EMERALD)])

        s.configure("TCheckbutton", background=BG_OBSIDIAN, foreground=FG_TEXT, font=("Segoe UI", 9))
        s.map("TCheckbutton", background=[("active", BG_OBSIDIAN)])

        s.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_CARD,
                    foreground=FG_TEXT, selectbackground=ACCENT_INDIGO,
                    selectforeground="#fff")
        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_INDIGO)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#fff")

        s.configure("TProgressbar", troughcolor=BG_CARD, background=ACCENT_INDIGO,
                    bordercolor=BG_CARD, lightcolor=ACCENT_INDIGO, darkcolor=ACCENT_HOVER)

        # Treeview
        s.configure("Main.Treeview", background=BG_INPUT, foreground=FG_TEXT,
                    fieldbackground=BG_INPUT, rowheight=26,
                    font=("Segoe UI", 9))
        s.configure("Main.Treeview.Heading", background=BG_CARD,
                    foreground=FG_TEXT, font=("Segoe UI", 9, "bold"),
                    borderwidth=0)
        s.map("Main.Treeview",
              background=[("selected", ACCENT_INDIGO)],
              foreground=[("selected", "#fff")])

    def _build_ui(self):
        # ── Заголовок ──
        header = tk.Frame(self.root, bg=BG_CARD, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⚙️ FS25 Автобалансировщик v13.0",
                 font=("Segoe UI", 14, "bold"), bg=BG_CARD, fg=ACCENT_INDIGO).pack(side="left", padx=16)

        self.ai_badge = tk.Label(header, text="🔴 ИИ выключен",
                                 font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=ACCENT_RED)
        self.ai_badge.pack(side="right", padx=16)

        self.stats_lbl = tk.Label(header, text="", font=("Segoe UI", 9),
                                  bg=BG_CARD, fg=FG_MUTED)
        self.stats_lbl.pack(side="right", padx=20)

        # ── Notebook ──
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        tab_main = tk.Frame(nb, bg=BG_OBSIDIAN)
        tab_pro  = tk.Frame(nb, bg=BG_OBSIDIAN)
        nb.add(tab_main, text="  🚜 Балансировщик  ")
        nb.add(tab_pro,  text="  ⚙️ ПРО-режим  ")

        self._build_main(tab_main)
        self._build_pro(tab_pro)

        # ── Статус бар ──
        sb = tk.Frame(self.root, bg=BG_CARD, height=30)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        self.status_var = tk.StringVar(value="✨ Готов к работе — FS25 Балансировщик v13.0 Ultimate")
        self.status_lbl = tk.Label(sb, textvariable=self.status_var,
                                   font=("Segoe UI", 9), bg=BG_CARD, fg=FG_MUTED, anchor="w")
        self.status_lbl.pack(fill="x", padx=12, pady=4)

        self._poll_ai()

    # ── Главная вкладка ──
    def _build_main(self, parent):
        # Панель настроек (компактная)
        settings_frame = tk.Frame(parent, bg=BG_OBSIDIAN)
        settings_frame.pack(fill="x", padx=10, pady=6)

        # Строка 1: Путь
        row1 = tk.Frame(settings_frame, bg=BG_CARD, bd=0, highlightthickness=1,
                        highlightbackground=BORDER_SUBTLE)
        row1.pack(fill="x", pady=3)

        tk.Label(row1, text="📁 Папка mods:", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_TEXT).pack(side="left", padx=8, pady=6)

        e = tk.Entry(row1, textvariable=self.mods_dir, font=("Segoe UI", 9),
                     bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                     bd=0, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        e.pack(side="left", fill="x", expand=True, padx=4, pady=6)

        tk.Button(row1, text="Обзор...", font=("Segoe UI", 9),
                  bg=BG_INPUT, fg=FG_TEXT, bd=0, padx=12,
                  activebackground=ACCENT_INDIGO, activeforeground="#fff",
                  command=self._choose_dir).pack(side="right", padx=8, pady=6)

        # Строка 2: Тип сканирования + режим валюты
        row2 = tk.Frame(settings_frame, bg=BG_CARD, bd=0, highlightthickness=1,
                        highlightbackground=BORDER_SUBTLE)
        row2.pack(fill="x", pady=3)

        tk.Label(row2, text="🎯 Цель:", font=("Segoe UI", 9, "bold"),
                 bg=BG_CARD, fg=ACCENT_CYAN).pack(side="left", padx=8, pady=6)

        for val, (tgt, lbl) in enumerate(SCAN_TARGET_LABELS.items()):
            tk.Radiobutton(
                row2, text=lbl, variable=self.scan_target, value=tgt.name,
                font=("Segoe UI", 9), bg=BG_CARD, fg=FG_TEXT,
                selectcolor=BG_INPUT, activebackground=BG_CARD,
                activeforeground=ACCENT_INDIGO, indicatoron=True
            ).pack(side="left", padx=8, pady=6)

        ttk.Separator(row2, orient="vertical").pack(side="left", fill="y", padx=8, pady=4)

        tk.Checkbutton(
            row2, text="💱 Additional Currencies", variable=self.add_curr,
            font=("Segoe UI", 9), bg=BG_CARD, fg=FG_TEXT,
            selectcolor=BG_INPUT, activebackground=BG_CARD
        ).pack(side="left", padx=8, pady=6)

        # Строка 3: Коэффициенты
        row3 = tk.Frame(settings_frame, bg=BG_CARD, bd=0, highlightthickness=1,
                        highlightbackground=BORDER_SUBTLE)
        row3.pack(fill="x", pady=3)

        params = [
            ("Курс:", self.rate, 5),
            ("СНГ:", self.k_cis, 4),
            ("Азия:", self.k_asian, 4),
            ("Запад:", self.k_west, 4),
            ("Здания:", self.k_place, 4),
        ]
        for label, var, w in params:
            tk.Label(row3, text=label, font=("Segoe UI", 9),
                     bg=BG_CARD, fg=FG_MUTED).pack(side="left", padx=(8, 2), pady=6)
            en = tk.Entry(row3, textvariable=var, width=w, font=("Segoe UI", 9),
                          bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                          bd=0, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
            en.pack(side="left", padx=(0, 6), pady=6)

        tk.Checkbutton(row3, text="📦 Бэкап", variable=self.backup,
                       font=("Segoe UI", 9), bg=BG_CARD, fg=FG_TEXT,
                       selectcolor=BG_INPUT, activebackground=BG_CARD).pack(side="left", padx=8)
        tk.Checkbutton(row3, text="🤖 ИИ", variable=self.use_ai,
                       font=("Segoe UI", 9), bg=BG_CARD, fg=FG_TEXT,
                       selectcolor=BG_INPUT, activebackground=BG_CARD).pack(side="left", padx=4)

        # Строка 4: ИИ-модель + кнопки
        row4 = tk.Frame(settings_frame, bg=BG_CARD, bd=0, highlightthickness=1,
                        highlightbackground=BORDER_SUBTLE)
        row4.pack(fill="x", pady=3)

        tk.Label(row4, text="🧠 Модель:", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_TEXT).pack(side="left", padx=8, pady=6)

        mc = ttk.Combobox(row4, textvariable=self.model_name,
                          values=["phi3", "gemma2:2b", "llama3.2:3b", "mistral", "qwen2.5:3b"],
                          width=14, state="readonly", font=("Segoe UI", 9))
        mc.pack(side="left", padx=4, pady=6)
        mc.bind("<<ComboboxSelected>>", self._on_model_change)

        self.model_desc = tk.Label(row4, text="", font=("Segoe UI", 8, "italic"),
                                   bg=BG_CARD, fg=ACCENT_PURPLE)
        self.model_desc.pack(side="left", padx=12, pady=6)
        self._update_model_desc(self.model_name.get())

        ai_btns = [
            ("📥 Ollama", self._install_ollama),
            ("⬇ Скачать", self._download_model),
            ("🚀 Старт", self._start_ai),
            ("⏹ Стоп", self._stop_ai),
            ("🗑 Удалить", self._delete_model),
            ("📖 Гайд", lambda: StartupGuide(self.root)),
        ]
        for txt, cmd in ai_btns:
            tk.Button(row4, text=txt, font=("Segoe UI", 8),
                      bg=BG_INPUT, fg=FG_TEXT, bd=0, padx=8, pady=3,
                      activebackground=ACCENT_INDIGO, activeforeground="#fff",
                      command=cmd).pack(side="left", padx=2, pady=6)

        # Поиск + кнопки действий
        action_frame = tk.Frame(parent, bg=BG_OBSIDIAN)
        action_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(action_frame, text="🔍", font=("Segoe UI", 12),
                 bg=BG_OBSIDIAN, fg=FG_MUTED).pack(side="left")

        self.search_var.trace_add("write", self._filter_table)
        se = tk.Entry(action_frame, textvariable=self.search_var, width=28,
                      font=("Segoe UI", 9), bg=BG_INPUT, fg=FG_TEXT,
                      insertbackground=FG_TEXT, bd=0, highlightthickness=1,
                      highlightbackground=BORDER_SUBTLE)
        se.pack(side="left", padx=6)

        self.btn_scan = tk.Button(
            action_frame, text="🔍 Сканировать", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_INDIGO, fg="#fff", bd=0, padx=18, pady=6,
            activebackground=ACCENT_HOVER, activeforeground="#fff",
            command=lambda: self._start_work(False))
        self.btn_scan.pack(side="left", padx=8)

        self.btn_apply = tk.Button(
            action_frame, text="✅ Применить баланс", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_GREEN, fg="#fff", bd=0, padx=18, pady=6,
            activebackground=ACCENT_EMERALD, activeforeground="#fff",
            command=lambda: self._start_work(True))
        self.btn_apply.pack(side="left", padx=4)

        self.btn_stop = tk.Button(
            action_frame, text="⏹ Стоп", font=("Segoe UI", 10),
            bg=ACCENT_RED, fg="#fff", bd=0, padx=14, pady=6,
            activebackground="#dc2626", state="disabled",
            command=self._stop_work)
        self.btn_stop.pack(side="left", padx=4)

        self.btn_restore = tk.Button(
            action_frame, text="↩ Бэкап", font=("Segoe UI", 9),
            bg=BG_CARD, fg=FG_TEXT, bd=0, padx=12, pady=6,
            activebackground=ACCENT_INDIGO, command=self._restore)
        self.btn_restore.pack(side="right", padx=4)

        # Подсказка
        tk.Label(action_frame, text="💡 Двойной клик → ручная цена",
                 font=("Segoe UI", 8), bg=BG_OBSIDIAN, fg=FG_DIM).pack(side="right", padx=12)

        # Прогресс
        pf_frame = tk.Frame(parent, bg=BG_OBSIDIAN)
        pf_frame.pack(fill="x", padx=10, pady=2)

        self.progress = ttk.Progressbar(pf_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

        self.progress_lbl = tk.Label(pf_frame, text="", font=("Segoe UI", 9),
                                     bg=BG_OBSIDIAN, fg=ACCENT_INDIGO)
        self.progress_lbl.pack(anchor="w", pady=2)

        # Таблица
        table_frame = tk.Frame(parent, bg=BG_OBSIDIAN)
        table_frame.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("type", "mod", "title", "brand", "origin", "cat", "specs",
                "old_price", "new_price", "rub_price", "configs")

        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                 height=18, style="Main.Treeview")

        self.tree.tag_configure("ok", background="#052e16", foreground="#bbf7d0")
        self.tree.tag_configure("review", background="#450a0a", foreground="#fecaca")
        self.tree.tag_configure("place_ok", background="#172554", foreground="#bfdbfe")
        self.tree.tag_configure("place_review", background="#451a03", foreground="#fed7aa")

        hdrs = {
            "type":      ("",            36),
            "mod":       ("Мод",         140),
            "title":     ("Название",    190),
            "brand":     ("Бренд",       85),
            "origin":    ("Регион",      130),
            "cat":       ("Категория",   110),
            "specs":     ("Характеристики", 220),
            "old_price": ("Старая",      85),
            "new_price": ("Новая XML",   85),
            "rub_price": ("Рубли ₽",     110),
            "configs":   ("Конфиг.",     75),
        }
        for col, (text, w) in hdrs.items():
            self.tree.heading(col, text=text)
            anc = "center" if col in ("type", "old_price", "new_price", "rub_price", "configs") else "w"
            self.tree.column(col, width=w, anchor=anc)

        self.tree.bind("<Double-1>", self._on_dblclick)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ── ПРО-вкладка ──
    def _build_pro(self, parent):
        # Предупреждение
        warn = tk.Frame(parent, bg="#451a03", height=40)
        warn.pack(fill="x", padx=12, pady=(8, 4))
        warn.pack_propagate(False)
        tk.Label(warn, text="⚠️ ПРО-режим — для опытных пользователей! Изменяет системные настройки ИИ.",
                 font=("Segoe UI", 10, "bold"), bg="#451a03", fg=ACCENT_AMBER).pack(pady=8, padx=12)

        # Промпт
        pf = tk.LabelFrame(parent, text="🧠 Системный промпт ИИ", font=("Segoe UI", 10, "bold"),
                           bg=BG_OBSIDIAN, fg=ACCENT_INDIGO, bd=1)
        pf.pack(fill="both", expand=True, padx=12, pady=6)

        self.prompt_text = tk.Text(pf, wrap="word", height=7, font=("Consolas", 9),
                                   bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                                   bd=0, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.prompt_text.pack(fill="both", expand=True, padx=8, pady=6)
        self.prompt_text.insert("1.0", PRO_DATA.get("custom_prompt", DEFAULT_AI_PROMPT))

        # Списки брендов
        lists = tk.Frame(parent, bg=BG_OBSIDIAN)
        lists.pack(fill="both", expand=True, padx=12, pady=6)

        for side, title, key, default in [
            ("left", "🌍 Западные бренды", "western_brands", DEFAULT_WESTERN_BRANDS),
            ("right", "🇷🇺 Бренды СНГ", "cis_brands", DEFAULT_CIS_BRANDS),
        ]:
            lf = tk.LabelFrame(lists, text=title, font=("Segoe UI", 10, "bold"),
                               bg=BG_OBSIDIAN, fg=ACCENT_INDIGO, bd=1)
            lf.pack(side=side, fill="both", expand=True, padx=4)

            txt = tk.Text(lf, wrap="word", height=5, font=("Consolas", 9),
                          bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                          bd=0, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
            txt.pack(fill="both", expand=True, padx=6, pady=6)
            txt.insert("1.0", "\n".join(PRO_DATA.get(key, default)))

            if "west" in key.lower():
                self.west_text = txt
            else:
                self.cis_text = txt

        # Кнопки
        bf = tk.Frame(parent, bg=BG_OBSIDIAN)
        bf.pack(fill="x", padx=12, pady=8)

        tk.Button(bf, text="💾 Сохранить ПРО", font=("Segoe UI", 10, "bold"),
                  bg=ACCENT_INDIGO, fg="#fff", bd=0, padx=20, pady=6,
                  activebackground=ACCENT_HOVER, command=self._save_pro).pack(side="left", padx=4)

        tk.Button(bf, text="🔄 Сброс", font=("Segoe UI", 10),
                  bg=BG_CARD, fg=FG_TEXT, bd=0, padx=16, pady=6,
                  activebackground=ACCENT_AMBER, command=self._reset_pro).pack(side="left", padx=4)

        tk.Button(bf, text="🧹 Очистить память и кэш", font=("Segoe UI", 10),
                  bg=ACCENT_RED, fg="#fff", bd=0, padx=16, pady=6,
                  activebackground="#dc2626", command=self._clear_caches).pack(side="right", padx=4)

    # ── Утилиты GUI ──
    def _model_descriptions(self) -> Dict[str, str]:
        return {
            "phi3":         "📌 Phi-3 (~2.3 ГБ) — Баланс скорости и точности",
            "gemma2:2b":    "⚡ Gemma 2 (~1.6 ГБ) — Самая лёгкая и быстрая",
            "llama3.2:3b":  "🧠 Llama 3.2 (~2.0 ГБ) — Глубокое понимание",
            "mistral":      "🔥 Mistral 7B (~4.4 ГБ) — Максимальная точность",
            "qwen2.5:3b":   "💎 Qwen 2.5 (~2.2 ГБ) — Отлично с русскими названиями",
        }

    def _update_model_desc(self, name: str):
        d = self._model_descriptions()
        self.model_desc.configure(text=d.get(name, "ИИ-модель"))

    def _on_model_change(self, e=None):
        self._update_model_desc(self.model_name.get())

    def _poll_ai(self):
        def check():
            ok, models = check_ollama()
            target = self.model_name.get()
            if ok and any(target in m for m in models):
                self.root.after(0, lambda: self.ai_badge.configure(
                    text=f"🟢 ИИ: {target}", fg=ACCENT_GREEN))
            elif ok:
                self.root.after(0, lambda: self.ai_badge.configure(
                    text=f"🟡 Нет модели {target}", fg=ACCENT_AMBER))
            else:
                self.root.after(0, lambda: self.ai_badge.configure(
                    text="🔴 ИИ выключен", fg=ACCENT_RED))
        threading.Thread(target=check, daemon=True).start()
        self.root.after(3000, self._poll_ai)

    def _filter_table(self, *a):
        q = self.search_var.get().lower().strip()
        for rid in self.tree.get_children():
            vals = self.tree.item(rid, "values")
            if any(q in str(v).lower() for v in vals):
                self.tree.reattach(rid, "", "end")
            else:
                self.tree.detach(rid)

    def _choose_dir(self):
        d = filedialog.askdirectory(title="Выберите папку mods")
        if d:
            self.mods_dir.set(d)

    def _get_cfg(self) -> BalancerConfig:
        tgt_map = {"VEHICLES": ScanTarget.VEHICLES, "PLACEABLES": ScanTarget.PLACEABLES,
                    "ALL": ScanTarget.ALL}
        return BalancerConfig(
            use_additional_currencies=self.add_curr.get(),
            exchange_rate=max(1.0, self.rate.get()),
            k_cis=max(0.05, self.k_cis.get()),
            k_asian=max(0.05, self.k_asian.get()),
            k_western=max(0.05, self.k_west.get()),
            k_placeable=max(0.05, self.k_place.get()),
            create_backups=self.backup.get(),
            use_local_ai=self.use_ai.get(),
            ai_model_name=self.model_name.get(),
            scan_target=tgt_map.get(self.scan_target.get(), ScanTarget.ALL),
        )

    # ── ИИ операции ──
    def _install_ollama(self):
        def w():
            install_ollama_app(
                lambda m: self.root.after(0, lambda: self.status_var.set(m)),
                lambda m: self.root.after(0, lambda: messagebox.showinfo("Ollama", m, parent=self.root)))
        threading.Thread(target=w, daemon=True).start()

    def _download_model(self):
        name = self.model_name.get()
        self.anim.start_pulse(self.ai_badge, "dl")
        def w():
            download_model(name,
                lambda m: self.root.after(0, lambda: self.status_var.set(m)),
                lambda m: self.root.after(0, self._on_dl_done, m))
        threading.Thread(target=w, daemon=True).start()

    def _on_dl_done(self, msg):
        self.anim.stop_pulse("dl")
        messagebox.showinfo("Модель", msg, parent=self.root)

    def _start_ai(self):
        def w():
            if start_ollama(lambda m: self.root.after(0, lambda: self.status_var.set(m))):
                self.root.after(0, lambda: messagebox.showinfo("ИИ", "Служба запущена!", parent=self.root))
            else:
                self.root.after(0, lambda: messagebox.showwarning("ИИ", "Не удалось.", parent=self.root))
        threading.Thread(target=w, daemon=True).start()

    def _stop_ai(self):
        def w():
            stop_ollama(lambda m: self.root.after(0, lambda: self.status_var.set(m)))
        threading.Thread(target=w, daemon=True).start()

    def _delete_model(self):
        name = self.model_name.get()
        if not messagebox.askyesno("Удаление", f"Удалить модель '{name}'?", parent=self.root):
            return
        def w():
            delete_model(name,
                lambda m: self.root.after(0, lambda: self.status_var.set(m)),
                lambda m: self.root.after(0, lambda: messagebox.showinfo("ИИ", m, parent=self.root)))
        threading.Thread(target=w, daemon=True).start()

    # ── ПРО операции ──
    def _save_pro(self):
        PRO_DATA["custom_prompt"] = self.prompt_text.get("1.0", "end-1c")
        PRO_DATA["western_brands"] = [b.strip().lower() for b in self.west_text.get("1.0", "end-1c").splitlines() if b.strip()]
        PRO_DATA["cis_brands"] = [b.strip().lower() for b in self.cis_text.get("1.0", "end-1c").splitlines() if b.strip()]
        save_json(PRO_SETTINGS_FILE, PRO_DATA)
        messagebox.showinfo("ПРО", "Настройки сохранены!", parent=self.root)

    def _reset_pro(self):
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", DEFAULT_AI_PROMPT)
        self.west_text.delete("1.0", "end")
        self.west_text.insert("1.0", "\n".join(DEFAULT_WESTERN_BRANDS))
        self.cis_text.delete("1.0", "end")
        self.cis_text.insert("1.0", "\n".join(DEFAULT_CIS_BRANDS))
        PRO_DATA.update({"custom_prompt": DEFAULT_AI_PROMPT,
                         "western_brands": DEFAULT_WESTERN_BRANDS,
                         "cis_brands": DEFAULT_CIS_BRANDS})
        save_json(PRO_SETTINGS_FILE, PRO_DATA)
        messagebox.showinfo("ПРО", "Сброшено.", parent=self.root)

    def _clear_caches(self):
        if not messagebox.askyesno("Очистка", "Сбросить всю память?", parent=self.root):
            return
        LEARNED_BRANDS.clear()
        MODS_CACHE.clear()
        AI_BRAND_CACHE.clear()
        PLACEABLE_MEMORY.clear()
        for f in (LEARNED_BRANDS_FILE, CACHE_INDEX_FILE, LEARNED_PLACEABLES):
            if os.path.isfile(f):
                os.remove(f)
        messagebox.showinfo("✅", "Память очищена.", parent=self.root)

    # ── Двойной клик ──
    def _on_dblclick(self, event):
        if self.is_busy:
            return
        iid = self.tree.focus()
        if not iid or iid not in self.row_specs:
            return
        spec = self.row_specs[iid]
        cfg = self._get_cfg()

        val = simpledialog.askinteger(
            "Ручная цена",
            f"{spec.type_icon} {spec.title}\nВведите цену в РУБЛЯХ (₽):",
            initialvalue=spec.new_price_rub, minvalue=100, parent=self.root)
        if val is None:
            return

        xm = 1.0 if cfg.use_additional_currencies else cfg.exchange_rate
        new_xml = int(round(val / xm)) if cfg.use_additional_currencies else val
        self.overrides[spec.unique_key] = max(10, new_xml)
        spec.new_price = new_xml
        dm = cfg.exchange_rate if cfg.use_additional_currencies else 1.0
        spec.new_price_rub = int(round(new_xml * dm))

        vals = list(self.tree.item(iid, "values"))
        vals[8] = f"{spec.new_price:,}".replace(",", " ")
        vals[9] = f"{spec.new_price_rub:,} ₽ ✏️".replace(",", " ")
        self.tree.item(iid, values=vals)

    # ── Восстановление бэкапа ──
    def _restore(self):
        if self.is_busy:
            return
        md = self.mods_dir.get().strip()
        bd = os.path.join(md, "_backup_original_mods")
        if not os.path.isdir(bd):
            messagebox.showinfo("Бэкап", "Папка бэкапа не найдена.", parent=self.root)
            return
        files = [f for f in os.listdir(bd) if f.lower().endswith(".zip")]
        for f in files:
            shutil.copy2(os.path.join(bd, f), os.path.join(md, f))
        messagebox.showinfo("✅", f"Восстановлено: {len(files)} файлов.", parent=self.root)

    # ── Основная работа ──
    def _start_work(self, apply: bool):
        if self.is_busy:
            return
        md = self.mods_dir.get().strip()
        if not os.path.isdir(md):
            messagebox.showerror("Ошибка", f"Папка не найдена:\n{md}", parent=self.root)
            return
        if apply and not messagebox.askyesno("Подтверждение",
                "Записать новые цены?\nБэкап будет создан автоматически.", parent=self.root):
            return

        self.is_busy = True
        self.stop_event.clear()
        self.all_specs.clear()

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.row_specs.clear()

        self.btn_scan.configure(state="disabled")
        self.btn_apply.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        self.anim.start_spinner(self.progress_lbl, "scan", "Сканирование...")

        cfg = self._get_cfg()
        threading.Thread(target=self._worker, args=(md, cfg, apply), daemon=True).start()

    def _stop_work(self):
        self.stop_event.set()
        self.status_var.set("⏹ Прерывание...")

    def _worker(self, mods_dir: str, cfg: BalancerConfig, apply: bool):
        backup_dir = os.path.join(mods_dir, "_backup_original_mods")
        items = sorted([
            f for f in os.listdir(mods_dir)
            if not f.startswith("_backup") and (
                f.lower().endswith(".zip") or os.path.isdir(os.path.join(mods_dir, f)))
        ])
        total = max(1, len(items))
        found = 0
        uncertain: List[ItemSpec] = []
        type_counts = defaultdict(int)
        t0 = time.time()

        for idx, item in enumerate(items, 1):
            if self.stop_event.is_set():
                break

            path = os.path.join(mods_dir, item)
            self.root.after(0, self._upd_progress, idx, total, item)

            specs = process_mod(path, cfg, apply, backup_dir, self.overrides, self.stop_event)
            for s in specs:
                found += 1
                type_counts[s.item_type] += 1
                self.all_specs.append(s)
                if s.needs_review:
                    uncertain.append(s)
                self.root.after(0, self._insert_row, s)

        elapsed = time.time() - t0
        save_json(CACHE_INDEX_FILE, MODS_CACHE)
        self.root.after(0, self._finish, found, apply, uncertain, type_counts, elapsed)

    def _upd_progress(self, cur, total, item):
        self.progress["maximum"] = total
        self.progress["value"] = cur
        pct = int(cur / total * 100)
        self.anim.stop_spinner("scan")
        self.progress_lbl.configure(
            text=f"{'⠸' if cur % 2 == 0 else '⠇'} [{cur}/{total}] {pct}% — {item}")
        self.status_var.set(f"Обработка: {item}")

    def _insert_row(self, s: ItemSpec):
        is_manual = s.unique_key in self.overrides
        rub = f"{s.new_price_rub:,} ₽".replace(",", " ")
        if is_manual:
            rub += " ✏️"

        if s.item_type == "placeable":
            tag = "place_review" if s.needs_review else "place_ok"
        else:
            tag = "review" if s.needs_review else "ok"

        iid = self.tree.insert("", "end", values=(
            s.type_icon, s.mod_name, s.title, s.brand, s.origin_group,
            s.category, s.specs_str,
            f"{s.old_price:,}".replace(",", " "),
            f"{s.new_price:,}".replace(",", " "),
            rub,
            f"{s.configs_updated}" if s.item_type == "vehicle" else "—"
        ), tags=(tag,))
        self.row_specs[iid] = s

    def _finish(self, found: int, apply: bool, uncertain: List[ItemSpec],
                counts: dict, elapsed: float):
        self.is_busy = False
        self.btn_scan.configure(state="normal")
        self.btn_apply.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.progress["value"] = 0
        self.anim.stop_spinner("scan")
        self.progress_lbl.configure(text="")

        if HAS_SOUND:
            try:
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            except Exception:
                pass

        # Статистика
        v_cnt = counts.get("vehicle", 0)
        p_cnt = counts.get("placeable", 0)
        stats = f"🚜 {v_cnt}  🏗️ {p_cnt}  ⏱ {elapsed:.1f}с"
        self.stats_lbl.configure(text=stats)
        self.anim.flash_widget(self.stats_lbl, ACCENT_GREEN, FG_MUTED, 4)

        # Обучение
        if uncertain and not self.stop_event.is_set():
            filtered = []
            for s in uncertain:
                b = s.brand.strip().lower()
                if b in LEARNED_BRANDS and LEARNED_BRANDS[b]:
                    r = LEARNED_BRANDS[b]
                    s.origin_group = f"{r} (📚)"
                else:
                    filtered.append(s)
            if filtered:
                self.root.after(200, lambda: ReviewDialog(
                    self.root, filtered, self._get_cfg(), self.anim))

        action = "Прервано" if self.stop_event.is_set() else (
            "✅ Применено!" if apply else "🔍 Сканирование завершено")
        self.status_var.set(f"{action} | Найдено: {found} (🚜{v_cnt} 🏗️{p_cnt}) за {elapsed:.1f}с")

        if apply and not self.stop_event.is_set():
            messagebox.showinfo("✅ Готово",
                f"Цены обновлены!\n\n"
                f"🚜 Техника: {v_cnt}\n"
                f"🏗️ Здания/объекты: {p_cnt}\n"
                f"⏱ Время: {elapsed:.1f} сек",
                parent=self.root)


# ══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    app = FSBalancerApp(root)
    root.mainloop()