import logging
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class MaxMessenger(BaseMessenger):
    """
    Адаптер для MAX (мессенджер VK/Mail.ru).
    Заглушка — подключается через официальный Bot API когда будет доступен.
    """
    name = "max"

    async def send_message(self, phone: str, text: str) -> bool:
        logger.info(f"[MAX stub] Would send to {phone}: {text[:50]}...")
        # TODO: подключить официальный MAX Bot API
        return False

    async def is_available(self) -> bool:
        return False
