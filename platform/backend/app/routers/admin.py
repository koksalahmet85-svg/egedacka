"""Job'ları elle tetikleme (yönetici) ve sağlık kontrolü."""

from datetime import date

from fastapi import APIRouter

from ..core.db import db
from ..core.deps import Management
from ..services import ads_sync, billing, invoicing, notifications

router = APIRouter(prefix="/admin", tags=["Yönetim"])


@router.post("/jobs/overdue")
async def run_overdue(_: Management, today: date | None = None):
    return await billing.process_overdue(today)


@router.post("/jobs/notifications")
async def run_notifications(_: Management):
    return await notifications.dispatch_queued()


@router.post("/jobs/invoices/retry")
async def run_invoice_retry(_: Management):
    return {"retried": await invoicing.retry_failed_invoices()}


@router.post("/jobs/ads-sync")
async def run_ads_sync(_: Management, days: int = 3):
    return {"rows": await ads_sync.sync_recent(days)}


@router.get("/webhook-errors")
async def webhook_errors(_: Management):
    return await db.webhookevent.find_many(where={"error": {"not": None}}, order={"receivedAt": "desc"}, take=50)
