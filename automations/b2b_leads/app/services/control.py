import logging
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

# Хранилище событий (в продакшне — PostgreSQL)
_events: list = []

SLA_MINUTES = {
    "high": 15,
    "medium": 60,
    "low": 240,
}


async def log_event(lead_id: str, event_type: str, data: dict) -> None:
    event = {
        "lead_id": lead_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data,
    }
    _events.append(event)
    logger.info(f"Event logged: {event_type} for lead {lead_id}")

    # Запускаем SLA-монитор для новых лидов
    if event_type == "created":
        priority = data.get("analysis", {}).get("priority", "medium")
        asyncio.create_task(_sla_watchdog(lead_id, priority))


async def log_manager_action(lead_id: str, manager_id: str, action: str) -> None:
    await log_event(lead_id, f"manager_{action}", {"manager_id": manager_id})


async def _sla_watchdog(lead_id: str, priority: str) -> None:
    """Алерт если менеджер не ответил вовремя."""
    sla = SLA_MINUTES.get(priority, 60)
    await asyncio.sleep(sla * 60)

    # Проверяем — был ли ответ менеджера
    manager_responded = any(
        e["lead_id"] == lead_id and e["event_type"].startswith("manager_")
        for e in _events
    )

    if not manager_responded:
        logger.warning(f"⚠️ SLA нарушен! Лид {lead_id} без ответа {sla} минут (приоритет: {priority})")
        # Здесь можно отправить алерт руководителю через messaging router
