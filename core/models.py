# -*- coding: utf-8 -*-
"""Модели данных и конфигурация балансировщика."""

from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class ScanTarget(Enum):
    VEHICLES   = auto()
    PLACEABLES = auto()
    FIELDS     = auto()
    ALL        = auto()


SCAN_TARGET_LABELS = {
    ScanTarget.VEHICLES:   "Техника",
    ScanTarget.PLACEABLES: "Здания и объекты",
    ScanTarget.FIELDS:     "Поля",
    ScanTarget.ALL:        "Всё (техника + здания + поля)",
}


@dataclass
class BalancerConfig:
    # Две независимые вещи: стоит ли мод Additional Currencies и включён ли в игре
    # его конвертер. Пишем рубли напрямую, если мода нет ИЛИ конвертер выключен.
    ac_mod_installed: bool = False
    ac_converter: bool = True
    exchange_rate: float = 112.66      # ₽ за 1 €, по умолчанию курс из мода AC
    ac_rate_auto: bool = True          # курс подставлен автодетектом, а не вручную
    ac_manual: bool = False            # пользователь сам трогал переключатель мода
    use_additional_currencies: bool = True   # LEGACY: только для чтения старых настроек
    country_multipliers: Dict[str, float] = field(default_factory=dict)
    k_placeable: float = 1.0
    k_field: float = 1.0
    k_retro: float = 0.65          # коэффициент цены ретро-техники
    retro_wear: float = 0.15       # коэффициент износа ретро (0..1)
    retro_enabled: bool = True     # общий выключатель ретро-механики
    global_difficulty_scale: float = 1.0
    create_backups: bool = True
    use_local_ai: bool = True
    stop_ai_on_close: bool = True     # гасить Ollama и модели при закрытии программы
    ai_model_name: str = "phi3"
    scan_target: ScanTarget = ScanTarget.ALL
    adjust_field_prices: bool = False
    field_max_distance: float = 3.0    # км, за пределами — минимальная цена
    field_distance_spread: float = 0.45  # 0..1 — насколько ближе = дороже
    shop_coordinates: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    selected_countries: List[str] = field(default_factory=list)
    mods_dir: str = ""

    @property
    def write_direct_rubles(self) -> bool:
        """В <price> ложится рублёвая сумма (без мода AC или с выключенным конвертером)."""
        return not (self.ac_mod_installed and self.ac_converter)

    @property
    def xml_factor(self) -> float:
        """Множитель EUR-базы -> число, которое пишем в XML."""
        return self.exchange_rate if self.write_direct_rubles else 1.0

    def rubles(self, eur_value: float) -> float:
        """Рубли для отображения: всегда база в EUR * курс (не зависит от режима записи)."""
        return float(eur_value) * self.exchange_rate

    def multiplier_for(self, country: str) -> float:
        from core.countries import country_info
        return float(self.country_multipliers.get(country, country_info(country)["k"]))


@dataclass
class MotorSpec:
    """Комплектация двигателя (одна из нескольких у машины)."""
    label: str = "Base"
    hp: float = 0.0
    max_speed: float = 0.0
    torque: float = 0.0
    price_delta: int = 0
    index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ItemSpec:
    """Техника, здание или поле."""
    mod_name: str
    xml_rel_path: str
    item_type: str = "vehicle"      # vehicle | placeable | field
    title: str = "Unknown"
    brand: str = "GENERIC"
    category: str = "misc"
    category_label: str = "Прочее"
    country: str = "Россия"
    country_flag: str = "\U0001F1F7\U0001F1FA"
    is_retro: bool = False
    manual_price: Optional[int] = None
    old_price: int = 0
    new_price: int = 0
    new_price_rub: int = 0
    base_price: int = 0
    hp: float = 0.0
    max_speed: float = 0.0
    capacity: float = 0.0
    working_width: float = 0.0
    needed_hp: float = 0.0
    configs_updated: int = 0
    needs_review: bool = False
    brand_mult: float = 1.0
    country_mult: float = 1.0
    retro_mult: float = 1.0
    wear_mult: float = 1.0
    ai_reason: str = "Словари"
    slots: int = 0
    production_cost: float = 0.0
    size_label: str = ""
    motors: List[MotorSpec] = field(default_factory=list)
    motor_prices: List[Dict[str, Any]] = field(default_factory=list)
    field_area: float = 0.0
    field_distance: float = 0.0
    field_coord: Optional[Tuple[float, float]] = None
    field_manual: bool = False
    xml_node_path: str = ""
    spec_fields: List[str] = field(default_factory=list)

    @property
    def unique_key(self) -> str:
        return f"{self.mod_name}::{self.xml_rel_path}"

    @property
    def type_icon(self) -> str:
        return {"vehicle": "\U0001F69C", "placeable": "\U0001F3D7", "field": "\U0001F33E"}.get(
            self.item_type, "\U0001F4E6")

    @property
    def specs_str(self) -> str:
        parts: List[str] = []
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
                parts.append("Ретро")
        elif self.item_type == "field":
            parts.append(f"{self.field_area:g} га" if self.field_area > 0 else "га ?")
            parts.append("дистанция ?" if self.field_distance < 0
                         else f"{self.field_distance:g} км до магазина")
        else:
            if self.slots > 0:
                parts.append(f"{self.slots} слотов")
            if self.capacity > 0:
                parts.append(f"{int(self.capacity)} л")
            if self.production_cost > 0:
                parts.append(f"произв. {int(self.production_cost)}")
            if self.size_label:
                parts.append(self.size_label)
        return " | ".join(parts) if parts else "—"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["unique_key"] = self.unique_key
        d["type_icon"] = self.type_icon
        d["specs_str"] = self.specs_str
        d["motor_prices"] = list(self.motor_prices)
        return d


@dataclass
class ScanStats:
    vehicles: int = 0
    placeables: int = 0
    fields: int = 0
    retro: int = 0
    review: int = 0
    applied: int = 0
    elapsed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
