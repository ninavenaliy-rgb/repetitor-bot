import os
import logging
import httpx
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class TelegramMessenger(BaseMessenger):
    name = "telegram"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    async def send_message(self, phone: str, text: str) -> bool:
        # phone здесь используется как chat_id для Telegram
        if not self.token:
            logger.warning("Telegram not configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": phone, "text": text, "parse_mode": "HTML"},
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def is_available(self) -> bool:
        if not self.token:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{self.token}/getMe"
                )
                return resp.status_code == 200
        except Exception:
            return False
