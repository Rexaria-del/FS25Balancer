# -*- coding: utf-8 -*-
"""Детект «читерных» (неадекватных) модов.

Режим ДОПОЛНИТЕЛЬНЫЙ и полностью отключаемый (cfg.cheat_detect).
Два источника вердикта:
  1. пороги, которые задал сам пользователь (0 = порог не задан);
  2. ИИ-модель (если включена и служба доступна).
Если порогов нет и ИИ выключен/недоступен — детект молчит (ничего не помечаем).
Такой мод НЕ исключается из пересчёта: он помечается и требует подтверждения.
"""

from typing import Any, Dict, List, Optional, Tuple

from core.i18n import t

# Пороги: (атрибут конфига, тип позиции, проверяемое поле ItemSpec)
_RULES: List[Tuple[str, str, str, str]] = [
    ("cheat_max_hp", "vehicle", "hp", "cheat.hp"),
    ("cheat_max_speed", "vehicle", "max_speed", "cheat.speed"),
    ("cheat_max_width", "vehicle", "working_width", "cheat.width"),
    ("cheat_max_capacity", "vehicle", "capacity", "cheat.capacity"),
    ("cheat_max_needed_hp", "vehicle", "needed_hp", "cheat.need_hp"),
    ("cheat_max_cycles", "placeable", "prod_cycles", "cheat.cycles"),
]


def _fmt(v: float) -> str:
    v = float(v or 0.0)
    return "{:g}".format(v)


def threshold_verdict(item: Dict[str, Any], cfg: Any) -> Tuple[bool, str]:
    """Проверяет позицию по числовым порогам пользователя."""
    lang = getattr(cfg, "ui_lang", "ru")
    itype = str(item.get("item_type", ""))
    for attr, want, field, key in _RULES:
        if itype != want and not (attr == "cheat_max_capacity" and itype == "placeable"):
            continue
        limit = float(getattr(cfg, attr, 0.0) or 0.0)
        if limit <= 0:
            continue
        actual = float(item.get(field, 0.0) or 0.0)
        if actual > limit:
            return True, t(key, lang, _fmt(actual), _fmt(limit))

    ratio = float(getattr(cfg, "cheat_price_ratio", 0.0) or 0.0)
    if ratio >= 1.0:
        old = float(item.get("old_price", 0) or 0)
        new = float(item.get("new_price", 0) or 0)
        if old > 0 and new > 0:
            rel = max(old / new, new / old)
            if rel >= ratio:
                return True, t("cheat.price", lang, "{:,.0f}".format(old), "{:,.0f}".format(new))
    return False, ""


def active_sources(cfg: Any) -> List[str]:
    """Что сейчас вообще способно что-то пометить: 'dict' и/или 'ai'."""
    out: List[str] = []
    if bool(getattr(cfg, "cheat_detect", False)):
        if cfg.cheat_rules_active():
            out.append("dict")
        if bool(getattr(cfg, "cheat_use_ai", True)):
            out.append("ai")
    return out


def evaluate(item: Dict[str, Any], cfg: Any,
             ai_hint: Optional[Tuple[bool, str]] = None) -> Dict[str, Any]:
    """Возвращает {is_cheat, cheat_reason, cheat_by}. Ничего не меняет в позиции."""
    if not bool(getattr(cfg, "cheat_detect", False)):
        return {"is_cheat": False, "cheat_reason": "", "cheat_by": ""}

    lang = getattr(cfg, "ui_lang", "ru")
    hits: List[str] = []
    by: List[str] = []

    if "dict" in active_sources(cfg):
        hit, reason = threshold_verdict(item, cfg)
        if hit:
            hits.append(reason)
            by.append("dict")

    if "ai" in active_sources(cfg) and ai_hint and ai_hint[0]:
        note = (ai_hint[1] or "").strip()
        hits.append(t("cheat.ai", lang, note or t("src.cheat_ai", lang)))
        by.append("ai")

    return {"is_cheat": bool(hits),
            "cheat_reason": "; ".join(h for h in hits if h),
            "cheat_by": "+".join(dict.fromkeys(by))}
