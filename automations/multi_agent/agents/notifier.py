"""Агент отправки уведомлений через мессенджеры."""
from automations.multi_agent.registry import registry


@registry.register(
    name="notifier",
    description="Отправляет уведомления клиенту или менеджеру через WhatsApp, Telegram, email, SMS",
    tags=["messaging", "output"],
)
async def notifier_agent(task: dict) -> dict:
    from automations.b2b_leads.app.services.messaging.router import send_to_user

    phone = task.get("phone", "")
    channel = task.get("source", "email")
    text = task.get("text") or task.get("message", "Ваша заявка принята")

    success = await send_to_user(channel=channel, phone=phone, text=text)
    return {"sent": success, "channel": channel, "phone": phone}
