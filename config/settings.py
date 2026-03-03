"""Application configuration via environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from .env file."""

    # Telegram
    bot_token: str = ""
    bot_username: str = ""  # e.g. "my_tutor_bot" (without @)

    # Database
    database_url: str = "postgresql+asyncpg://repetitor:changeme@localhost:5432/repetitor"
    db_password: str = "changeme"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Google Calendar
    google_calendar_credentials_path: str = "credentials.json"
    google_calendar_id: str = "primary"

    # Telegram Stars — основной способ оплаты подписок (встроен в Telegram, ничего настраивать не нужно)

    # Оплата уроков через @BotFather (опционально, для пакетов уроков)
    yookassa_provider_token: str = ""  # from @BotFather → Payments

    # Менеджер для оплаты переводом на карту
    manager_username: str = "aileadflow"

    # Feedback
    feedback_chat_id: int = 0  # Chat/channel ID where student feedback is forwarded

    # App Settings
    timezone: str = "Europe/Moscow"
    reminder_minutes_before: int = 60
    ai_rate_limit_per_user: int = 20
    dashboard_secret_key: str = "change-this-to-random-string"

    # Admin Access (comma-separated Telegram user IDs)
    admin_user_ids: str = ""  # e.g. "123456789,987654321"

    # Paths
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"

    def get_admin_ids(self) -> list[int]:
        """Parse admin user IDs from comma-separated string."""
        if not self.admin_user_ids:
            return []
        return [int(uid.strip()) for uid in self.admin_user_ids.split(",") if uid.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
