"""Bot and Dispatcher factory."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings


def create_bot() -> Bot:
    """Create and configure the Bot instance."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Create Dispatcher with FSM storage and register all routers."""
    dp = Dispatcher(storage=MemoryStorage())

    # Register middlewares
    from src.bot.middlewares.logging_mw import LoggingMiddleware
    from src.bot.middlewares.auth_mw import AuthMiddleware
    from src.middleware.admin_middleware import AdminMiddleware
    from src.middleware.subscription_middleware import (
        SubscriptionMiddleware,
        StudentLimitMiddleware,
    )

    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # Subscription middleware (after auth, so db_tutor is available)
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    dp.message.middleware(StudentLimitMiddleware())
    dp.callback_query.middleware(StudentLimitMiddleware())

    # Register routers
    from src.bot.handlers.admin_panel import router as admin_panel_router
    from src.bot.handlers.start import router as start_router
    from src.bot.handlers.placement import router as placement_router
    from src.bot.handlers.booking import router as booking_router
    from src.bot.handlers.engagement import router as engagement_router
    from src.bot.handlers.homework import router as homework_router
    from src.bot.handlers.confirmation import router as confirmation_router
    from src.bot.handlers.tutor_panel import router as tutor_panel_router
    from src.bot.handlers.tutor_registration import router as tutor_reg_router
    # from src.bot.handlers.lesson_plan import router as lesson_plan_router  # DEPRECATED: moved to tutor_panel.py with premium checks
    from src.bot.handlers.student_payment import router as student_payment_router
    from src.bot.handlers.referral import router as referral_router
    from src.bot.handlers.student_referral import router as student_referral_router
    from src.bot.handlers.language import router as language_router
    from src.bot.handlers.feedback import router as feedback_router
    from src.bot.handlers.subscription_panel import router as subscription_panel_router
    from src.bot.handlers.ai_admin_handler import router as ai_admin_router

    # Admin panel must come FIRST for highest priority
    dp.include_router(admin_panel_router)

    # Tutor panel and registration must come BEFORE start so their handlers take priority
    dp.include_router(ai_admin_router)   # AI admin: catches 'ИИ ...' text + voice from tutors
    dp.include_router(tutor_reg_router)
    dp.include_router(subscription_panel_router)  # NEW: Subscription management
    dp.include_router(tutor_panel_router)
    # dp.include_router(lesson_plan_router)  # DEPRECATED: functionality moved to tutor_panel.py
    dp.include_router(referral_router)
    dp.include_router(student_payment_router)
    dp.include_router(student_referral_router)
    dp.include_router(language_router)
    dp.include_router(start_router)
    dp.include_router(placement_router)
    dp.include_router(booking_router)
    dp.include_router(feedback_router)
    dp.include_router(homework_router)
    dp.include_router(confirmation_router)
    dp.include_router(engagement_router)

    return dp
