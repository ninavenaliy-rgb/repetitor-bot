from abc import ABC, abstractmethod
from typing import Optional


class BaseCRM(ABC):
    name: str = "base"

    @abstractmethod
    async def create_lead(self, data: dict) -> str:
        """Создать лид, вернуть ID."""
        ...

    @abstractmethod
    async def update_status(self, lead_id: str, status: str) -> bool:
        ...

    @abstractmethod
    async def assign_manager(self, lead_id: str, priority: str) -> bool:
        ...
