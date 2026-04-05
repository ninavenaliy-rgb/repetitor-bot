import os
import logging
import httpx
import random
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class VKMessenger(BaseMessenger):
    name = "vk"

    def __init__(self):
        self.token = os.getenv("VK_TOKEN", "")
        self.group_id = os.getenv("VK_GROUP_ID", "")

    async def send_message(self, phone: str, text: str) -> bool:
        # phone = vk user_id
        if not self.token:
            logger.warning("VK not configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.vk.com/method/messages.send",
                    data={
                        "user_id": phone,
                        "message": text,
                        "random_id": random.randint(0, 2**31),
                        "access_token": self.token,
                        "v": "5.131",
                    },
                )
                data = resp.json()
                if "error" in data:
                    logger.error(f"VK error: {data['error']}")
                    return False
                return True
        except Exception as e:
            logger.error(f"VK send failed: {e}")
            return False

    async def is_available(self) -> bool:
        return bool(self.token)
