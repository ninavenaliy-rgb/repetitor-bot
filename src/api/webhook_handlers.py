"""Webhook handlers for payment providers."""

from __future__ import annotations

import json
from typing import Optional

from aiohttp import web
from loguru import logger

from src.services.billing_service import BillingService


class WebhookHandlers:
    """HTTP handlers for payment webhooks."""

    def __init__(self):
        self.billing_service = BillingService()

    async def yookassa_webhook(self, request: web.Request) -> web.Response:
        """Handle YooKassa webhook.

        YooKassa sends POST request with JSON payload.
        Signature is in HTTP header: X-YooKassa-Signature
        """
        try:
            # Get signature from header
            signature = request.headers.get("X-YooKassa-Signature", "")

            # Get payload
            payload = await request.json()

            logger.info(f"YooKassa webhook received: {payload.get('event')}")

            # Process webhook (idempotent)
            success = await self.billing_service.process_webhook(
                provider="yookassa",
                payload=payload,
                signature=signature,
            )

            if success:
                return web.json_response({"status": "ok"}, status=200)
            else:
                return web.json_response(
                    {"status": "error", "message": "Processing failed"}, status=400
                )

        except json.JSONDecodeError:
            logger.error("Invalid JSON in YooKassa webhook")
            return web.json_response(
                {"status": "error", "message": "Invalid JSON"}, status=400
            )

        except Exception as e:
            logger.error(f"YooKassa webhook error: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, status=500
            )

    async def stripe_webhook(self, request: web.Request) -> web.Response:
        """Handle Stripe webhook.

        Stripe sends POST request with JSON payload.
        Signature is in HTTP header: Stripe-Signature
        """
        try:
            # Get signature from header
            signature = request.headers.get("Stripe-Signature", "")

            # Get raw payload (Stripe requires raw body for signature verification)
            raw_payload = await request.text()
            payload = json.loads(raw_payload)

            logger.info(f"Stripe webhook received: {payload.get('type')}")

            # Process webhook (idempotent)
            success = await self.billing_service.process_webhook(
                provider="stripe",
                payload=payload,
                signature=signature,
            )

            if success:
                return web.json_response({"status": "ok"}, status=200)
            else:
                return web.json_response(
                    {"status": "error", "message": "Processing failed"}, status=400
                )

        except json.JSONDecodeError:
            logger.error("Invalid JSON in Stripe webhook")
            return web.json_response(
                {"status": "error", "message": "Invalid JSON"}, status=400
            )

        except Exception as e:
            logger.error(f"Stripe webhook error: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, status=500
            )

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"}, status=200)


async def create_webhook_app(host: str = "0.0.0.0", port: int = 8080) -> web.Application:
    """Create aiohttp app for webhooks.

    This runs alongside the Telegram bot in the same process.
    """
    app = web.Application()
    handlers = WebhookHandlers()

    # Routes
    app.router.add_post("/webhooks/yookassa", handlers.yookassa_webhook)
    app.router.add_post("/webhooks/stripe", handlers.stripe_webhook)
    app.router.add_get("/health", handlers.health_check)

    logger.info(f"Webhook server configured on {host}:{port}")
    return app


async def start_webhook_server(app: web.Application, host: str, port: int):
    """Start webhook server."""
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"Webhook server started on {host}:{port}")


# Example integration with main bot
"""
Usage in main.py:

async def main():
    # Start bot
    bot = Bot(...)
    dp = Dispatcher()

    # Start webhook server in background
    webhook_app = await create_webhook_app(host="0.0.0.0", port=8080)
    asyncio.create_task(start_webhook_server(webhook_app, "0.0.0.0", 8080))

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
"""
