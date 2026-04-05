"""
Агент проверки склада.

Логика:
1. Берёт продукт и материал из задачи
2. Ищет совпадение в базе склада (сейчас JSON-файл, легко заменить на 1С/МойСклад/API)
3. Возвращает: есть ли в наличии, сколько, когда следующая поставка
"""

import json
import os
import logging
from pathlib import Path
from automations.multi_agent.registry import registry

logger = logging.getLogger(__name__)

# ─── База склада ──────────────────────────────────────────────────────────────
# В реальности это запрос к 1С, МойСклад, или любому складскому API.
# Сейчас: JSON-файл рядом. Легко заменить — меняешь только _get_stock().

STOCK_DB_PATH = Path(__file__).parent.parent / "data" / "stock.json"

DEFAULT_STOCK = {
    "труба стальная": {"quantity": 25, "unit": "тонн", "next_delivery": "2026-04-10"},
    "труба нержавеющая": {"quantity": 5, "unit": "тонн", "next_delivery": "2026-04-15"},
    "лист стальной": {"quantity": 40, "unit": "тонн", "next_delivery": None},
    "лист алюминиевый": {"quantity": 8, "unit": "тонн", "next_delivery": "2026-04-12"},
    "профиль стальной": {"quantity": 15, "unit": "тонн", "next_delivery": None},
    "арматура": {"quantity": 60, "unit": "тонн", "next_delivery": None},
    "заготовка стальная": {"quantity": 20, "unit": "шт", "next_delivery": "2026-04-08"},
}


def _get_stock() -> dict:
    """Загрузить склад из файла. Если файла нет — создать с дефолтными данными."""
    if STOCK_DB_PATH.exists():
        with open(STOCK_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    # Создаём файл-пример при первом запуске
    STOCK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STOCK_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_STOCK, f, ensure_ascii=False, indent=2)
    return DEFAULT_STOCK


def _find_item(product: str, material: str, stock: dict):
    """Нечёткий поиск позиции на складе по продукту и материалу."""
    product = (product or "").lower()
    material = (material or "").lower()
    query = f"{product} {material}".strip()

    # Прямое совпадение
    for key, value in stock.items():
        if key.lower() == query:
            return key, value

    # Частичное совпадение
    for key, value in stock.items():
        key_lower = key.lower()
        if product and product in key_lower:
            return key, value
        if material and material in key_lower:
            return key, value

    return None, None


@registry.register(
    name="warehouse",
    description="Проверяет наличие материала на складе: есть ли нужный объём, когда следующая поставка",
    tags=["stock", "production"],
)
async def warehouse_agent(task: dict) -> dict:
    # Берём данные из analyzer если они есть, иначе из самой задачи
    analysis = task.get("analyzer_result") or task
    product = analysis.get("product") or task.get("product", "")
    material = analysis.get("material") or task.get("material", "")
    volume_raw = analysis.get("volume") or task.get("volume", "")

    # Парсим нужный объём
    requested_qty = _parse_quantity(volume_raw)

    stock = _get_stock()
    item_name, item_data = _find_item(product, material, stock)

    if not item_data:
        return {
            "found": False,
            "product": f"{product} {material}".strip(),
            "message": "Позиция не найдена на складе. Требуется уточнение у снабженца.",
            "action": "contact_supplier",
        }

    available = item_data["quantity"]
    unit = item_data["unit"]
    next_delivery = item_data.get("next_delivery")

    # Хватает ли материала?
    if requested_qty and available >= requested_qty:
        status = "in_stock"
        message = f"В наличии {available} {unit}. Заказ на {requested_qty} {unit} можно выполнить."
    elif requested_qty and next_delivery:
        status = "partial"
        message = (
            f"В наличии {available} {unit}, нужно {requested_qty} {unit}. "
            f"Следующая поставка: {next_delivery}."
        )
    elif requested_qty:
        status = "shortage"
        message = f"Недостаточно. В наличии {available} {unit}, нужно {requested_qty} {unit}. Поставка не запланирована."
    else:
        status = "in_stock" if available > 0 else "out_of_stock"
        message = f"В наличии {available} {unit}."

    return {
        "found": True,
        "item": item_name,
        "status": status,          # in_stock / partial / shortage / out_of_stock
        "available": available,
        "requested": requested_qty,
        "unit": unit,
        "next_delivery": next_delivery,
        "message": message,
    }


def _parse_quantity(raw: str):
    if not raw:
        return None
    import re
    match = re.search(r"(\d+[\.,]?\d*)", str(raw))
    if match:
        return float(match.group(1).replace(",", "."))
    return None
