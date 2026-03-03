"""Application entry point — starts bot and web dashboard."""

from __future__ import annotations

import asyncio
import signal
import sys

from loguru import logger


def setup_logging() -> None:
    """Configure structured logging with loguru."""
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
        level="INFO",
    )
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )


async def run() -> None:
    """Main async entry point."""
    setup_logging()
    logger.info("Starting Repetitor Bot...")

    from src.bot.create_bot import create_bot, create_dispatcher
    from src.database.engine import init_db
    from src.services.reminder_service import (
        start_churn_check_loop,
        start_daily_word_loop,
        start_reminder_loop,
        start_trial_expiry_loop,
    )

    # Verify DB connection
    try:
        await init_db()
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

    bot = create_bot()
    dp = create_dispatcher()

    # Start background tasks
    reminder_task = asyncio.create_task(start_reminder_loop(bot))
    daily_word_task = asyncio.create_task(start_daily_word_loop(bot))
    churn_task = asyncio.create_task(start_churn_check_loop(bot))
    trial_task = asyncio.create_task(start_trial_expiry_loop(bot))

    logger.info("Bot is starting polling...")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        for task in (reminder_task, daily_word_task, churn_task, trial_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        logger.info("Bot stopped")


def main() -> None:
    """Synchronous entry point with signal handling."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.stop())

    try:
        loop.run_until_complete(run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
