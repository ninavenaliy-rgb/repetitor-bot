import os
import logging
import httpx
from app.services.crm.base import BaseCRM

logger = logging.getLogger(__name__)


class BitrixCRM(BaseCRM):
    name = "bitrix24"

    def __init__(self):
        self.webhook_url = os.getenv("BITRIX24_WEBHOOK_URL", "")

    async def create_lead(self, data: dict) -> str:
        analysis = data.get("analysis", {})
        price = data.get("price")

        fields = {
            "TITLE": f"Заявка от {data['name']} [{data['source']}]",
            "NAME": data["name"],
            "PHONE": [{"VALUE": data["phone"], "VALUE_TYPE": "WORK"}],
            "SOURCE_ID": "WEB",
            "COMMENTS": analysis.get("summary", data["message"]),
            "OPPORTUNITY": str(price["total"]) if price else "",
            "CURRENCY_ID": "RUB",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.webhook_url}/crm.lead.add.json",
                    json={"fields": fields},
                )
                result = resp.json()
                lead_id = str(result.get("result", "unknown"))
                logger.info(f"Bitrix24 lead created: {lead_id}")
                return lead_id
        except Exception as e:
            logger.error(f"Bitrix24 create_lead failed: {e}")
            return "error"

    async def update_status(self, lead_id: str, status: str) -> bool:
        status_map = {
            "new": "NEW",
            "in_progress": "IN_PROCESS",
            "won": "WON",
            "lost": "LOSE",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.webhook_url}/crm.lead.update.json",
                    json={"id": lead_id, "fields": {"STATUS_ID": status_map.get(status, "NEW")}},
                )
                return resp.json().get("result") is True
        except Exception as e:
            logger.error(f"Bitrix24 update_status failed: {e}")
            return False

    async def assign_manager(self, lead_id: str, priority: str) -> bool:
        # Назначаем ответственного из ENV (можно расширить логику)
        manager_id = os.getenv(f"BITRIX24_MANAGER_{priority.upper()}", os.getenv("BITRIX24_DEFAULT_MANAGER", "1"))
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.webhook_url}/crm.lead.update.json",
                    json={"id": lead_id, "fields": {"ASSIGNED_BY_ID": manager_id}},
                )
                return True
        except Exception as e:
            logger.error(f"Bitrix24 assign_manager failed: {e}")
            return False
