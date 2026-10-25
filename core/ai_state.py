# -*- coding: utf-8 -*-
"""Runtime-состояние PRO/памяти: единый источник для AI и parser (без циклов импорта)."""

from typing import Any, Dict, List

from core import storage
from core.brands import DEFAULT_COUNTRY_BRANDS, merge_defaults

_state: Dict[str, Any] = {
    "pro": {},
    "learned": {},
    "mods_cache": {},
    "placeables": {},
    "selected": [],
}


def init_state() -> None:
    pro = storage.load_json(storage.PRO_FILE, {})
    pro["country_brands"] = merge_defaults(pro.get("country_brands", {}))
    if not pro.get("custom_prompt"):
        from core.ai import DEFAULT_AI_PROMPT
        pro["custom_prompt"] = DEFAULT_AI_PROMPT
    _state["pro"] = pro
    _state["learned"] = storage.load_json(storage.LEARNED_BRANDS_FILE, {})
    _state["mods_cache"] = storage.load_json(storage.CACHE_FILE, {})
    _state["placeables"] = storage.load_json(storage.PLACEABLES_FILE, {})

    sel = storage.load_json(storage.COUNTRIES_FILE, [])
    from core.countries import ALL_COUNTRIES, DEFAULT_SELECTED_COUNTRIES
    sel = [c for c in sel if c in ALL_COUNTRIES]
    _state["selected"] = sel or list(DEFAULT_SELECTED_COUNTRIES)


def get_pro_data() -> Dict[str, Any]:
    return _state["pro"]


def set_pro_data(data: Dict[str, Any]) -> None:
    data["country_brands"] = merge_defaults(data.get("country_brands", {}))
    _state["pro"] = data


def get_learned() -> Dict[str, str]:
    return _state["learned"]


def get_mods_cache() -> Dict[str, str]:
    return _state["mods_cache"]


def get_placeable_memory() -> Dict[str, dict]:
    return _state["placeables"]


def get_selected() -> List[str]:
    return _state["selected"]


def set_selected(countries: List[str]) -> None:
    from core.countries import ALL_COUNTRIES
    _state["selected"] = [c for c in countries if c in ALL_COUNTRIES]


def persist() -> None:
    storage.save_json(storage.PRO_FILE, _state["pro"])
    storage.save_json(storage.LEARNED_BRANDS_FILE, _state["learned"])
    storage.save_json(storage.CACHE_FILE, _state["mods_cache"])
    storage.save_json(storage.PLACEABLES_FILE, _state["placeables"])
    storage.save_json(storage.COUNTRIES_FILE, _state["selected"])


def remember_brand(brand: str, country: str, is_retro: bool = False) -> None:
    """Память брендов = только страна. Ретро — свойство конкретной позиции."""
    b = (brand or "").strip().lower()
    if not b or b in ("lizard", "none", "generic"):
        return
    _state["learned"][b] = country


def clear_caches() -> None:
    _state["learned"].clear()
    _state["mods_cache"].clear()
    _state["placeables"].clear()
    for f in (storage.LEARNED_BRANDS_FILE, storage.CACHE_FILE, storage.PLACEABLES_FILE):
        p = storage.path_of(f)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass


import os  # noqa: E402  (нужен для clear_caches)
