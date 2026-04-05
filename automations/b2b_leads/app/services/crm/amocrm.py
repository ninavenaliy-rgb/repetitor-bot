import os
import logging
import httpx
from app.services.crm.base import BaseCRM

logger = logging.getLogger(__name__)


class AmoCRM(BaseCRM):
    name = "amocrm"

    def __init__(self):
        self.domain = os.getenv("AMOCRM_DOMAIN", "")  # yourcompany.amocrm.ru
        self.token = os.getenv("AMOCRM_TOKEN", "")
        self.pipeline_id = int(os.getenv("AMOCRM_PIPELINE_ID", "0"))

    @property
    def base_url(self):
        return f"https://{self.domain}/api/v4"

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def create_lead(self, data: dict) -> str:
        analysis = data.get("analysis", {})
        price = data.get("price")

        payload = [{
            "name": f"Заявка от {data['name']} [{data['source']}]",
            "price": int(price["total"]) if price else 0,
            "pipeline_id": self.pipeline_id,
            "_embedded": {
                "contacts": [{
                    "name": data["name"],
                    "custom_fields_values": [
                        {"field_code": "PHONE", "values": [{"value": data["phone"]}]},
                    ]
                }]
            },
            "custom_fields_values": [
                {"field_id": 1, "values": [{"value": analysis.get("summary", data["message"])}]},
            ]
        }]

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/leads/complex",
                    headers=self.headers,
                    json=payload,
                )
                result = resp.json()
                lead_id = str(result[0].get("id", "unknown"))
                logger.info(f"amoCRM lead created: {lead_id}")
                return lead_id
        except Exception as e:
            logger.error(f"amoCRM create_lead failed: {e}")
            return "error"

    async def update_status(self, lead_id: str, status: str) -> bool:
        status_map = {"new": 142, "won": 142, "lost": 143}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.patch(
                    f"{self.base_url}/leads/{lead_id}",
                    headers=self.headers,
                    json={"status_id": status_map.get(status, 142)},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"amoCRM update_status failed: {e}")
            return False

    async def assign_manager(self, lead_id: str, priority: str) -> bool:
        manager_id = int(os.getenv(f"AMOCRM_MANAGER_{priority.upper()}", os.getenv("AMOCRM_DEFAULT_MANAGER", "0")))
        if not manager_id:
            return True
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.patch(
                    f"{self.base_url}/leads/{lead_id}",
                    headers=self.headers,
                    json={"responsible_user_id": manager_id},
                )
                return True
        except Exception as e:
            logger.error(f"amoCRM assign_manager failed: {e}")
            return False
