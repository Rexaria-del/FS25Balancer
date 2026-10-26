# -*- coding: utf-8 -*-
"""Хранилище: настройки, кэши, память ИИ. Единая папка %APPDATA%/FS25Balancer."""

import json
import os
import shutil
from typing import Any, Dict, Optional

APP_NAME = "FS25Balancer"

SETTINGS_FILE = "app_settings.json"
PRO_FILE = "pro_settings.json"
LEARNED_BRANDS_FILE = "learned_brands.json"
CACHE_FILE = "mods_cache_index.json"
PLACEABLES_FILE = "learned_placeables.json"
COUNTRIES_FILE = "selected_countries.json"
LAST_SCAN_FILE = "last_scan.json"
SPEC_PATCH_FILE = "spec_patches.json"


def data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    else:
        path = os.path.join(os.environ.get("XDG_CONFIG_HOME") or
                            os.path.join(os.path.expanduser("~"), ".config"), APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _path(name: str) -> str:
    return os.path.join(data_dir(), name)


def _legacy_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def load_json(name: str, default: Optional[Any] = None) -> Any:
    if default is None:
        default = {}
    p = _path(name)
    if not os.path.isfile(p):
        legacy = os.path.join(_legacy_dir(), name)
        if os.path.isfile(legacy):
            try:
                shutil.copy2(legacy, p)
            except Exception:
                pass
        else:
            return default() if callable(default) else default
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
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


def path_of(name: str) -> str:
    return _path(name)


def export_bundle(dest_dir: str) -> str:
    """Копирует весь профиль настроек в выбранную папку (резервная копия)."""
    stamp = __import__("time").strftime("%Y%m%d_%H%M%S")
    target = os.path.join(dest_dir, f"{APP_NAME}_profile_{stamp}")
    os.makedirs(target, exist_ok=True)
    for fn in os.listdir(data_dir()):
        if fn.endswith(".json"):
            try:
                shutil.copy2(os.path.join(data_dir(), fn), os.path.join(target, fn))
            except Exception:
                pass
    return target


def list_state_files() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for fn in sorted(os.listdir(data_dir())):
        if fn.endswith(".json"):
            try:
                out[fn] = os.path.getsize(os.path.join(data_dir(), fn))
            except Exception:
                out[fn] = 0
    return out
