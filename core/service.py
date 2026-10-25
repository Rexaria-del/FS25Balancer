# -*- coding: utf-8 -*-
"""Слой сервиса: оркестрация сканирования/применения в фоновых потоках.

UI не блокируется: все тяжёлые операции идут в threading.Thread,
а события складываются в очередь, которую фронтенд опрашивает.
"""

import os, threading, time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from core import storage
from core.ai_state import (
    clear_caches, get_learned, get_mods_cache, get_placeable_memory, get_pro_data,
    get_selected, persist, remember_brand, set_pro_data, set_selected,
)
from core.models import BalancerConfig, ItemSpec, ScanStats, ScanTarget, SCAN_TARGET_LABELS
from core.parser import process_mod, recalc_specs
from core.pricing import (
    apply_item_multipliers, calc_placeable_price, calc_vehicle_price, clean_round,
    field_price, motor_price_for_delta,
)

EVENTS: "list[tuple]" = []
_EVENTS_LOCK = threading.Lock()


def emit(kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
    with _EVENTS_LOCK:
        EVENTS.append((kind, payload or {}))
        if len(EVENTS) > 4000:
            del EVENTS[:2000]


def drain_events() -> List[Dict[str, Any]]:
    with _EVENTS_LOCK:
        if not EVENTS:
            return []
        out = [{"type": k, "data": v} for k, v in EVENTS]
        EVENTS.clear()
        return out


class BalancerService:
    def __init__(self) -> None:
        self.specs: List[ItemSpec] = []
        self.raw_cache: Dict[str, Dict[str, Any]] = {}
        self.overrides: Dict[str, int] = {}
        self.cfg = BalancerConfig()
        self.stats = ScanStats()
        self.busy = False
        self.last_error = ""
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ── Конфигурация ──
    def load_settings(self) -> BalancerConfig:
        data = storage.load_json(storage.SETTINGS_FILE, {})
        tgt_name = str(data.get("scan_target", "ALL")).upper()
        tgt = getattr(ScanTarget, tgt_name, ScanTarget.ALL)
        self.cfg = BalancerConfig(
            use_additional_currencies=bool(data.get("use_additional_currencies", True)),
            exchange_rate=max(1.0, float(data.get("exchange_rate", 100.0))),
            country_multipliers={str(k): float(v) for k, v in
                                 (data.get("country_multipliers") or {}).items()},
            k_placeable=max(0.05, float(data.get("k_placeable", 1.0))),
            k_field=max(0.05, float(data.get("k_field", 1.0))),
            k_retro=min(1.0, max(0.0, float(data.get("k_retro", 0.65)))),
            retro_wear=min(1.0, max(0.0, float(data.get("retro_wear", 0.15)))),
            global_difficulty_scale=max(0.1, float(data.get("global_difficulty_scale", 1.0))),
            create_backups=bool(data.get("create_backups", True)),
            use_local_ai=bool(data.get("use_local_ai", True)),
            ai_model_name=str(data.get("ai_model_name", "phi3")),
            scan_target=tgt,
            adjust_field_prices=bool(data.get("adjust_field_prices", False)),
            field_max_distance=max(0.1, float(data.get("field_max_distance", 3.0))),
            field_distance_spread=min(1.0, max(0.0, float(data.get("field_distance_spread", 0.45)))),
            shop_coordinates={k: (float(v[0]), float(v[1])) for k, v in
                              (data.get("shop_coordinates") or {}).items()
                              if isinstance(v, (list, tuple)) and len(v) == 2},
            selected_countries=list(get_selected()),
            mods_dir=str(data.get("mods_dir", self.default_mods_dir())),
        )
        return self.cfg

    def save_settings(self) -> None:
        c = self.cfg
        storage.save_json(storage.SETTINGS_FILE, {
            "use_additional_currencies": c.use_additional_currencies,
            "exchange_rate": c.exchange_rate,
            "country_multipliers": c.country_multipliers,
            "k_placeable": c.k_placeable, "k_field": c.k_field,
            "k_retro": c.k_retro, "retro_wear": c.retro_wear,
            "global_difficulty_scale": c.global_difficulty_scale,
            "create_backups": c.create_backups, "use_local_ai": c.use_local_ai,
            "ai_model_name": c.ai_model_name, "scan_target": c.scan_target.name,
            "adjust_field_prices": c.adjust_field_prices,
            "field_max_distance": c.field_max_distance,
            "field_distance_spread": c.field_distance_spread,
            "shop_coordinates": {k: list(v) for k, v in c.shop_coordinates.items()},
            "mods_dir": c.mods_dir,
        })
        persist()

    @staticmethod
    def default_mods_dir() -> str:
        base = os.path.expandvars(r"%USERPROFILE%\Documents\My Games\FarmingSimulator25\mods")
        if os.path.isdir(base):
            return base
        return os.path.expandvars(r"%USERPROFILE%\Documents\My Games\FarmingSimulator25")

    def config_payload(self) -> Dict[str, Any]:
        c = self.cfg
        return {
            "use_additional_currencies": c.use_additional_currencies,
            "exchange_rate": c.exchange_rate,
            "country_multipliers": c.country_multipliers,
            "k_placeable": c.k_placeable, "k_field": c.k_field,
            "k_retro": c.k_retro, "retro_wear": c.retro_wear,
            "global_difficulty_scale": c.global_difficulty_scale,
            "create_backups": c.create_backups, "use_local_ai": c.use_local_ai,
            "ai_model_name": c.ai_model_name, "scan_target": c.scan_target.name,
            "scan_target_label": SCAN_TARGET_LABELS.get(c.scan_target, "Всё"),
            "adjust_field_prices": c.adjust_field_prices,
            "field_max_distance": c.field_max_distance,
            "field_distance_spread": c.field_distance_spread,
            "shop_coordinates": {k: list(v) for k, v in c.shop_coordinates.items()},
            "selected_countries": list(c.selected_countries or get_selected()),
            "mods_dir": c.mods_dir,
            "busy": self.busy,
            "last_error": self.last_error,
            "items": len(self.specs),
            "stats": self.stats.__dict__,
        }

    def update_config(self, patch: Dict[str, Any]) -> None:
        """Применяет патч из фронтенда к BalancerConfig и сохраняет."""
        c = self.cfg
        FLOAT_FIELDS = ("exchange_rate", "k_placeable", "k_field", "k_retro",
                        "retro_wear", "global_difficulty_scale",
                        "field_max_distance", "field_distance_spread")
        BOOL_FIELDS = ("use_additional_currencies", "create_backups",
                       "use_local_ai", "adjust_field_prices")
        for k, v in (patch or {}).items():
            if k in FLOAT_FIELDS:
                try:
                    setattr(c, k, max(0.0, float(v)))
                except (TypeError, ValueError):
                    pass
            elif k in BOOL_FIELDS:
                setattr(c, k, bool(v))
            elif k == "ai_model_name" and isinstance(v, str) and v.strip():
                c.ai_model_name = v.strip()
            elif k == "mods_dir" and isinstance(v, str) and v.strip():
                c.mods_dir = v.strip()
            elif k == "scan_target" and isinstance(v, str):
                try:
                    c.scan_target = ScanTarget[v.upper()]
                except KeyError:
                    pass
            elif k in ("shop_x", "shop_z"):
                try:
                    cur = [float(x) for x in c.shop_coordinates.get("shop", (0.0, 0.0))]
                    while len(cur) < 2:
                        cur.append(0.0)
                    cur[0 if k == "shop_x" else 1] = float(v)
                    c.shop_coordinates["shop"] = (cur[0], cur[1])
                except (TypeError, ValueError):
                    pass
            elif k == "country_multipliers" and isinstance(v, dict):
                out = {}
                for cn, mv in v.items():
                    try:
                        out[str(cn)] = float(mv)
                    except (TypeError, ValueError):
                        pass
                c.country_multipliers = out
        self.save_settings()

    def pro_payload(self) -> Dict[str, Any]:
        pro = get_pro_data()
        return {
            "custom_prompt": pro.get("custom_prompt", ""),
            "country_brands": {k: list(v) for k, v in (pro.get("country_brands") or {}).items()},
            "default_prompt_default": _default_prompt(),
        }

    # ── Сканирование ──
    def start_scan(self, apply: bool) -> Dict[str, Any]:
        if self.busy:
            return {"ok": False, "error": "Уже выполняется операция"}
        mods_dir = self.cfg.mods_dir
        if not mods_dir or not os.path.isdir(mods_dir):
            return {"ok": False, "error": f"Папка mods не найдена: {mods_dir}"}
        self.busy = True
        self._stop.clear()
        self.last_error = ""
        threading.Thread(target=self._scan_worker, args=(mods_dir, apply),
                         daemon=True).start()
        return {"ok": True, "apply": apply}

    def _scan_worker(self, mods_dir: str, apply: bool) -> None:
        backup_dir = os.path.join(mods_dir, "_backup_original_mods")
        try:
            items = sorted(f for f in os.listdir(mods_dir)
                           if not f.startswith("_backup") and (
                               f.lower().endswith(".zip") or
                               os.path.isdir(os.path.join(mods_dir, f))))
        except Exception as e:
            self.busy = False
            emit("error", {"message": f"Не удалось прочитать папку: {e}"})
            return

        total = max(1, len(items))
        found = 0
        counts: Dict[str, int] = defaultdict(int)
        uncertain: List[ItemSpec] = []
        with self._lock:
            self.specs = []
            self.raw_cache = {}
        t0 = time.time()

        emit("scan_start", {"total": total, "apply": apply})

        for idx, item in enumerate(items, 1):
            if self._stop.is_set():
                break
            path = os.path.join(mods_dir, item)
            emit("progress", {"current": idx, "total": total, "item": item})
            try:
                specs = process_mod(path, self.cfg, apply, backup_dir,
                                    self.overrides, self._stop)
            except Exception as e:
                emit("log", {"message": f"⚠ {item}: {e}"})
                continue

            for s in specs:
                found += 1
                counts[s.item_type] += 1
                if s.is_retro:
                    counts["retro"] += 1
                if s.needs_review:
                    uncertain.append(s)
                with self._lock:
                    self.specs.append(s)
                    self.raw_cache[s.unique_key] = _raw_of(s)
                emit("item", s.to_dict())

        self.stats = ScanStats(
            vehicles=counts.get("vehicle", 0), placeables=counts.get("placeable", 0),
            fields=counts.get("field", 0), retro=counts.get("retro", 0),
            review=len(uncertain), applied=found if apply else 0,
            elapsed=round(time.time() - t0, 1))
        self.busy = False
        persist()
        self.save_settings()
        emit("scan_done", {
            "found": found, "apply": apply, "stats": self.stats.__dict__,
            "aborted": self._stop.is_set(),
            "uncertain": [s.to_dict() for s in uncertain[:40]],
        })

    def stop(self) -> None:
        self._stop.set()
        emit("log", {"message": "⏹ Остановка запрошена…"})

    # ── Ручное обновление цен (без сканирования) ──
    def recalculate(self) -> Dict[str, Any]:
        if self.busy:
            return {"ok": False, "error": "Сканирование выполняется — дождитесь"}
        if not self.specs:
            return {"ok": False, "error": "Нет данных: сначала выполните сканирование"}
        self.busy = True
        threading.Thread(target=self._recalc_worker, daemon=True).start()
        return {"ok": True}

    def _recalc_worker(self) -> None:
        t0 = time.time()
        try:
            with self._lock:
                updated = recalc_specs(self.specs, self.cfg, self.overrides, self.raw_cache)
                self.specs = updated
            for s in updated:
                emit("item", s.to_dict())
            self.stats.elapsed = round(time.time() - t0, 1)
            emit("recalc_done", {"items": len(updated),
                                 "elapsed": self.stats.elapsed,
                                 "stats": self.stats.__dict__})
        except Exception as e:
            self.last_error = str(e)
            emit("error", {"message": f"Пересчёт не удался: {e}"})
        finally:
            self.busy = False

    # ── Применение результатов к уже отсканированным данным ──
    def apply_results(self) -> Dict[str, Any]:
        if self.busy:
            return {"ok": False, "error": "Занято"}
        if not self.specs:
            return {"ok": False, "error": "Нет данных для применения"}
        self.busy = True
        threading.Thread(target=self._apply_worker, daemon=True).start()
        return {"ok": True}

    def _apply_worker(self) -> None:
        mods_dir = self.cfg.mods_dir
        backup_dir = os.path.join(mods_dir, "_backup_original_mods")
        done = 0
        try:
            for s in list(self.specs):
                if self._stop.is_set():
                    break
                mod_path = os.path.join(mods_dir, s.mod_name)
                overrides = {**self.overrides, s.unique_key: int(s.new_price)}
                cfg = self.cfg
                try:
                    res = process_mod(mod_path, cfg, True, backup_dir, overrides, self._stop)
                    done += len(res)
                except Exception as e:
                    emit("log", {"message": f"⚠ {s.mod_name}: {e}"})
            emit("applied", {"count": done, "aborted": self._stop.is_set()})
        except Exception as e:
            self.last_error = str(e)
            emit("error", {"message": f"Применение не удалось: {e}"})
        finally:
            self.busy = False

    # ── Правки из таблицы ──
    def _raw(self, s: ItemSpec) -> Dict[str, Any]:
        c = self.raw_cache.get(s.unique_key)
        if c:
            return c
        return {"kind": s.item_type, "category": s.category, "hp": s.hp,
                "spd": s.max_speed, "cap": s.capacity, "ww": s.working_width,
                "nhp": s.needed_hp, "slots": s.slots,
                "prod": s.production_cost, "area": s.field_area}

    def reprice_item(self, s: ItemSpec) -> None:
        """Пересчёт одной позиции по текущему cfg (тот же путь, что и скан)."""
        if s.item_type == "field":
            self._recalc_field(s)
            return
        c = self._raw(s)
        xm = 1.0 if self.cfg.use_additional_currencies else self.cfg.exchange_rate
        dm = self.cfg.exchange_rate if self.cfg.use_additional_currencies else 1.0
        cat = c.get("category") or s.category
        if s.item_type == "placeable":
            base_eur = calc_placeable_price(cat, s.title, s.xml_rel_path,
                                           c.get("cap", 0.0), c.get("slots", 0),
                                           c.get("prod", 0.0), self.cfg.k_placeable,
                                           self.cfg.global_difficulty_scale)
        else:
            base_eur = calc_vehicle_price(cat, c.get("hp", 0.0), c.get("spd", 0.0),
                                          c.get("cap", 0.0), c.get("ww", 0.0),
                                          c.get("nhp", 0.0), 1.0,
                                          self.cfg.global_difficulty_scale)
        k_country = (self.cfg.multiplier_for(s.country)
                     if s.country in _known() else 1.0)
        priced, k_country, k_retro = apply_item_multipliers(
            base_eur, k_country, s.is_retro, self.cfg)
        s.base_price = clean_round(base_eur * xm)
        s.country_mult, s.retro_mult = k_country, k_retro
        s.wear_mult = 1.0 + float(self.cfg.retro_wear) if s.is_retro else 1.0

        if s.unique_key in self.overrides:
            s.new_price = int(self.overrides[s.unique_key])
        else:
            s.new_price = clean_round(priced * xm)
        s.new_price_rub = clean_round(priced * dm) if dm else s.new_price

        if s.item_type == "vehicle" and s.motors:
            base_hp = c.get("hp", s.hp)
            cnt = 0
            s.motor_prices = []
            for m in s.motors:
                if m.index == 0:
                    m.price_delta = 0
                else:
                    m.price_delta = motor_price_for_delta(
                        base_eur, max(0.0, m.hp - base_hp), k_country * k_retro,
                        xm, s.is_retro, self.cfg)
                    cnt += 1
                s.motor_prices.append({"index": m.index, "label": m.label,
                                       "hp": m.hp, "speed": m.max_speed,
                                       "delta": m.price_delta,
                                       "total": clean_round(s.new_price + m.price_delta)})
            s.configs_updated = cnt

    def set_country(self, key: str, country: str) -> Dict[str, Any]:
        with self._lock:
            for s in self.specs:
                if s.unique_key != key:
                    continue
                from core.countries import country_info
                info = country_info(country)
                s.country = country
                s.country_flag = str(info["flag"])
                s.needs_review = False
                s.ai_reason = "Вручную"
                self.reprice_item(s)
                remember_brand(s.brand, country, False)
                persist()
                return {"ok": True, "item": s.to_dict()}
        return {"ok": False, "error": "Элемент не найден"}

    def set_retro(self, key: str, is_retro: bool) -> Dict[str, Any]:
        with self._lock:
            for s in self.specs:
                if s.unique_key != key:
                    continue
                s.is_retro = bool(is_retro)
                self.reprice_item(s)
                # Ретро не пишем в память брендов: у одной марки бывают
                # и ретро-, и современные модели.
                persist()
                return {"ok": True, "item": s.to_dict()}
        return {"ok": False, "error": "Элемент не найден"}

    def set_price(self, key: str, price: int) -> Dict[str, Any]:
        with self._lock:
            for s in self.specs:
                if s.unique_key != key:
                    continue
                p = max(50, int(price))
                self.overrides[key] = p
                s.manual_price = p
                s.new_price = p
                s.new_price_rub = clean_round_rub(p, self.cfg)
                return {"ok": True, "item": s.to_dict()}
        return {"ok": False, "error": "Элемент не найден"}

    def set_motor(self, key: str, index: int, hp: float, price_delta: int) -> Dict[str, Any]:
        with self._lock:
            for s in self.specs:
                if s.unique_key != key:
                    continue
                for m in s.motors:
                    if m.index != int(index):
                        continue
                    m.hp = max(0.0, float(hp))
                    m.price_delta = max(0, int(price_delta))
                    self.raw_cache.setdefault(key, {})["hp"] = (
                        m.hp if m.index == 0 else self.raw_cache.get(key, {}).get("hp", s.hp))
                    s.motor_prices = [
                        {"index": mm.index, "label": mm.label, "hp": mm.hp,
                         "speed": mm.max_speed, "delta": mm.price_delta,
                         "total": clean_round(s.new_price + mm.price_delta)}
                        for mm in s.motors]
                    return {"ok": True, "item": s.to_dict()}
        return {"ok": False, "error": "Комплектация не найдена"}

    def patch_field(self, key: str, area: Optional[float] = None,
                    distance: Optional[float] = None) -> Dict[str, Any]:
        """Ручной ввод га/дистанции для поля. distance < 0 = неизвестна."""
        with self._lock:
            for s in self.specs:
                if s.unique_key != key or s.item_type != "field":
                    continue
                if area is not None:
                    try:
                        a = float(area)
                    except (TypeError, ValueError):
                        return {"ok": False, "error": "Площадь должна быть числом"}
                    if a < 0 or a > 5000:
                        return {"ok": False, "error": "Площадь вне диапазона 0..5000 га"}
                    s.field_area = a
                    s.field_manual = True
                if distance is not None:
                    try:
                        d = float(distance)
                    except (TypeError, ValueError):
                        return {"ok": False, "error": "Дистанция должна быть числом"}
                    s.field_distance = -1.0 if d < 0 else min(50.0, max(0.0, d))
                    s.field_manual = True
                ok_area = s.field_area > 0
                ok_dist = (not self.cfg.adjust_field_prices) or s.field_distance >= 0
                if ok_area and ok_dist:
                    s.needs_review = False
                    s.ai_reason = "Поле (вручную)"
                self._recalc_field(s)
                return {"ok": True, "item": s.to_dict()}
        return {"ok": False, "error": "Поле не найдено"}

    def _recalc_field(self, s: ItemSpec) -> None:
        xm = 1.0 if self.cfg.use_additional_currencies else self.cfg.exchange_rate
        dist = None if s.field_distance < 0 else s.field_distance
        base = field_price(s.field_area if s.field_area > 0 else 0.0, dist, self.cfg)
        s.base_price = clean_round(base * xm)
        if s.unique_key not in self.overrides:
            s.new_price = s.base_price
        s.new_price_rub = clean_round(base * self.cfg.exchange_rate)

    def update_pro(self, custom_prompt: str, country_brands: Dict[str, List[str]]) -> Dict[str, Any]:
        pro = get_pro_data()
        pro["custom_prompt"] = custom_prompt or _default_prompt()
        pro["country_brands"] = {k: [str(b).strip().lower() for b in v if str(b).strip()]
                                 for k, v in (country_brands or {}).items()}
        set_pro_data(pro)
        persist()
        return {"ok": True}

    def update_countries(self, selected: List[str],
                         multipliers: Dict[str, float]) -> Dict[str, Any]:
        clean = [c for c in selected if c in _known()]
        if not clean:
            return {"ok": False, "error": "Выберите хотя бы одну страну"}
        set_selected(clean)
        self.cfg.selected_countries = clean
        self.cfg.country_multipliers = {str(k): float(v) for k, v in (multipliers or {}).items()}
        self.save_settings()
        return {"ok": True, "selected": clean}

    def clear_memory(self) -> Dict[str, Any]:
        clear_caches()
        persist()
        return {"ok": True}

    def items_payload(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self.specs]


def clean_round_rub(price_xml: int, cfg: BalancerConfig) -> int:
    xm = 1.0 if cfg.use_additional_currencies else cfg.exchange_rate
    if xm <= 0:
        xm = 1.0
    return clean_round(price_xml / xm * cfg.exchange_rate)


def _raw_of(s: ItemSpec) -> Dict[str, Any]:
    if s.item_type == "vehicle":
        return {"kind": "vehicle", "category": s.category, "hp": s.hp, "spd": s.max_speed,
                "cap": s.capacity, "ww": s.working_width, "nhp": s.needed_hp}
    if s.item_type == "placeable":
        return {"kind": "placeable", "category": s.category, "cap": s.capacity,
                "slots": s.slots, "prod": s.production_cost}
    return {"kind": "field", "area": s.field_area}


def _default_prompt() -> str:
    from core.ai import DEFAULT_AI_PROMPT
    return DEFAULT_AI_PROMPT


def _known() -> set:
    from core.countries import ALL_COUNTRIES
    return set(ALL_COUNTRIES.keys())
