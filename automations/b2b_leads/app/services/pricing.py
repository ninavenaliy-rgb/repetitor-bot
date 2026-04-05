import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Базовые ставки по материалам (руб/кг или руб/ед)
MATERIAL_RATES = {
    "сталь": 85,
    "нержавейка": 210,
    "алюминий": 180,
    "пластик": 120,
    "дерево": 60,
    "default": 100,
}

URGENCY_MULTIPLIERS = {
    "срочно": 1.4,
    "быстро": 1.25,
    "стандарт": 1.0,
}

BASE_MARGIN = 0.25  # 25% маржа


def calculate_price(analysis: dict) -> Optional[dict]:
    try:
        material = _extract_material(analysis.get("material", ""))
        volume = _parse_volume(analysis.get("volume", ""))
        urgency = _detect_urgency(analysis.get("deadline", ""))

        if volume is None:
            return None

        material_cost = MATERIAL_RATES.get(material, MATERIAL_RATES["default"]) * volume
        labor_cost = material_cost * 0.35
        urgency_multiplier = URGENCY_MULTIPLIERS.get(urgency, 1.0)

        subtotal = (material_cost + labor_cost) * urgency_multiplier
        total = subtotal * (1 + BASE_MARGIN)

        return {
            "material_cost": round(material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "urgency_multiplier": urgency_multiplier,
            "margin_pct": BASE_MARGIN * 100,
            "total": round(total, 2),
            "currency": "RUB",
            "note": "Предварительный расчёт. Окончательная цена после уточнения ТЗ.",
        }

    except Exception as e:
        logger.warning(f"Pricing failed: {e}")
        return None


def _extract_material(raw: str) -> str:
    raw = raw.lower() if raw else ""
    for key in MATERIAL_RATES:
        if key in raw:
            return key
    return "default"


def _parse_volume(raw: str) -> Optional[float]:
    if not raw:
        return None
    import re
    match = re.search(r"(\d+[\.,]?\d*)", raw)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _detect_urgency(deadline: str) -> str:
    if not deadline:
        return "стандарт"
    deadline = deadline.lower()
    if "срочно" in deadline or "1-3" in deadline or "завтра" in deadline:
        return "срочно"
    if "быстро" in deadline or "неделя" in deadline:
        return "быстро"
    return "стандарт"
