import logging
from datetime import date
from collections import defaultdict

logger = logging.getLogger(__name__)

# В продакшне данные идут в PostgreSQL, здесь — in-memory для демо
_metrics: dict = defaultdict(lambda: defaultdict(int))


async def track_lead(source: str, priority: str) -> None:
    today = str(date.today())
    _metrics[today]["total"] += 1
    _metrics[today][f"source_{source}"] += 1
    _metrics[today][f"priority_{priority}"] += 1

    if priority == "high":
        _metrics[today]["hot_leads"] += 1


async def track_conversion(source: str) -> None:
    today = str(date.today())
    _metrics[today]["converted"] += 1
    _metrics[today][f"converted_{source}"] += 1


def get_report(period: str = "today") -> dict:
    today = str(date.today())
    data = dict(_metrics.get(today, {}))

    total = data.get("total", 0)
    converted = data.get("converted", 0)
    conversion_rate = round(converted / total * 100, 1) if total else 0

    return {
        "period": period,
        "total_leads": total,
        "hot_leads": data.get("hot_leads", 0),
        "converted": converted,
        "conversion_rate_pct": conversion_rate,
        "by_source": {
            k.replace("source_", ""): v
            for k, v in data.items() if k.startswith("source_")
        },
        "by_priority": {
            k.replace("priority_", ""): v
            for k, v in data.items() if k.startswith("priority_")
        },
    }
