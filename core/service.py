# -*- coding: utf-8 -*-
"""Слой сервиса: оркестрация сканирования/применения в фоновых потоках.

UI не блокируется: все тяжёлые операции идут в threading.Thread,
а события складываются в очередь, которую фронтенд опрашивает.
"""

import os, threading, time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import storage
from core.ai_state import (
    clear_caches, get_learned, get_mods_cache, get_placeable_memory, get_pro_data,
    get_selected, get_spec_patches, persist, remember_brand, set_pro_data, set_selected,
    set_spec_patch,
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
            ac_mod_installed=bool(data.get("ac_mod_installed", False)),
            ac_converter=bool(data.get("ac_converter", True)),
            ac_rate_auto=bool(data.get("ac_rate_auto", True)),
            ac_manual=bool(data.get("ac_manual", False)),
            exchange_rate=min(100000.0, max(1.0, float(data.get("exchange_rate", 112.66) or 112.66))),
            country_multipliers={str(k): float(v) for k, v in
                                 (data.get("country_multipliers") or {}).items()},
            k_placeable=max(0.05, float(data.get("k_placeable", 1.0))),
            k_field=max(0.05, float(data.get("k_field", 1.0))),
            k_retro=min(1.0, max(0.0, float(data.get("k_retro", 0.65)))),
            retro_wear=min(1.0, max(0.0, float(data.get("retro_wear", 0.15)))),
            retro_enabled=bool(data.get("retro_enabled", True)),
            create_backups=bool(data.get("create_backups", True)),
            use_local_ai=bool(data.get("use_local_ai", True)),
            stop_ai_on_close=bool(data.get("stop_ai_on_close", True)),
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
            "ac_mod_installed": c.ac_mod_installed, "ac_converter": c.ac_converter,
            "ac_rate_auto": c.ac_rate_auto, "ac_manual": c.ac_manual,
            "exchange_rate": c.exchange_rate,
            "country_multipliers": c.country_multipliers,
            "k_placeable": c.k_placeable, "k_field": c.k_field,
            "k_retro": c.k_retro, "retro_wear": c.retro_wear,
            "retro_enabled": c.retro_enabled,
            "create_backups": c.create_backups, "use_local_ai": c.use_local_ai,
            "stop_ai_on_close": c.stop_ai_on_close,
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
            "ac_mod_installed": c.ac_mod_installed, "ac_converter": c.ac_converter,
            "ac_rate_auto": c.ac_rate_auto, "ac_manual": c.ac_manual,
            "exchange_rate": c.exchange_rate,
            "write_direct_rubles": c.write_direct_rubles,
            "xml_factor": c.xml_factor,
            "country_multipliers": c.country_multipliers,
            "k_placeable": c.k_placeable, "k_field": c.k_field,
            "k_retro": c.k_retro, "retro_wear": c.retro_wear,
            "retro_enabled": c.retro_enabled,
            "create_backups": c.create_backups, "use_local_ai": c.use_local_ai,
            "stop_ai_on_close": c.stop_ai_on_close,
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
        # границы обязательны: значения приходят из слайдеров и number-полей
        FLOAT_FIELDS = {
            "exchange_rate": (1.0, 100000.0),
            "k_placeable": (0.05, 10.0), "k_field": (0.05, 10.0),
            "k_retro": (0.0, 1.0), "retro_wear": (0.0, 1.0),
            "field_max_distance": (0.1, 20.0), "field_distance_spread": (0.0, 1.0),
        }
        BOOL_FIELDS = ("ac_mod_installed", "ac_converter", "ac_rate_auto", "ac_manual", "create_backups",
                       "use_local_ai", "adjust_field_prices", "retro_enabled",
                       "stop_ai_on_close")
        for k, v in (patch or {}).items():
            if k in FLOAT_FIELDS:
                lo, hi = FLOAT_FIELDS[k]
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                if f != f or f in (float("inf"), float("-inf")):
                    continue
                setattr(c, k, min(hi, max(lo, f)))
            elif k in BOOL_FIELDS:
                setattr(c, k, bool(v))
                if k in ("ac_mod_installed", "ac_converter"):
                    c.ac_manual = True   # больше не спорить с пользователем при автодетекте
            elif k == "ai_model_name" and isinstance(v, str) and v.strip():
                c.ai_model_name = v.strip()
            elif k == "mods_dir" and isinstance(v, str) and v.strip():
                c.mods_dir = v.strip()
                self.detect_currency(apply=True)
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
                c.country_multipliers = self._clean_multipliers(v)
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
        emit("recalc_start", {"total": len(self.specs)})
        threading.Thread(target=self._recalc_worker, daemon=True).start()
        return {"ok": True}

    def _recalc_worker(self) -> None:
        t0 = time.time()
        try:
            with self._lock:
                updated = recalc_specs(self.specs, self.cfg, self.overrides, self.raw_cache)
                self.specs = updated
            n = max(1, len(updated))
            for i, s in enumerate(updated, 1):
                emit("item", s.to_dict())
                if i == n or i % 10 == 0:
                    emit("progress", {"current": i, "total": n, "item": s.title})
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
        emit("applied_start", {"total": len(self.specs)})
        threading.Thread(target=self._apply_worker, daemon=True).start()
        return {"ok": True}

    def _apply_worker(self) -> None:
        mods_dir = self.cfg.mods_dir
        backup_dir = os.path.join(mods_dir, "_backup_original_mods")
        done = 0
        try:
            items = list(self.specs)
            n = max(1, len(items))
            for i, s in enumerate(items, 1):
                if self._stop.is_set():
                    break
                emit("progress", {"current": i, "total": n, "item": s.mod_name})
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
        xm = self.cfg.xml_factor
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
        s.wear_mult = 1.0 + float(self.cfg.retro_wear) if (s.is_retro and self.cfg.retro_enabled) else 1.0

        if s.unique_key in self.overrides:
            s.new_price = int(self.overrides[s.unique_key])
        else:
            s.new_price = clean_round(priced * xm)
        s.new_price_rub = clean_round(self.cfg.rubles(priced))

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

    # ── Ручные правки ТТХ и разбор цены ──
    SPEC_RAW_KEYS = {"hp": "hp", "max_speed": "spd", "capacity": "cap",
                     "working_width": "ww", "needed_hp": "nhp", "production_cost": "prod",
                     "slots": "slots"}

    def _find_spec(self, key: str) -> Optional[ItemSpec]:
        for s in self.specs:
            if s.unique_key == key:
                return s
        return None

    def _base_eur(self, s: ItemSpec, raw: Dict[str, Any]) -> float:
        """Базовая цена (в EUR-семантике алгоритма) по переданным характеристикам."""
        cat = raw.get("category") or s.category or "misc"
        if s.item_type == "placeable":
            return calc_placeable_price(
                cat, s.title, s.xml_rel_path,
                float(raw.get("cap", 0.0) or 0.0), int(raw.get("slots", 0) or 0),
                float(raw.get("prod", 0.0) or 0.0), self.cfg.k_placeable,
                self.cfg.global_difficulty_scale)
        return calc_vehicle_price(
            cat, float(raw.get("hp", 0.0) or 0.0), float(raw.get("spd", 0.0) or 0.0),
            float(raw.get("cap", 0.0) or 0.0), float(raw.get("ww", 0.0) or 0.0),
            float(raw.get("nhp", 0.0) or 0.0), 1.0, self.cfg.global_difficulty_scale)

    @staticmethod
    def _n(v: float) -> str:
        return format(int(round(float(v))), ",").replace(",", " ")

    def breakdown(self, s: ItemSpec, raw: Optional[Dict[str, Any]] = None,
                  base_eur: Optional[float] = None, k_country: Optional[float] = None,
                  k_retro: Optional[float] = None, dist: Optional[float] = None,
                  area: Optional[float] = None) -> Dict[str, Any]:
        """Человеческая расшифровка: из чего складывается итоговая цена позиции."""
        from core.pricing import FIELD_BASE_PRICE_PER_HA, field_price
        cfg = self.cfg
        raw = raw if raw is not None else self._raw(s)
        xm = cfg.xml_factor or 1.0
        lines: List[Dict[str, Any]] = []

        if s.item_type == "field":
            a = s.field_area if (area is None and s.field_area > 0) else (area if area is not None else raw.get("area", 0.0))
            d = dist if dist is not None else (None if s.field_distance < 0 else s.field_distance)
            plain = field_price(float(a or 0.0), None, cfg)
            priced = field_price(float(a or 0.0), d, cfg)
            lines.append({"k": "Площадь поля", "v": ("%g га" % a) if a and a > 0 else "не определена (ручной ввод)"})
            lines.append({"k": "База по площади", "v": "%s € · %.0f € за га, минимум 1500 €" % (self._n(plain / (cfg.k_field or 1.0)), FIELD_BASE_PRICE_PER_HA)})
            if plain > 0 and priced != plain:
                lines.append({"k": "Надбавка за близость к магазину",
                              "v": "×%.2f · дистанция %s км (радиус %.1f км, сила %d%%)" % (
                                  priced / plain, ("?" if d is None else "%g" % d),
                                  cfg.field_max_distance, round(cfg.field_distance_spread * 100))})
            elif cfg.adjust_field_prices and d is None:
                lines.append({"k": "Надбавка за близость", "v": "не применена — нет дистанции", "warn": True})
            lines.append({"k": "Коэф. полей (настройки)", "v": "×%.2f" % cfg.k_field})
        else:
            base_eur = base_eur if base_eur is not None else self._base_eur(s, raw)
            if k_country is None:
                k_country = cfg.multiplier_for(s.country) if s.country in _known() else 1.0
            if k_retro is None:
                k_retro = float(cfg.k_retro) if (s.is_retro and cfg.retro_enabled) else 1.0
            priced = base_eur * k_country * k_retro
            if s.item_type == "placeable":
                lines.append({"k": "Класс объекта", "v": "%s · %s" % (s.category_label or "misc", s.size_label or "размер не определён")})
                lines.append({"k": "Характеристики для расчёта",
                              "v": "%s л · %d мест · производство %s" % (
                                  self._n(raw.get("cap", 0.0)), int(raw.get("slots", 0) or 0),
                                  self._n(raw.get("prod", 0.0)))})
                lines.append({"k": "База по классу и размеру", "v": "%s €" % self._n(base_eur)})
                lines.append({"k": "Коэф. зданий (настройки)", "v": "×%.2f" % cfg.k_placeable})
            else:
                lines.append({"k": "Класс техники", "v": s.category_label or "misc"})
                lines.append({"k": "Характеристики для расчёта",
                              "v": "%s л.с. · %s км/ч · %s л · захват %s м · треб. %s л.с." % (
                                  self._n(raw.get("hp", 0.0)), self._n(raw.get("spd", 0.0)),
                                  self._n(raw.get("cap", 0.0)), ("%g" % float(raw.get("ww", 0.0) or 0.0)),
                                  self._n(raw.get("nhp", 0.0)))})
                lines.append({"k": "База по ТТХ", "v": "%s €" % self._n(base_eur)})
            lines.append({"k": "Коэф. страны «%s»" % s.country, "v": "×%.2f" % k_country})
            if s.is_retro and cfg.retro_enabled:
                lines.append({"k": "Коэф. ретро", "v": "×%.2f" % k_retro})
                lines.append({"k": "Износ ретро (dailyUpkeep)", "v": "×%.2f" % (1.0 + float(cfg.retro_wear))})
            elif s.is_retro:
                lines.append({"k": "Ретро", "v": "помечено, но режим ретро выключен в настройках", "warn": True})

        if s.item_type == "field":
            a = area if area is not None else s.field_area
            d = dist if dist is not None else (None if s.field_distance < 0 else s.field_distance)
            auto_eur = field_price(float(a or 0.0), d, cfg)
        else:
            auto_eur = base_eur * k_country * k_retro  # type: ignore

        auto_xml = clean_round(auto_eur * xm)
        auto_rub = clean_round(cfg.rubles(auto_eur))
        lines.append({"k": "Итог в рублях", "v": "%s ₽" % self._n(auto_rub), "hi": True})
        if s.manual_price:
            lines.append({"k": "Ручная цена (переопределяет расчёт)",
                          "v": "%s · ₽-эквивалент %s" % (self._n(s.manual_price), self._n(clean_round_rub(int(s.manual_price), cfg)))})
        lines.append({"k": "Что ляжет в файл мода",
                      "v": "%s %s" % (self._n(s.manual_price or auto_xml),
                                       "₽ напрямую" if cfg.write_direct_rubles else "€-база · игра сама домножит на %.2f" % cfg.exchange_rate)})
        if s.item_type == "vehicle" and s.motor_prices:
            for m in s.motor_prices:
                lines.append({"k": "Комплектация «%s»" % m.get("label", "?"),
                              "v": "%s л.с. · +%s = %s" % (self._n(m.get("hp", 0)), self._n(m.get("delta", 0)), self._n(m.get("total", 0)))})

        return {
            "lines": lines,
            "base_price": clean_round((auto_eur if s.item_type != "field" else field_price(
                float((area if area is not None else s.field_area) or 0.0), None, cfg)) * xm),
            "auto_price": int(auto_xml),
            "auto_price_rub": int(auto_rub),
            "new_price": int(s.manual_price or auto_xml),
            "price_eur": round(auto_eur, 2),
            "k_country": round(float(k_country) if s.item_type != "field" else float(cfg.k_field), 3),
            "k_retro": round(float(k_retro) if (s.item_type != "field" and k_retro is not None) else 1.0, 3),
        }

    def validate_specs(self, patch: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
        from core.specs import SPEC_FIELDS
        out: Dict[str, float] = {}
        warns: List[str] = []
        extra = {"area": (0.0, 5000.0), "distance": (-1.0, 50.0)}
        for k, v in (patch or {}).items():
            if k in extra:
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                if f == f:
                    out[k] = min(extra[k][1], max(extra[k][0], f))
                continue
            if k == "slots":
                warns.append("«Места» — только информация: количество слотов задаёт структура мода")
                continue
            meta = SPEC_FIELDS.get(k)
            if not meta:
                warns.append("Неизвестное поле: %s" % k)
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                warns.append("%s: нужно число, пропущено" % meta["label"])
                continue
            if f != f or f in (float("inf"), float("-inf")):
                warns.append("%s: некорректное число" % meta["label"])
                continue
            out[k] = min(float(meta["max"]), max(float(meta["min"]), f))
        return out, warns

    def _merged_raw(self, s: ItemSpec, patch: Dict[str, float]) -> Dict[str, Any]:
        raw = dict(self._raw(s))
        for k, v in (patch or {}).items():
            rk = self.SPEC_RAW_KEYS.get(k)
            if rk:
                raw[rk] = float(v)
        return raw

    def preview_specs(self, key: str, patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Предпросмотр без записи: какие цены получат правки ТТХ."""
        with self._lock:
            s = self._find_spec(key)
            if not s:
                return {"ok": False, "error": "Позиция не найдена"}
            clean, warns = self.validate_specs(patch or {})
            if s.item_type == "field":
                raw = self._raw(s)
                area = float(clean["area"]) if "area" in clean else (s.field_area or float(raw.get("area", 0.0)))
                dist = (None if float(clean["distance"]) < 0 else float(clean["distance"])) \
                    if "distance" in clean else (None if s.field_distance < 0 else s.field_distance)
                bd = self.breakdown(s, raw=raw, area=area, dist=dist)
            else:
                raw = self._merged_raw(s, clean)
                base_eur = self._base_eur(s, raw)
                k_country = (self.cfg.multiplier_for(s.country)
                             if s.country in _known() else 1.0)
                k_retro = float(self.cfg.k_retro) if (s.is_retro and self.cfg.retro_enabled) else 1.0
                bd = self.breakdown(s, raw=raw, base_eur=base_eur, k_country=k_country, k_retro=k_retro)
            bd["warnings"] = warns
            bd["patch"] = clean
            bd["item"] = s.to_dict()
            bd["current_price"] = int(s.new_price)
            bd["diff"] = int(bd["auto_price"]) - int(s.manual_price or s.new_price)
            return {"ok": True, **bd}

    def update_specs(self, key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Сохраняет правки ТТХ: патч ляжет в XML при «Применить», цена пересчитывается сразу."""
        with self._lock:
            s = self._find_spec(key)
            if not s:
                return {"ok": False, "error": "Позиция не найдена"}
            if s.item_type == "field":
                return {"ok": False, "error": "Для поля используй площадь и дистанцию"}
            clean, warns = self.validate_specs(patch or {})
            if not clean:
                return {"ok": False, "error": warns and " ".join(warns) or "Нет корректных значений"}
            store = dict(get_spec_patches().get(key, {}))
            store.update(clean)
            set_spec_patch(key, store)
            raw = self.raw_cache.setdefault(key, self._raw(s))
            for k, v in clean.items():
                rk = self.SPEC_RAW_KEYS.get(k)
                if rk:
                    raw[rk] = v
            if "hp" in clean:
                s.hp = clean["hp"]
                if s.motors:
                    delta = clean["hp"] - float(s.motors[0].hp)
                    for m in s.motors:
                        m.hp = max(0.0, float(m.hp) + delta)
            if "max_speed" in clean:
                s.max_speed = clean["max_speed"]
                for m in s.motors:
                    m.max_speed = clean["max_speed"]
            if "capacity" in clean:
                s.capacity = clean["capacity"]
            if "working_width" in clean:
                s.working_width = clean["working_width"]
            if "needed_hp" in clean:
                s.needed_hp = clean["needed_hp"]
            if "production_cost" in clean:
                s.production_cost = clean["production_cost"]
            self.reprice_item(s)
            d = s.to_dict()
            d["spec_patch"] = store
            bd = self.breakdown(s)
            bd["warnings"] = warns
            return {"ok": True, "item": d, "breakdown": bd, "warnings": warns}

    def reset_specs(self, key: str) -> Dict[str, Any]:
        """Сбрасывает ручные правки позиции и берёт ТТХ заново из файла мода."""
        with self._lock:
            s = self._find_spec(key)
            if not s:
                return {"ok": False, "error": "Позиция не найдена"}
            set_spec_patch(key, {})
            mod_path = os.path.join(self.cfg.mods_dir, s.mod_name)
            if not (os.path.exists(mod_path)):
                self.reprice_item(s)
                return {"ok": True, "item": s.to_dict(),
                        "note": "файл мода не найден — верни значения сканированием"}
            import copy
            tmp_cfg = copy.deepcopy(self.cfg)
            tmp_cfg.use_local_ai = False          # сброс не должен дёргать ИИ
            try:
                specs = process_mod(mod_path, tmp_cfg, False, None, self.overrides)
            except Exception as e:
                return {"ok": False, "error": "Не удалось перечитать мод: %s" % e}
            fresh = next((x for x in specs if x.unique_key == key), None)
            if not fresh:
                return {"ok": False, "error": "Позиция не найдена в файле мода"}
            fresh.country, fresh.country_flag = s.country, s.country_flag
            fresh.is_retro = s.is_retro
            fresh.manual_price = s.manual_price
            if s.ai_reason == "Вручную":
                fresh.ai_reason, fresh.needs_review = s.ai_reason, False
            try:
                self.specs[self.specs.index(s)] = fresh
            except ValueError:
                self.specs.append(fresh)
            self.raw_cache[key] = _raw_of(fresh)
            self.reprice_item(fresh)
            d = fresh.to_dict()
            d["spec_patch"] = {}
            return {"ok": True, "item": d, "breakdown": self.breakdown(fresh)}

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
        xm = self.cfg.xml_factor
        dist = None if s.field_distance < 0 else s.field_distance
        area = s.field_area if s.field_area > 0 else 0.0
        base = field_price(area, dist, self.cfg)
        s.base_price = clean_round(field_price(area, None, self.cfg) * xm)
        if s.unique_key not in self.overrides:
            s.new_price = clean_round(base * xm)
        s.new_price_rub = clean_round(self.cfg.rubles(base))

    @staticmethod
    def _clean_multipliers(raw: Dict[str, Any]) -> Dict[str, float]:
        """Только известные страны и числа в диапазоне 0.05..10 (защита от мусора из UI)."""
        known = _known()
        out: Dict[str, float] = {}
        for cn, mv in (raw or {}).items():
            name = str(cn)
            if name not in known:
                continue
            try:
                f = float(mv)
            except (TypeError, ValueError):
                continue
            if f != f or f in (float("inf"), float("-inf")):
                continue
            out[name] = min(10.0, max(0.05, f))
        return out

    def detect_currency(self, apply: bool = True, force: bool = False) -> Dict[str, Any]:
        """Ищет мод Additional Currencies в папке mods и подтягивает его рублёвый курс.

        force=True — явная кнопка пользователя; иначе ручной выбор стран(ы) мода не перетирается.
        """
        from core import currency
        info = currency.detect(self.cfg.mods_dir)
        if apply and (force or not self.cfg.ac_manual):
            self.cfg.ac_mod_installed = bool(info.get("found"))
            if info.get("rate") and self.cfg.ac_rate_auto:
                self.cfg.exchange_rate = float(info["rate"])
            self.save_settings()
        info["applied"] = bool(apply)
        info["manual"] = bool(self.cfg.ac_manual)
        info["write_direct_rubles"] = self.cfg.write_direct_rubles if apply else \
            (not (bool(info.get("found")) and self.cfg.ac_converter))
        return info

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
        merged = dict(self.cfg.country_multipliers or {})
        merged.update(self._clean_multipliers(multipliers or {}))
        # у каждой выбранной страны обязан быть свой коэффициент — вместо
        # прежнего глобального масштаба сложности
        from core.countries import country_info
        for cn in clean:
            merged.setdefault(cn, float(country_info(cn)["k"]))
        self.cfg.country_multipliers = {cn: merged[cn] for cn in clean}
        self.save_settings()
        rescan = self.recalculate() if self.specs else {"ok": False}
        return {"ok": True, "selected": clean, "recalc": bool(rescan.get("ok")),
                "config": self.config_payload()}

    def clear_memory(self) -> Dict[str, Any]:
        clear_caches()
        persist()
        return {"ok": True}

    def items_payload(self) -> List[Dict[str, Any]]:
        patches = get_spec_patches()
        with self._lock:
            out = []
            for s in self.specs:
                d = s.to_dict()
                d["spec_patch"] = patches.get(s.unique_key, {})
                out.append(d)
            return out


def clean_round_rub(price_xml: int, cfg: BalancerConfig) -> int:
    """Рубли из числа, лежашего в XML (там либо уже ₽, либо EUR-база)."""
    xm = cfg.xml_factor or 1.0
    return clean_round(cfg.rubles(price_xml / xm))


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
