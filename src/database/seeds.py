"""Seed initial data — subscription plans (START / PRO)."""

from __future__ import annotations

from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models_subscription import SubscriptionPlan


PLAN_DEFINITIONS = [
    {
        "code": "START",
        "name_ru": "СТАРТ",
        "name_en": "Start",
        "description_ru": "Всё необходимое для репетитора",
        "price_rub_monthly": Decimal("990.00"),
        "max_students": -1,  # Безлимит
        "max_ai_checks_per_month": 30,
        "sort_order": 1,
        "features": {
            "booking": True,
            "homework_tracking": True,
            "reminders": True,
            "lesson_packages": True,
            "basic_analytics": True,
            "ai_homework_check": True,
            "ai_lesson_planning": False,
            "analytics_detail": False,
            "calendar_sync": False,
            "parent_notifications": False,
            "priority_support": False,
        },
    },
    {
        "code": "PRO",
        "name_ru": "ПРО",
        "name_en": "Pro",
        "description_ru": "Расширенные возможности для продвинутых репетиторов",
        "price_rub_monthly": Decimal("1990.00"),
        "max_students": -1,  # Безлимит
        "max_ai_checks_per_month": None,  # Безлимит
        "sort_order": 2,
        "features": {
            "booking": True,
            "homework_tracking": True,
            "reminders": True,
            "lesson_packages": True,
            "basic_analytics": True,
            "ai_homework_check": True,
            "ai_lesson_planning": True,
            "analytics_detail": True,
            "calendar_sync": True,
            "parent_notifications": True,
            "priority_support": True,
        },
    },
]


async def seed_subscription_plans(session: AsyncSession) -> None:
    """Create START and PRO plans if they don't exist yet."""
    for plan_data in PLAN_DEFINITIONS:
        result = await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.code == plan_data["code"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update features and pricing in case they changed
            existing.features = plan_data["features"]
            existing.price_rub_monthly = plan_data["price_rub_monthly"]
            existing.max_students = plan_data["max_students"]
            existing.max_ai_checks_per_month = plan_data["max_ai_checks_per_month"]
            logger.debug(f"Plan {plan_data['code']} updated")
        else:
            plan = SubscriptionPlan(
                code=plan_data["code"],
                name_ru=plan_data["name_ru"],
                name_en=plan_data["name_en"],
                description_ru=plan_data.get("description_ru"),
                description_en=None,
                price_rub_monthly=plan_data["price_rub_monthly"],
                max_students=plan_data["max_students"],
                max_ai_checks_per_month=plan_data["max_ai_checks_per_month"],
                sort_order=plan_data["sort_order"],
                features=plan_data["features"],
                is_active=True,
                trial_days=7,
                grace_period_days=3,
            )
            session.add(plan)
            logger.info(f"Plan {plan_data['code']} created")

    # Deactivate legacy plans that no longer exist in PLAN_DEFINITIONS
    active_codes = {p["code"] for p in PLAN_DEFINITIONS}
    legacy_result = await session.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.code.notin_(active_codes))
    )
    for legacy_plan in legacy_result.scalars().all():
        if legacy_plan.is_active:
            legacy_plan.is_active = False
            logger.info(f"Legacy plan {legacy_plan.code} deactivated")

    await session.commit()
