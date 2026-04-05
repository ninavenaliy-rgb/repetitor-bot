import logging
from typing import Optional
from app.services.messaging.router import send_to_user

logger = logging.getLogger(__name__)

CLARIFICATION_MESSAGE = """Здравствуйте, {name}! 👋

Спасибо за вашу заявку. Чтобы подготовить точный расчёт, уточните, пожалуйста:

1. Какой продукт вас интересует?
2. Из какого материала?
3. Какой объём/количество?
4. В какие сроки нужно?

Мы ответим в течение 15 минут в рабочее время.
"""

PRICE_MESSAGE = """Здравствуйте, {name}! ✅

Ваша заявка принята. Предварительный расчёт:

📦 Продукт: {product}
📐 Объём: {volume}
💰 Стоимость: от {total} ₽

*{note}*

Менеджер свяжется с вами для уточнения деталей и финального КП.
"""

WARMUP_MESSAGE = """Здравствуйте, {name}!

Ваша заявка обрабатывается. Мы уже изучаем детали и подготовим предложение.

Если хотите ускорить — позвоните: {phone}
Или напишите ещё раз с уточнениями.
"""


async def send_auto_reply(lead_data: dict, analysis: dict, price: Optional[dict]) -> None:
    name = lead_data.get("name", "клиент")
    phone = lead_data.get("phone", "")
    source = lead_data.get("source", "other")
    email = lead_data.get("email")

    if analysis.get("needs_clarification"):
        text = CLARIFICATION_MESSAGE.format(name=name)
    elif price:
        text = PRICE_MESSAGE.format(
            name=name,
            product=analysis.get("product", "—"),
            volume=analysis.get("volume", "—"),
            total=f"{price['total']:,.0f}",
            note=price.get("note", ""),
        )
    else:
        text = WARMUP_MESSAGE.format(name=name, phone=phone)

    # Отправляем через мессенджер
    await send_to_user(channel=source, phone=phone, text=text)

    # Дублируем на email если есть
    if email:
        await send_to_user(channel="email", phone=email, text=text)
