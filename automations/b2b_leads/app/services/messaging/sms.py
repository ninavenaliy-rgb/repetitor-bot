import os
import logging
import httpx
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class SMSMessenger(BaseMessenger):
    """SMS через sms.ru или любой другой РФ-провайдер."""
    name = "sms"

    def __init__(self):
        self.api_id = os.getenv("SMSRU_API_ID", "")

    async def send_message(self, phone: str, text: str) -> bool:
        if not self.api_id:
            logger.warning("SMS (sms.ru) not configured")
            return False
        try:
            # SMS ограничен 160 символами
            text = text[:160]
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://sms.ru/sms/send",
                    params={
                        "api_id": self.api_id,
                        "to": phone,
                        "msg": text,
                        "json": 1,
                    },
                )
                data = resp.json()
                if data.get("status") == "OK":
                    return True
                logger.error(f"SMS error: {data}")
                return False
        except Exception as e:
            logger.error(f"SMS send failed: {e}")
            return False

    async def is_available(self) -> bool:
        return bool(self.api_id)
