"""FastAPI application for tutor dashboard and payment webhooks."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Repetitor Bot Dashboard", docs_url=None, redoc_url=None)

templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, token: str = Query(default="")):
    """Main dashboard page."""
    from src.web.dependencies import get_tutor_by_token

    tutor = await get_tutor_by_token(token)
    if not tutor:
        return HTMLResponse("<h1>Unauthorized</h1><p>Invalid token.</p>", status_code=401)

    from src.services.analytics_service import AnalyticsService

    analytics = AnalyticsService()
    metrics = await analytics.get_dashboard_metrics(tutor.id)
    students = await analytics.get_students_list(tutor.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tutor": tutor,
            "metrics": metrics,
            "students": students,
        },
    )


@app.post("/webhook/robokassa")
async def robokassa_webhook(request: Request) -> PlainTextResponse:
    """Handle Robokassa payment notifications.

    Robokassa sends POST with: OutSum, InvId, SignatureValue, [EMail], [Fee]
    Must respond with "OK{InvId}" on success.
    """
    from loguru import logger

    form = await request.form()
    out_sum = form.get("OutSum", "")
    inv_id = form.get("InvId", "")
    signature = form.get("SignatureValue", "")

    logger.info(f"Robokassa webhook: OutSum={out_sum}, InvId={inv_id}")

    if not out_sum or not inv_id or not signature:
        logger.warning("Robokassa webhook: missing required fields")
        return PlainTextResponse("FAIL", status_code=400)

    from src.services.billing_service import BillingService

    billing = BillingService()
    success = await billing.process_webhook(
        provider="robokassa",
        payload={"OutSum": out_sum, "InvId": inv_id},
        signature=signature,
    )

    if success:
        # Robokassa requires "OK{InvId}" response to confirm receipt
        return PlainTextResponse(f"OK{inv_id}")
    else:
        return PlainTextResponse("FAIL", status_code=400)
