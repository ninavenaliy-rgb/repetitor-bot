"""Управление подпиской репетитора — выбор тарифа, оплата Stars/картой."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from src.database.engine import get_session
from src.services.subscription_service import SubscriptionService
from src.services.telegram_stars_billing import TelegramStarsBilling

router = Router(name="subscription_panel")

# Shared service instance (avoids re-instantiation per callback)
_subscription_service = SubscriptionService()

# ── Конфигурация ─────────────────────────────────────────────────────────────

MANAGER_URL = "https://t.me/aileadflow"

PLANS = {
    "START": {
        "name": "СТАРТ",
        "emoji": "📦",
        "price_rub": 990,
        "stars": 50,
        "features": [
            "Безлимит студентов",
            "Расписание и запись на уроки",
            "Домашние задания и прогресс",
            "Напоминания за 24ч и 2ч до урока",
            "Пакеты уроков (оплата студентами)",
            "AI проверка домашних заданий — 30/мес",
            "Базовая аналитика доходов",
        ],
    },
    "PRO": {
        "name": "ПРО",
        "emoji": "💎",
        "price_rub": 1990,
        "stars": 100,
        "features": [
            "Всё из тарифа СТАРТ, плюс:",
            "AI проверка ДЗ — без ограничений",
            "AI составление плана урока",
            "Расширенная аналитика с трендами",
            "Google Calendar синхронизация",
            "Уведомления для родителей",
            "Приоритетная поддержка",
        ],
    },
}

STATUS_EMOJI = {"trial": "🎁", "active": "✅", "grace": "⚠️", "expired": "❌", "canceled": "🚫"}
STATUS_LABEL = {
    "trial": "Пробный период",
    "active": "Активна",
    "grace": "Льготный период",
    "expired": "Истекла",
    "canceled": "Отменена",
}


# ── Главный экран ─────────────────────────────────────────────────────────────


@router.message(Command("subscription"))
@router.message(F.text == "💎 Моя подписка")
async def subscription_menu(message: Message, db_tutor=None, subscription=None, subscription_plan=None):
    """Показать текущую подписку или предложить выбор тарифа."""
    if not db_tutor:
        await message.answer("Эта функция только для репетиторов.\n\nЗарегистрируйтесь: /become_tutor")
        return

    if not subscription or not subscription_plan:
        await message.answer(
            _plans_text(),
            parse_mode="HTML",
            reply_markup=_plans_keyboard(),
        )
        return

    # Данные тарифа — сначала из локального словаря, иначе из БД
    plan_cfg = PLANS.get(subscription_plan.code, {})
    plan_name = plan_cfg.get("name") or getattr(subscription_plan, "name_ru", subscription_plan.code)
    plan_emoji = plan_cfg.get("emoji", "📦")

    now = datetime.now(timezone.utc)

    # Определяем дату окончания
    if subscription.status == "trial" and subscription.trial_end:
        end_date = subscription.trial_end
    elif subscription.status == "grace" and subscription.grace_period_end:
        end_date = subscription.grace_period_end
    else:
        end_date = subscription.current_period_end

    days_left = max(0, (end_date - now).days) if end_date else 0

    # Отменена ли подписка (но ещё активна до конца периода)
    is_pending_cancel = (
        getattr(subscription, "canceled_at", None) is not None
        and subscription.status in ("trial", "active")
    )

    if is_pending_cancel:
        emoji = "🔴"
        label = f"Отменяется {end_date.strftime('%d.%m.%Y')}"
    else:
        emoji = STATUS_EMOJI.get(subscription.status, "📋")
        label = STATUS_LABEL.get(subscription.status, subscription.status)

    price = int(subscription.amount) if subscription.amount else plan_cfg.get("price_rub", 0)

    text = (
        f"{emoji} <b>Подписка {plan_emoji} {plan_name}</b>\n\n"
        f"Статус: {label}\n"
        f"Осталось: {days_left} дн. (до {end_date.strftime('%d.%m.%Y') if end_date else '—'})\n"
        f"Стоимость: {price:,}₽/мес\n"
    )

    rows = []
    if is_pending_cancel:
        # Подписка уже отменена — только восстановление
        rows.append([
            InlineKeyboardButton(text="↩️ Восстановить подписку", callback_data="sub_restore")
        ])
        rows.append([
            InlineKeyboardButton(text="🔄 Сменить тариф", callback_data="sub_show_plans")
        ])
    elif subscription.status in ("trial", "active"):
        if subscription_plan.code == "START":
            rows.append([
                InlineKeyboardButton(text="⬆️ Улучшить до ПРО", callback_data="sub_upgrade_PRO")
            ])
        elif subscription_plan.code == "PRO":
            rows.append([
                InlineKeyboardButton(text="⬇️ Понизить до СТАРТ", callback_data="sub_downgrade_START")
            ])
        rows.append([
            InlineKeyboardButton(text="❌ Отменить подписку", callback_data="sub_cancel_confirm")
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="sub_show_plans")
        ])

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )


# ── Выбор тарифа ─────────────────────────────────────────────────────────────


def _plans_text() -> str:
    lines = ["💎 <b>Выберите тариф для репетитора</b>\n"]
    for plan in PLANS.values():
        lines.append(f"{plan['emoji']} <b>{plan['name']} — {plan['price_rub']:,}₽/мес</b>")
        for f in plan["features"]:
            lines.append(f"  • {f}")
        lines.append("")
    lines.append("🎁 <b>7 дней бесплатно</b> при первом подключении!")
    return "\n".join(lines)


def _plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 СТАРТ — 990₽/мес", callback_data="sub_select_START")],
            [InlineKeyboardButton(text="💎 ПРО — 1990₽/мес", callback_data="sub_select_PRO")],
        ]
    )


@router.callback_query(F.data == "sub_show_plans")
async def show_plans(callback: CallbackQuery):
    await callback.message.edit_text(_plans_text(), parse_mode="HTML", reply_markup=_plans_keyboard())
    await callback.answer()


@router.callback_query(F.data.in_({"sub_select_START", "sub_select_PRO"}))
async def select_plan(callback: CallbackQuery, db_tutor):
    """Выбрать тариф — запустить триал или показать оплату."""
    if not db_tutor:
        await callback.answer("Ошибка: репетитор не найден", show_alert=True)
        return

    plan_code = callback.data.replace("sub_select_", "")
    plan = PLANS[plan_code]
    service = SubscriptionService()

    try:
        subscription = await service.create_trial_subscription(
            tutor_id=db_tutor.id,
            plan_code=plan_code,
            currency="RUB",
        )

        text = (
            f"🎉 <b>7 дней бесплатно активированы!</b>\n\n"
            f"Тариф: {plan['emoji']} {plan['name']}\n"
            f"Пробный период до: <b>{subscription.trial_end.strftime('%d.%m.%Y')}</b>\n"
            f"После окончания: {plan['price_rub']:,}₽/мес\n\n"
            f"Оплатить сейчас или ближе к окончанию пробного периода — выбор за вами."
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_payment_keyboard(plan_code),
        )
        await callback.answer("Пробный период активирован!")

    except ValueError:
        # Триал уже был использован — сразу показываем оплату
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository
            sub_repo = SubscriptionRepository(session)
            subscription = await sub_repo.get_by_tutor(db_tutor.id)

        if not subscription:
            await callback.answer("Ошибка: подписка не найдена", show_alert=True)
            return

        text = (
            f"{plan['emoji']} <b>Оплата тарифа {plan['name']}</b>\n\n"
            f"Стоимость: {plan['price_rub']:,}₽/мес\n\n"
            f"Выберите удобный способ оплаты:"
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_payment_keyboard(plan_code),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора тарифа: {e}")
        await callback.answer("Ошибка. Попробуйте позже.", show_alert=True)


def _payment_keyboard(plan_code: str) -> InlineKeyboardMarkup:
    plan = PLANS[plan_code]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Оплатить {plan['stars']} Telegram Stars",
                    callback_data=f"sub_pay_stars_{plan_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Оплатить переводом на карту",
                    callback_data=f"sub_pay_card_{plan_code}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="sub_show_plans")],
        ]
    )


# ── Оплата через Telegram Stars ───────────────────────────────────────────────


@router.callback_query(F.data.startswith("sub_pay_stars_"))
async def pay_with_stars(callback: CallbackQuery, db_tutor):
    """Отправить инвойс в Telegram Stars."""
    if not db_tutor:
        await callback.answer("Ошибка: репетитор не найден", show_alert=True)
        return

    plan_code = callback.data.replace("sub_pay_stars_", "")
    if plan_code not in PLANS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    plan = PLANS[plan_code]

    async with get_session() as session:
        from src.database.repositories.subscription_repo import SubscriptionRepository
        sub_repo = SubscriptionRepository(session)
        subscription = await sub_repo.get_by_tutor(db_tutor.id)

    if not subscription:
        await callback.answer("Подписка не найдена. Сначала выберите тариф.", show_alert=True)
        return

    try:
        billing = TelegramStarsBilling()
        await billing.create_invoice(
            bot=callback.bot,
            chat_id=callback.from_user.id,
            subscription_id=subscription.id,
            tutor_id=db_tutor.id,
            plan_code=plan_code,
            plan_name=plan["name"],
            description=f"Доступ на 30 дней — тариф {plan['name']}",
        )
        await callback.answer(f"Инвойс на {plan['stars']} Stars отправлен ↑")

    except Exception as e:
        logger.error(f"Ошибка создания Stars инвойса: {e}")
        await callback.answer("Не удалось создать инвойс. Попробуйте позже.", show_alert=True)


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query):
    """Проверка перед списанием Stars."""
    billing = TelegramStarsBilling()
    await billing.handle_pre_checkout(pre_checkout_query)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message):
    """Успешная оплата Stars — активировать подписку."""
    billing = TelegramStarsBilling()
    success = await billing.handle_successful_payment(
        payment=message.successful_payment,
        user_id=message.from_user.id,
    )

    if success:
        await message.answer(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "Подписка активирована на 30 дней.\n"
            "Детали: /subscription",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "Оплата получена, но возникла ошибка при активации.\n"
            "Напишите менеджеру — разберёмся быстро: @aileadflow"
        )


# ── Оплата переводом на карту ────────────────────────────────────────────────


@router.callback_query(F.data.startswith("sub_pay_card_"))
async def pay_by_card(callback: CallbackQuery):
    """Инструкция для оплаты переводом через менеджера."""
    plan_code = callback.data.replace("sub_pay_card_", "")
    if plan_code not in PLANS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    plan = PLANS[plan_code]

    text = (
        f"💳 <b>Оплата переводом — тариф {plan['emoji']} {plan['name']}</b>\n\n"
        f"Сумма: <b>{plan['price_rub']:,}₽/мес</b>\n\n"
        f"Как оплатить:\n"
        f"1. Нажмите кнопку ниже — откроется чат с менеджером\n"
        f"2. Напишите: <i>«Хочу оплатить {plan['name']} {plan['price_rub']}₽»</i>\n"
        f"3. Получите реквизиты и переведите деньги\n"
        f"4. Пришлите скриншот чека — подписку активируют в течение 15 минут\n\n"
        f"⭐ Или оплатите через Telegram Stars — активация мгновенная."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Написать менеджеру @aileadflow",
                    url=MANAGER_URL,
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ Оплатить {plan['stars']} Stars (мгновенно)",
                    callback_data=f"sub_pay_stars_{plan_code}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"sub_select_{plan_code}")],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ── Апгрейд и даунгрейд ──────────────────────────────────────────────────────


@router.callback_query(F.data == "sub_upgrade_PRO")
async def upgrade_to_pro(callback: CallbackQuery, db_tutor=None, subscription=None):
    """Апгрейд со СТАРТ на ПРО."""
    if not db_tutor or not subscription:
        await callback.answer("Ошибка: данные не найдены", show_alert=True)
        return

    plan = PLANS["PRO"]

    try:
        service = SubscriptionService()
        await service.upgrade_subscription(subscription_id=subscription.id, new_plan_code="PRO")
    except Exception as e:
        logger.error(f"Ошибка апгрейда: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    text = (
        f"💎 <b>Апгрейд до ПРО</b>\n\n"
        f"Стоимость: {plan['price_rub']:,}₽/мес\n\n"
        f"Оплатите любым удобным способом:"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_payment_keyboard("PRO"),
    )
    await callback.answer()


@router.callback_query(F.data == "sub_downgrade_START")
async def downgrade_to_start(callback: CallbackQuery, subscription=None):
    """Понижение с ПРО до СТАРТ — вступает в силу со следующего периода."""
    if not subscription:
        await callback.answer("Подписка не найдена", show_alert=True)
        return

    try:
        service = SubscriptionService()
        await service.downgrade_subscription(subscription_id=subscription.id, new_plan_code="START")
    except Exception as e:
        logger.error(f"Ошибка даунгрейда: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    text = (
        f"⬇️ <b>Понижение до СТАРТ запланировано</b>\n\n"
        f"Дата перехода: {subscription.current_period_end.strftime('%d.%m.%Y')}\n\n"
        f"До этого дня все функции ПРО остаются доступными."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Понятно", callback_data="sub_back")]]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer("Даунгрейд запланирован")


# ── Отмена подписки ───────────────────────────────────────────────────────────


@router.callback_query(F.data == "sub_cancel_confirm")
async def cancel_confirm(callback: CallbackQuery):
    """Подтверждение отмены подписки."""
    text = (
        "❌ <b>Отмена подписки</b>\n\n"
        "После окончания текущего периода доступ к функциям ограничится.\n"
        "До конца оплаченного периода всё работает как обычно."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отменить", callback_data="sub_cancel_yes"),
                InlineKeyboardButton(text="◀️ Нет, оставить", callback_data="sub_back"),
            ]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "sub_cancel_yes")
async def cancel_subscription(callback: CallbackQuery, subscription=None):
    """Отменить подписку (действует до конца периода)."""
    if not subscription:
        await callback.answer("Подписка не найдена", show_alert=True)
        return

    try:
        service = SubscriptionService()
        await service.cancel_subscription(subscription_id=subscription.id, immediate=False)
    except Exception as e:
        logger.error(f"Ошибка отмены: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    # Determine end date (trial subscriptions use trial_end)
    if subscription.status == "trial" and subscription.trial_end:
        end_date = subscription.trial_end
    else:
        end_date = subscription.current_period_end

    text = (
        "✅ <b>Подписка отменена</b>\n\n"
        f"Все функции доступны до: <b>{end_date.strftime('%d.%m.%Y')}</b>\n\n"
        "Чтобы возобновить — откройте /subscription"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Восстановить", callback_data="sub_restore")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer("Подписка отменена")


@router.callback_query(F.data == "sub_restore")
async def restore_subscription(callback: CallbackQuery, subscription=None):
    """Восстановить (отменить отмену) подписки."""
    if not subscription:
        await callback.answer("Подписка не найдена", show_alert=True)
        return

    try:
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository
            repo = SubscriptionRepository(session)
            sub = await repo.get_by_id(subscription.id)
            if sub:
                await repo.update(sub, auto_renew=True, canceled_at=None)
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ <b>Подписка восстановлена!</b>\n\nДоступ продолжится в обычном режиме.",
        parse_mode="HTML",
    )
    await callback.answer("Подписка восстановлена!")


# ── Навигация ─────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "sub_back")
async def back_to_menu(callback: CallbackQuery, db_tutor):
    """Вернуться в главное меню подписки — перезагружаем свежие данные."""
    await callback.message.delete()
    # Reload fresh subscription data instead of using potentially stale cached objects
    fresh_sub, fresh_plan = await _subscription_service.get_subscription_with_plan(db_tutor.id) if db_tutor else (None, None)
    # Re-use subscription_menu logic with a fake Message-like context
    fake = callback.message
    await subscription_menu(fake, db_tutor, fresh_sub, fresh_plan)
    await callback.answer()
