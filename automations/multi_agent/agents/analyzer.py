"""Агент анализа входящей заявки."""
from automations.multi_agent.registry import registry


@registry.register(
    name="analyzer",
    description="Анализирует входящую заявку: извлекает продукт, материал, объём, срок, приоритет",
    tags=["input", "ai"],
)
async def analyzer_agent(task: dict) -> dict:
    message = task.get("message", "")
    # Здесь вызываем AI-анализ из b2b_leads
    from automations.b2b_leads.app.agent.analyzer import analyze_lead
    return await analyze_lead(message)
