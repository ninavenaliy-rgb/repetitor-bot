import logging
from typing import Optional

from app.services.messaging.whatsapp import WhatsAppMessenger
from app.services.messaging.telegram import TelegramMessenger
from app.services.messaging.vk import VKMessenger
from app.services.messaging.email import EmailMessenger
from app.services.messaging.sms import SMSMessenger
from app.services.messaging.max import MaxMessenger

logger = logging.getLogger(__name__)

# Порядок fallback: предпочтительный → резервные
CHANNEL_PRIORITY = {
    "whatsapp": ["whatsapp", "sms", "email"],
    "telegram": ["telegram", "whatsapp", "email"],
    "vk":       ["vk", "email", "sms"],
    "email":    ["email", "sms"],
    "avito":    ["whatsapp", "email", "sms"],
    "website":  ["whatsapp", "email", "sms"],
    "other":    ["email", "sms", "whatsapp"],
}

MESSENGERS = {
    "whatsapp": WhatsAppMessenger(),
    "telegram": TelegramMessenger(),
    "vk": VKMessenger(),
    "email": EmailMessenger(),
    "sms": SMSMessenger(),
    "max": MaxMessenger(),
}


async def send_to_user(channel: str, phone: str, text: str) -> bool:
    """
    Отправляет сообщение через предпочтительный канал.
    Если канал недоступен — пробует fallback по очереди.
    """
    priority = CHANNEL_PRIORITY.get(channel, CHANNEL_PRIORITY["other"])

    for ch_name in priority:
        messenger = MESSENGERS.get(ch_name)
        if not messenger:
            continue
        if not await messenger.is_available():
            logger.info(f"Channel {ch_name} unavailable, trying next...")
            continue
        success = await messenger.send_message(phone, text)
        if success:
            logger.info(f"Message sent via {ch_name}")
            return True
        logger.warning(f"Failed to send via {ch_name}, trying fallback...")

    logger.error(f"All channels failed for {phone}")
    return False
