import os
import logging
import httpx
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class WhatsAppMessenger(BaseMessenger):
    name = "whatsapp"

    def __init__(self):
        self.api_url = os.getenv("WHATSAPP_API_URL", "")
        self.token = os.getenv("WHATSAPP_TOKEN", "")
        self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")

    async def send_message(self, phone: str, text: str) -> bool:
        if not self.token or not self.phone_id:
            logger.warning("WhatsApp not configured")
            return False
        try:
            phone = phone.lstrip("+").replace(" ", "").replace("-", "")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://graph.facebook.com/v18.0/{self.phone_id}/messages",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "text",
                        "text": {"body": text},
                    },
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False

    async def is_available(self) -> bool:
        return bool(self.token and self.phone_id)
