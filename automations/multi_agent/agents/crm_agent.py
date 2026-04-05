"""Агент записи в CRM."""
from automations.multi_agent.registry import registry


@registry.register(
    name="crm",
    description="Создаёт или обновляет лид в CRM (Bitrix24, amoCRM или внутренней)",
    tags=["crm", "output"],
)
async def crm_agent(task: dict) -> dict:
    from automations.b2b_leads.app.services.crm.factory import get_crm

    crm = get_crm()
    lead_id = await crm.create_lead(task)
    priority = task.get("analyzer_result", {}).get("priority", "medium") if "analyzer_result" in task else "medium"
    await crm.assign_manager(lead_id, priority)

    return {"lead_id": lead_id, "crm": crm.name}
