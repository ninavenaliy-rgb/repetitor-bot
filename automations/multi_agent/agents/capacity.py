"""
Агент загрузки производства.

Логика:
1. Читает очередь заказов (JSON-файл / API производственной системы)
2. Считает занятые мощности на каждый день
3. Находит ближайший свободный слот под новый заказ
4. Возвращает реальную дату начала и срок выполнения
"""

import json
import logging
from pathlib import Path
from datetime import date, timedelta
from automations.multi_agent.registry import registry

logger = logging.getLogger(__name__)

CAPACITY_DB_PATH = Path(__file__).parent.parent / "data" / "capacity.json"

# Производительность по умолчанию (тонн/день на каждый тип работ)
DEFAULT_CAPACITY = {
    "max_tons_per_day": 10,
    "working_days": ["mon", "tue", "wed", "thu", "fri"],
    "orders": [
        # Текущие заказы в очереди
        {"id": "ORD-001", "tons": 15, "start": "2026-04-05", "end": "2026-04-07"},
        {"id": "ORD-002", "tons": 8,  "start": "2026-04-07", "end": "2026-04-08"},
        {"id": "ORD-003", "tons": 20, "start": "2026-04-09", "end": "2026-04-11"},
    ]
}

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _load_capacity() -> dict:
    if CAPACITY_DB_PATH.exists():
        with open(CAPACITY_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    CAPACITY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CAPACITY_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CAPACITY, f, ensure_ascii=False, indent=2)
    return DEFAULT_CAPACITY


def _is_working_day(d: date, working_days: list) -> bool:
    return DAY_NAMES[d.weekday()] in working_days


def _get_busy_days(orders: list) -> set:
    """Возвращает множество дат, когда производство занято."""
    busy = set()
    for order in orders:
        start = date.fromisoformat(order["start"])
        end = date.fromisoformat(order["end"])
        current = start
        while current <= end:
            busy.add(str(current))
            current += timedelta(days=1)
    return busy


def _find_free_slot(start_from: date, duration_days: int, capacity: dict):
    """Найти ближайший свободный слот нужной длины."""
    busy = _get_busy_days(capacity.get("orders", []))
    working_days = capacity.get("working_days", DAY_NAMES[:5])

    current = start_from
    consecutive = 0
    slot_start = None

    for _ in range(120):  # ищем в пределах 120 дней
        if _is_working_day(current, working_days) and str(current) not in busy:
            if slot_start is None:
                slot_start = current
            consecutive += 1
            if consecutive >= duration_days:
                return slot_start, current
        else:
            slot_start = None
            consecutive = 0
        current += timedelta(days=1)

    # Если не нашли — возвращаем через 30 дней
    fallback = start_from + timedelta(days=30)
    return fallback, fallback + timedelta(days=duration_days)


def _estimate_duration(volume_tons: float, max_per_day: float) -> int:
    """Сколько рабочих дней нужно на заказ."""
    if not volume_tons or not max_per_day:
        return 3  # по умолчанию 3 дня
    days = volume_tons / max_per_day
    return max(1, round(days))


@registry.register(
    name="capacity",
    description="Проверяет загрузку производства: когда можно взять заказ, реальный срок выполнения",
    tags=["production", "planning"],
)
async def capacity_agent(task: dict) -> dict:
    analysis = task.get("analyzer_result") or task
    warehouse = task.get("warehouse_result") or {}

    # Объём из задачи
    from automations.multi_agent.agents.warehouse import _parse_quantity
    volume_raw = analysis.get("volume") or task.get("volume", "")
    volume_tons = _parse_quantity(volume_raw) or 5  # 5 тонн по умолчанию

    # Если склада нет — задержка на поставку
    stock_status = warehouse.get("status", "in_stock")
    next_delivery = warehouse.get("next_delivery")

    today = date.today()

    if stock_status in ("shortage", "out_of_stock") and next_delivery:
        # Начинаем не раньше даты поставки
        start_from = date.fromisoformat(next_delivery) + timedelta(days=1)
        delay_reason = f"ожидание поставки материала ({next_delivery})"
    else:
        start_from = today + timedelta(days=1)
        delay_reason = None

    capacity = _load_capacity()
    max_per_day = capacity.get("max_tons_per_day", 10)
    duration_days = _estimate_duration(volume_tons, max_per_day)

    slot_start, slot_end = _find_free_slot(start_from, duration_days, capacity)

    # Итоговый срок с запасом 20%
    total_days = (slot_end - today).days
    deadline = slot_end + timedelta(days=1)  # +1 день на контроль качества

    result = {
        "can_start": str(slot_start),
        "estimated_end": str(slot_end),
        "deadline_for_client": str(deadline),
        "duration_working_days": duration_days,
        "total_calendar_days": total_days,
        "volume_tons": volume_tons,
        "message": (
            f"Производство свободно с {slot_start.strftime('%d.%m.%Y')}. "
            f"Срок выполнения: {duration_days} раб. дней. "
            f"Готовность заказа: {deadline.strftime('%d.%m.%Y')}."
        ),
    }

    if delay_reason:
        result["delay_reason"] = delay_reason

    return result
