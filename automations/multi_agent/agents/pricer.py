"""Агент расчёта стоимости заказа."""
from automations.multi_agent.registry import registry


@registry.register(
    name="pricer",
    description="Рассчитывает стоимость заказа по материалу, объёму и срокам",
    tags=["pricing"],
)
async def pricer_agent(task: dict) -> dict:
    from automations.b2b_leads.app.services.pricing import calculate_price

    # Берём либо прямые данные, либо результат analyzer
    analysis = task.get("analyzer_result") or task
    result = calculate_price(analysis)

    if result is None:
        return {"error": "Недостаточно данных для расчёта", "needs": ["product", "volume"]}
    return result
