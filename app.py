# -*- coding: utf-8 -*-
"""FS25 Balancer v15 — точка входа: окно PyWebView + мост Python<->JS."""

import json, os, sys, threading

import webview

from core import storage
from core.ai_state import init_state
from core.countries import countries_payload, GROUP_LABELS
from core.service import BalancerService, drain_events
from core.models import SCAN_TARGET_LABELS, ScanTarget

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
        "ИИ в один клик: каталог 12 моделей + mistral, рекомендация по железу",
        "Удаление моделей и деинсталляция Ollama прямо из программы",
        "Общий выключатель режима «Ретро» в настройках",
        "Фиксы: прокрутка колесом, кэш WebView2, обучающий тур, тост о мосте",
        "Кинематографичная заставка в стиле Ubisoft",
        "Фиксы: галочка тура, достижимая прокрутка",
        "Один скролл на вкладке, яркая пульсация рекомендации",
        "Заставка уровня кинотитров: частицы, неоновый пол, орбита, глитч, вспышка",
        "Мягкий звук заставки (WebAudio-синтез), прогресс pull с % и скоростью, статус VRAM моделей",
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
        self._svc = BalancerService()
        self._svc.load_settings()
        self._win = None
        self._ai_cache = {"running": False, "models": []}

    def bind(self, win):
        self._win = win

    def log(self, msg) -> dict:
        try:
            import datetime
            with open(storage.path_of("crash.log"), "a", encoding="utf-8") as f:
                f.write("[js] " + str(msg) + " @ " + str(datetime.datetime.now().time()) + chr(10))
        except Exception:
            pass
        return {"ok": True}

    # ── boot / poll ──
    def boot(self) -> dict:
        try:
            _cancel_dump()
            self.log("py boot() served start")
            threading.Thread(target=self._refresh_ai, daemon=True).start()
            payload = {
                "version": APP_VERSION_STR,
                "data_dir": storage.data_dir(),
                "default_mods_dir": self._svc.default_mods_dir(),
                "scan_targets": [{"key": t.name, "label": SCAN_TARGET_LABELS[t]}
                                 for t in ScanTarget],
                "countries": countries_payload(),
                "groups": dict(GROUP_LABELS),
                "config": self._svc.config_payload(),
                "pro": self._svc.pro_payload(),
                "changelog": CHANGELOG,
                "ai": self._ai_status(),
                "items": self._svc.items_payload(),
            }
            print("[boot] served, items:", len(payload.get("items") or []), flush=True)
            return payload
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"ok": False, "error": str(e), "version": APP_VERSION_STR,
                    "data_dir": "", "default_mods_dir": "", "scan_targets": [],
                    "countries": [], "config": {}, "pro": {}, "changelog": [],
                    "ai": {"running": False, "models": []}, "items": []}

    def poll(self) -> list:
        return drain_events()

    # ── config ──
    def set_config(self, patch: dict) -> dict:
        try:
            self._svc.update_config(patch)
            return {"ok": True, "config": self._svc.config_payload()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def choose_dir(self) -> dict:
        if not self._win:
            return {"ok": False, "error": "Окно не готово"}
        result = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            path = result[0] if isinstance(result[0], str) else str(result[0])
            self._svc.cfg.mods_dir = path
            self._svc.save_settings()
            return {"ok": True, "path": path}
        return {"ok": False, "error": ""}

    # ── scan / recalc / apply ──
    def start_scan(self, apply: bool = False) -> dict:
        return self._svc.start_scan(bool(apply))

    def stop_scan(self) -> dict:
        self._svc.stop()
        return {"ok": True}

    def recalculate(self) -> dict:
        return self._svc.recalculate()

    def apply_results(self) -> dict:
        return self._svc.apply_results()

    # ── row edits ──
    def set_country(self, key: str, country: str) -> dict:
        return self._svc.set_country(str(key), str(country))

    def set_retro(self, key: str, is_retro) -> dict:
        return self._svc.set_retro(str(key), bool(is_retro))

    def set_price(self, key: str, price) -> dict:
        try:
            return self._svc.set_price(str(key), int(float(price)))
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Цена: {e}"}

    def set_motor(self, key: str, idx, hp, delta) -> dict:
        try:
            return self._svc.set_motor(str(key), int(idx), float(hp), int(float(delta)))
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Мотор: {e}"}

    def patch_field(self, key: str, area, distance) -> dict:
        try:
            a = None if area in (None, "", -999) else float(area)
            d = None if distance in (None, "", -999) else float(distance)
            return self._svc.patch_field(str(key), a, d)
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Поле: {e}"}

    # ── PRO ──
    def update_pro(self, prompt=None, brands=None) -> dict:
        return self._svc.update_pro(str(prompt or ''), dict(brands or {}))

    def update_countries(self, countries: list, multipliers=None) -> dict:
        return self._svc.update_countries(list(countries or []), dict(multipliers or {}))

    def clear_memory(self) -> dict:
        self._svc.clear_memory()
        return {"ok": True}

    # ── AI / Ollama ──
    def _ai_status(self) -> dict:
        d = dict(self._ai_cache or {"running": False, "models": []})
        d["ok"] = bool(d.get("running"))
        return d

    def _refresh_ai(self) -> None:
        try:
            from core.ai import check_ollama
            ok, models = check_ollama()
            self._ai_cache = {"running": bool(ok), "models": list(models)}
        except Exception:
            self._ai_cache = {"running": False, "models": []}
        try:
            from core.service import emit
            emit("ai_status", dict(self._ai_cache))
        except Exception:
            pass

    def ai_status(self) -> dict:
        threading.Thread(target=self._refresh_ai, daemon=True).start()
        return self._ai_status()

    def _ai_setup_worker(self, model: str, need_install: bool) -> None:
        from core import ai as ai_mod
        from core.service import emit

        def prog(m):
            emit("ai_progress", m if isinstance(m, dict) else {"msg": str(m)})

        try:
            if need_install:
                if not ai_mod.install_ollama_silent(prog, prog):
                    emit("ai_done", {"msg": "Не удалось установить Ollama"})
                    return
            if not ai_mod.start_ollama(prog):
                emit("ai_done", {"msg": "Не удалось запустить службу Ollama"})
                return
            ok, models = ai_mod.check_ollama()
            if not any(str(model) in m for m in models):
                prog(f"Скачиваю модель {model}…")
                ai_mod.download_model(str(model), prog, prog)
            self._svc.update_config({"ai_model_name": str(model), "use_local_ai": True})
            self._refresh_ai()
            emit("ai_done", {"msg": f"Модель {model} готова — ИИ включён"})
        except Exception as e:
            emit("ai_done", {"msg": f"Ошибка настройки ИИ: {e}"})

    def ai_catalog(self) -> dict:
        from core.ai import model_catalog
        d = dict(model_catalog())
        d["current"] = self._svc.cfg.ai_model_name
        d["use_ai"] = bool(self._svc.cfg.use_local_ai)
        return d

    def ai_setup(self, model: str) -> dict:
        from core.ai import get_ollama_exe
        if not get_ollama_exe():
            return {"ok": False, "need_ollama": True}
        threading.Thread(target=self._ai_setup_worker, args=(str(model), False), daemon=True).start()
        return {"ok": True}

    def ai_install_setup(self, model: str) -> dict:
        threading.Thread(target=self._ai_setup_worker, args=(str(model), True), daemon=True).start()
        return {"ok": True}

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

    def ai_uninstall(self) -> dict:
        def w():
            from core.ai import uninstall_ollama
            from core.service import emit
            uninstall_ollama(lambda m: emit("ai_progress", {"msg": m}))
            self._refresh_ai()
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
                           lambda m: emit("ai_progress", m if isinstance(m, dict) else {"msg": str(m)}),
                           lambda m: emit("ai_done", {"msg": m}))
        threading.Thread(target=w, daemon=True).start()
        return {"ok": True}

    def ai_delete(self, model: str) -> dict:
        def w():
            from core.ai import delete_model, start_ollama
            from core.service import emit
            start_ollama(lambda m: None)
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

    def save_pro(self, prompt=None, brands=None) -> dict:
        return self.update_pro(prompt, brands)

    def select_countries(self, countries, multipliers=None) -> dict:
        return self.update_countries(list(countries or []), multipliers)

    def export_profile(self, path=None) -> dict:
        """Экспорт текущего профиля настроек как JSON-словаря."""
        try:
            if not path:
                return {"ok": False, "error": "Не указана папка для экспорта"}
            profile = {
                "version": APP_VERSION_STR,
                "config": self._svc.config_payload(),
                "pro": self._svc.pro_payload(),
                "countries": countries_payload(),
            }
            fn = os.path.join(str(path), "fs25balancer_profile.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
            return {"ok": True, "path": fn}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _setup_crashlog():
    import datetime, faulthandler, traceback
    path = storage.path_of("crash.log")
    logf = open(path, "a", encoding="utf-8", buffering=1)
    print("=== start", datetime.datetime.now().isoformat(timespec="seconds"), "===", file=logf)
    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb, file=logf)
        traceback.print_exception(exc_type, exc, tb)
    sys.excepthook = hook
    faulthandler.enable(file=logf)
    faulthandler.dump_traceback_later(20, file=logf)
    return logf


def _cancel_dump():
    import faulthandler
    try:
        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass


def _setup_pywebview_log():
    import logging
    lg = logging.getLogger("pywebview")
    lg.setLevel(logging.DEBUG)
    fh = logging.FileHandler(storage.path_of("webview.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(threadName)s %(levelname)s %(message)s"))
    lg.addHandler(fh)
    return fh


def main():
    # WebView2 иначе кэширует app.js/app.css между запусками — фиксы не долетают до пользователя
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                          "--disable-http-cache --autoplay-policy=no-user-gesture-required")
    logf = _setup_crashlog()
    _setup_pywebview_log()
    print("[boot] crashlog:", logf.name, flush=True)
    init_state()
    print("[boot] state ready", flush=True)
    api = Api()
    print("[boot] api ready, web root:", _web_root(), flush=True)
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
    win.events.loaded += lambda: print("[boot] event loaded", flush=True)
    win.events._pywebviewready += lambda: print("[boot] event pywebviewready", flush=True)
    print("[boot] window created; starting webview", flush=True)
    webview.start(debug=bool(os.environ.get("FS25_DEBUG")), private_mode=False)


if __name__ == "__main__":
    main()
