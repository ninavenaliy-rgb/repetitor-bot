import logging

logger = logging.getLogger(__name__)

# Пороги для определения крупного B2B заказа
LARGE_ORDER_KEYWORDS = ["тонн", "тн", "партия", "оптом", "серия", "контракт"]
HIGH_PRIORITY_SOURCES = ["avito", "vk", "website"]


async def decide(analysis: dict, lead_data: dict) -> dict:
    priority = _calc_priority(analysis, lead_data)
    can_price = _can_calculate_price(analysis)
    urgent = priority == "high"
    large_b2b = _is_large_b2b(analysis, lead_data)

    result = {
        "priority": priority,
        "can_price": can_price,
        "urgent": urgent,
        "large_b2b": large_b2b,
        "action": _pick_action(analysis, can_price, large_b2b),
    }

    logger.info(f"Decision: {result}")
    return result


def _calc_priority(analysis: dict, lead_data: dict) -> str:
    # Высокий приоритет если AI сказал high
    if analysis.get("priority") == "high":
        return "high"

    # Высокий приоритет если крупный заказ
    if _is_large_b2b(analysis, lead_data):
        return "high"

    # Средний приоритет по умолчанию
    return analysis.get("priority", "medium")


def _can_calculate_price(analysis: dict) -> bool:
    return (
        analysis.get("product") is not None
        and analysis.get("volume") is not None
    )


def _is_large_b2b(analysis: dict, lead_data: dict) -> bool:
    message = lead_data.get("message", "").lower()
    return any(kw in message for kw in LARGE_ORDER_KEYWORDS)


def _pick_action(analysis: dict, can_price: bool, large_b2b: bool) -> str:
    if large_b2b:
        return "escalate_to_manager"
    if can_price:
        return "send_price"
    if analysis.get("needs_clarification"):
        return "clarify"
    return "send_info"
