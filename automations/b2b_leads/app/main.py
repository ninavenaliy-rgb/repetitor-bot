from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from app.database.engine import init_db
from app.agent.analyzer import analyze_lead
from app.agent.decision import decide
from app.services.pricing import calculate_price
from app.services.auto_reply import send_auto_reply
from app.services.control import log_event
from app.services.crm.factory import get_crm
from app.services.messaging.router import send_to_user
from app.analytics.metrics import track_lead
from app.queue.worker import enqueue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="B2B Lead Automation", version="1.0.0")


class WebhookPayload(BaseModel):
    name: str
    phone: str
    message: str
    source: str = "website"  # website/whatsapp/telegram/avito/email/vk/other
    email: Optional[str] = None


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("DB initialized")


@app.post("/webhook")
async def webhook(payload: WebhookPayload, background: BackgroundTasks):
    logger.info(f"New lead from {payload.source}: {payload.name}")
    background.add_task(process_lead, payload.dict())
    return {"status": "accepted"}


async def process_lead(data: dict):
    try:
        # 1. AI анализ
        analysis = await analyze_lead(data["message"])

        # 2. Decision engine
        decision = await decide(analysis, data)

        # 3. Расчёт цены (если хватает данных)
        price = None
        if decision["can_price"]:
            price = calculate_price(analysis)

        # 4. CRM
        crm = get_crm()
        lead_id = await crm.create_lead({**data, "analysis": analysis, "price": price})
        await crm.assign_manager(lead_id, decision["priority"])

        # 5. Уведомление менеджера
        if decision["urgent"]:
            await send_to_user(
                channel=data["source"],
                phone=data["phone"],
                text=f"🔥 СРОЧНО: Новый крупный заказ от {data['name']}\n{analysis['summary']}"
            )

        # 6. Автоответ клиенту
        await send_auto_reply(data, analysis, price)

        # 7. Аналитика
        await track_lead(data["source"], decision["priority"])

        # 8. Логирование
        await log_event(lead_id, "created", data)

    except Exception as e:
        logger.error(f"Error processing lead: {e}", exc_info=True)


@app.get("/health")
async def health():
    return {"status": "ok"}
