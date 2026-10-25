# -*- coding: utf-8 -*-
"""FS25 Balancer v15 — точка входа: окно PyWebView + мост Python<->JS."""

import json, os, sys, threading

import webview

from core import storage
from core.ai_state import init_state
from core.countries import countries_payload
from core.service import BalancerService, drain_events
from core.models import SCAN_TARGET_LABELS

APP_VERSION_STR = "15.0"
HERE = os.path.dirname(os.path.abspath(__file__))

CHANGELOG = [
    {"v": "15.0", "date": "2026-10-25", "items": [
        "Полный переход на PyWebView (HTML5/CSS3/JS) — glassmorphism, анимации",
        "177 стран мира + СССР, мультиселект с тегами",
        "Ретро-техника: тоггл в строке, слайдеры коэффициентов",
        "Комплектации двигателей: выпадающий список цен, редактор ТТХ",
        "Цены полей зависят от расстояния до магазина",
        "Кнопка «Обновить цены» без повторного сканирования",
        "PRO-режим: списки брендов по каждой стране",
        "Интерактивный онбординг (тур)",
        "История обновлений в приложении",
    ]},
    {"v": "14.0", "date": "2026-10-20", "items": [
        "Все страны мира, ретро-детект, комплектации",
    ]},
    {"v": "13.0", "date": "2026-10-15", "items": [
        "Здания, поля, анимации, обучение ИИ",
    ]},
]


def _web_root() -> str:
    base = getattr(sys, "_MEIPASS", HERE)
    cand = os.path.join(base, "web")
    if os.path.isdir(cand):
        return cand
    return os.path.join(HERE, "web")


class Api:
    def __init__(self):
        self.svc = BalancerService()
        self.svc.load_settings()
        self.win = None

    def bind(self, win):
        self.win = win

    # ── boot / poll ──
    def boot(self) -> dict:
        return {
            "version": APP_VERSION_STR,
            "countries": countries_payload(),
            "config": self.svc.config_payload(),
            "pro": self.svc.pro_payload(),
            "changelog": CHANGELOG,
            "ai": self._ai_status(),
        }

    def poll(self) -> list:
        return drain_events()

    # ── config ──
    def set_config(self, patch: dict) -> dict:
        try:
            self.svc.update_config(patch)
            return {"ok": True, "config": self.svc.config_payload()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def choose_dir(self) -> dict:
        if not self.win:
            return {"ok": False, "error": "Окно не готово"}
        result = self.win.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            path = result[0] if isinstance(result[0], str) else str(result[0])
            self.svc.cfg.mods_dir = path
            self.svc.save_settings()
            return {"ok": True, "path": path}
        return {"ok": False, "error": ""}

    # ── scan / recalc / apply ──
    def start_scan(self, apply: bool = False) -> dict:
        self.svc.start_scan(apply)
        return {"ok": True}

    def stop_scan(self) -> dict:
        self.svc.stop()
        return {"ok": True}

    def recalculate(self) -> dict:
        self.svc.recalculate()
        return {"ok": True}

    def apply_results(self) -> dict:
        self.svc.apply_results()
        return {"ok": True}

    # ── row edits ──
    def set_country(self, key: str, country: str) -> dict:
        return self.svc.set_country(str(key), str(country))

    def set_retro(self, key: str, is_retro) -> dict:
        return self.svc.set_retro(str(key), bool(is_retro))

    def set_price(self, key: str, price) -> dict:
        try:
            return self.svc.set_price(str(key), int(float(price)))
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Цена: {e}"}

    def set_motor(self, key: str, idx, hp, delta) -> dict:
        try:
            return self.svc.set_motor(str(key), int(idx), float(hp), int(float(delta)))
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Мотор: {e}"}

    def patch_field(self, key: str, area, distance) -> dict:
        try:
            a = None if area in (None, "", -999) else float(area)
            d = None if distance in (None, "", -999) else float(distance)
            return self.svc.patch_field(str(key), a, d)
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Поле: {e}"}

    # ── PRO ──
    def update_pro(self, data: dict) -> dict:
        return self.svc.update_pro(data)

    def update_countries(self, countries: list) -> dict:
        return self.svc.update_countries(countries)

    def clear_memory(self) -> dict:
        self.svc.clear_memory()
        return {"ok": True}

    # ── AI / Ollama ──
    def _ai_status(self) -> dict:
        from core.ai import check_ollama
        ok, models = check_ollama()
        return {"running": ok, "models": models}

    def ai_status(self) -> dict:
        return self._ai_status()

    def ai_start(self) -> dict:
        def w():
            from core.ai import start_ollama
            start_ollama(lambda m: None)
            from core.service import emit
            emit("ai_status", self._ai_status())
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}

    def ai_stop(self) -> dict:
        def w():
            from core.ai import stop_ollama
            stop_ollama(lambda m: None)
            from core.service import emit
            emit("ai_status", self._ai_status())
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}

    def ai_install(self) -> dict:
        def w():
            from core.ai import install_ollama_app
            install_ollama_app(lambda m: None, lambda m: None)
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}

    def ai_download(self, model: str) -> dict:
        def w():
            from core.ai import download_model
            from core.service import emit
            download_model(str(model),
                           lambda m: emit("ai_progress", {"msg": m}),
                           lambda m: emit("ai_done", {"msg": m}))
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}

    def ai_delete(self, model: str) -> dict:
        def w():
            from core.ai import delete_model
            from core.service import emit
            delete_model(str(model), lambda m: None,
                         lambda m: emit("ai_done", {"msg": m}))
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}


    # ── алиасы для контракта фронтенда ──
    def scan(self, apply: bool = False) -> dict:
        return self.start_scan(bool(apply))

    def stop(self) -> dict:
        return self.stop_scan()

    def recalc(self) -> dict:
        return self.recalculate()

    def apply(self) -> dict:
        return self.apply_results()

    def save_pro(self, data: dict) -> dict:
        return self.update_pro(data or {})

    def select_countries(self, countries) -> dict:
        return self.update_countries(list(countries or []))

    def export_profile(self) -> dict:
        """Экспорт текущего профиля настроек как JSON-словаря."""
        try:
            profile = {
                "version": APP_VERSION_STR,
                "config": self.svc.config_payload(),
                "pro": self.svc.pro_payload(),
                "countries": countries_payload(),
            }
            return {"ok": True, "profile": profile}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def main():
    init_state()
    api = Api()
    win = webview.create_window(
        f"FS25 Автобалансировщик v{APP_VERSION_STR}",
        url=os.path.join(_web_root(), "index.html"),
        js_api=api,
        width=1360,
        height=900,
        min_size=(1024, 680),
        background_color="#0b0d11",
        text_select=True,
    )
    api.bind(win)
    webview.start(debug=bool(os.environ.get("FS25_DEBUG")), private_mode=False)


if __name__ == "__main__":
    main()
