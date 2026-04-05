from abc import ABC, abstractmethod
from typing import Optional


class BaseMessenger(ABC):
    name: str = "base"

    @abstractmethod
    async def send_message(self, phone: str, text: str) -> bool:
        """Отправить сообщение пользователю. Возвращает True если успешно."""
        ...

    async def send_notification(self, data: dict) -> bool:
        text = self._format_notification(data)
        return await self.send_message(data["phone"], text)

    def _format_notification(self, data: dict) -> str:
        return (
            f"📋 Новая заявка\n"
            f"Имя: {data.get('name')}\n"
            f"Телефон: {data.get('phone')}\n"
            f"Источник: {data.get('source')}\n"
            f"Сообщение: {data.get('message', '')[:200]}"
        )

    async def is_available(self) -> bool:
        return True
