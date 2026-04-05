import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.services.messaging.base import BaseMessenger

logger = logging.getLogger(__name__)


class EmailMessenger(BaseMessenger):
    name = "email"

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "smtp.yandex.ru")
        self.port = int(os.getenv("SMTP_PORT", "465"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_name = os.getenv("SMTP_FROM_NAME", "B2B Система")

    async def send_message(self, phone: str, text: str) -> bool:
        # phone здесь используется как email адрес
        if not self.user or not self.password:
            logger.warning("Email not configured")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Ответ на вашу заявку"
            msg["From"] = f"{self.from_name} <{self.user}>"
            msg["To"] = phone
            msg.attach(MIMEText(text, "plain", "utf-8"))

            with smtplib.SMTP_SSL(self.host, self.port) as server:
                server.login(self.user, self.password)
                server.sendmail(self.user, phone, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    async def is_available(self) -> bool:
        return bool(self.user and self.password)
