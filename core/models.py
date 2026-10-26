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

# Ключи категорий для мультивыбора «что сканируем»
SCAN_CATEGORY_KEYS = ["vehicle", "placeable", "field"]

# category (из XML) -> подгруппа здания. Подгруппы нужны фильтру и группировке в таблице.
PLACEABLE_SUBGROUPS: Dict[str, str] = {
    "productions": "production", "productionpoints": "production",
    "greenhouses": "production", "beehives": "production",
    "sellingpoints": "selling",
    "silos": "storage", "storages": "storage", "liquidstorages": "storage",
    "animalpens": "animals", "animals": "animals",
    "farmhouses": "farm", "sheds": "farm", "buildings": "farm",
    "decorations": "decor", "fences": "decor", "lights": "decor",
    "placeables": "other", "misc": "other",
}
SUBGROUP_ORDER = ["production", "selling", "storage", "animals", "farm", "decor", "other"]


def subgroup_for(category: str, item_type: str = "placeable") -> str:
    if item_type != "placeable":
        return ""
    return PLACEABLE_SUBGROUPS.get(str(category or "misc").strip().lower(), "other")


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
    ai_model_name: str = "qwen2.5:3b"
    scan_target: ScanTarget = ScanTarget.ALL
    adjust_field_prices: bool = False
    field_max_distance: float = 3.0    # км, за пределами — минимальная цена
    field_distance_spread: float = 0.45  # 0..1 — насколько ближе = дороже
    shop_coordinates: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    selected_countries: List[str] = field(default_factory=list)
    mods_dir: str = ""
    # Язык интерфейса: ru | en. Влияет на подписи категорий, стран, ТТХ и разбора цены.
    ui_lang: str = "ru"
    tour_never: bool = False
    # Мультивыбор категорий для сканирования (заменяет одиночный scan_target).
    scan_targets: List[str] = field(default_factory=lambda: list(SCAN_CATEGORY_KEYS))
    # Детект «читерских» модов: дополнительный режим, по умолчанию выключен.
    cheat_detect: bool = False
    cheat_use_ai: bool = True
    # Пороги: 0 = не задан. Если ни один не задан и ИИ выключен — детект не работает.
    cheat_max_hp: float = 0.0
    cheat_max_speed: float = 0.0
    cheat_max_width: float = 0.0
    cheat_max_capacity: float = 0.0
    cheat_max_needed_hp: float = 0.0
    cheat_max_cycles: float = 0.0
    cheat_price_ratio: float = 0.0

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

    def wants(self, item_type: str) -> bool:
        """Сканируем ли этот тип позиций (с учётом legacy-переключателя scan_target)."""
        keys = [k for k in (self.scan_targets or []) if k in SCAN_CATEGORY_KEYS]
        if not keys:
            t = self.scan_target
            keys = SCAN_CATEGORY_KEYS if t == ScanTarget.ALL else {
                ScanTarget.VEHICLES: ["vehicle"],
                ScanTarget.PLACEABLES: ["placeable"],
                ScanTarget.FIELDS: ["field"],
            }[t]
        return item_type in keys

    def cheat_rules_active(self) -> bool:
        """Задан ли хоть один числовой порог читерства."""
        return any(float(getattr(self, k, 0.0) or 0.0) > 0 for k in (
            "cheat_max_hp", "cheat_max_speed", "cheat_max_width",
            "cheat_max_capacity", "cheat_max_needed_hp", "cheat_max_cycles",
            "cheat_price_ratio"))

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
class ProductionSpec:
    """Один блок <production> у здания: скорость линии, сырьё, выпуск, расходы, склад."""
    index: int = 0
    title: str = ""
    cycles_per_hour: float = 0.0
    input_amount: float = 0.0     # литр/л.с.-екв. сырья за цикл (сумма <input>)
    output_amount: float = 0.0    # выход готовой продукции за цикл (сумма <output>)
    costs_per_active_hour: float = 0.0
    costs_per_active_month: float = 0.0
    storage_capacity: float = 0.0  # <capacity> внутренних складов завода
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def throughput(self) -> float:
        """Что линия выдаёт в час — именно это и определяет её ценность."""
        return max(0.0, self.cycles_per_hour * self.output_amount)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["throughput"] = self.throughput
        return d


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
    price_source: str = ""      # "" | manual | motor — откуда взялась переопределённая цена
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
    # Здания: подгруппа (production/selling/storage/...), линии производства, товары точки продажи
    subgroup: str = ""
    productions: List[ProductionSpec] = field(default_factory=list)
    prod_cycles: float = 0.0
    prod_output: float = 0.0
    prod_input: float = 0.0
    prod_cost_month: float = 0.0
    storage_capacity: float = 0.0
    goods_count: int = 0
    # Подозрение на «читерный» мод
    needs_write: bool = False   # в файле реально что-то меняется (иначе персобираем зип впустую)
    is_cheat: bool = False
    cheat_reason: str = ""
    cheat_by: str = ""            # "dict" | "ai" | "manual"
    # Разбор цены: из чего сложилась итоговая цифра (видно всегда)
    price_chain: List[Dict[str, Any]] = field(default_factory=list)
    ui_lang: str = "ru"            # язык, на котором собраны подписи этой позиции

    @property
    def unique_key(self) -> str:
        return f"{self.mod_name}::{self.xml_rel_path}"

    @property
    def type_icon(self) -> str:
        return {"vehicle": "\U0001F69C", "placeable": "\U0001F3D7", "field": "\U0001F33E"}.get(
            self.item_type, "\U0001F4E6")

    def specs_text(self, lang: Optional[str] = None) -> str:
        """Строка ТТХ для колонки «Хар-ки» — в языке интерфейса."""
        from core.i18n import norm_lang, t
        lg = norm_lang(lang if lang is not None else self.ui_lang)
        parts: List[str] = []
        if self.item_type == "vehicle":
            if self.hp > 0:
                parts.append(t("lbl.hp", lg, int(self.hp)))
            if self.capacity > 0:
                parts.append(t("lbl.cap", lg, int(self.capacity)))
            if self.max_speed > 0:
                parts.append(t("lbl.spd", lg, int(self.max_speed)))
            if self.working_width > 0:
                parts.append(t("lbl.width", lg, "{0:g}".format(self.working_width)))
            if self.is_retro:
                parts.append(t("lbl.retro", lg))
        elif self.item_type == "field":
            parts.append(t("lbl.area", lg, "{0:g}".format(self.field_area))
                         if self.field_area > 0 else t("lbl.area_q", lg))
            parts.append(t("lbl.dist_q", lg) if self.field_distance < 0
                         else t("lbl.dist", lg, "{0:g}".format(self.field_distance)))
        else:
            if self.slots > 0:
                parts.append(t("lbl.slots", lg, self.slots))
            if self.capacity > 0:
                parts.append(t("lbl.cap", lg, int(self.capacity)))
            if self.prod_cycles > 0:
                parts.append(t("lbl.cycles", lg, "{0:g}".format(self.prod_cycles)))
            if self.prod_output > 0:
                parts.append(t("lbl.out", lg, int(self.prod_output)))
            if self.prod_input > 0:
                parts.append(t("lbl.in", lg, int(self.prod_input)))
            if self.storage_capacity > 0:
                parts.append(t("lbl.store", lg, int(self.storage_capacity)))
            if self.goods_count > 0:
                parts.append(t("lbl.goods", lg, self.goods_count))
            if self.production_cost > 0:
                parts.append(t("lbl.upkeep", lg, int(self.production_cost)))
            if self.size_label:
                parts.append(self.size_label)
            if self.is_cheat:
                parts.append(t("lbl.cheat", lg))
        return " | ".join(parts) if parts else "—"

    @property
    def specs_str(self) -> str:
        return self.specs_text(self.ui_lang)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["unique_key"] = self.unique_key
        d["type_icon"] = self.type_icon
        d["specs_str"] = self.specs_text(self.ui_lang)
        d["motor_prices"] = list(self.motor_prices)
        d["productions"] = [p.to_dict() for p in self.productions]
        d["subgroup"] = self.subgroup or ""
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
