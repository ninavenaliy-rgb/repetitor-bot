import logging
import uuid
from app.services.crm.base import BaseCRM

logger = logging.getLogger(__name__)

# Внутренняя CRM — fallback если нет Bitrix/amoCRM
_leads_store: dict = {}


class InternalCRM(BaseCRM):
    name = "internal"

    async def create_lead(self, data: dict) -> str:
        lead_id = str(uuid.uuid4())[:8]
        _leads_store[lead_id] = {**data, "status": "new", "manager": None}
        logger.info(f"Internal CRM: lead {lead_id} created")
        return lead_id

    async def update_status(self, lead_id: str, status: str) -> bool:
        if lead_id in _leads_store:
            _leads_store[lead_id]["status"] = status
            return True
        return False

    async def assign_manager(self, lead_id: str, priority: str) -> bool:
        if lead_id in _leads_store:
            _leads_store[lead_id]["manager"] = f"manager_{priority}"
            return True
        return False
