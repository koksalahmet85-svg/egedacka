"""Dış sistem webhook'ları. İmza doğrulanır, ham olay saklanır, işlem idempotenttir."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response

from prisma import Json
from prisma.errors import UniqueViolationError

from ..core.config import get_settings
from ..core.db import db
from ..core.timeutil import utcnow
from ..services import crm, dashboard

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


async def _store(provider: str, external_id: str, payload: dict) -> str | None:
    """İlk kez geliyorsa olay id'si, tekrar ise None döner."""
    try:
        ev = await db.webhookevent.create(
            data={"provider": provider, "externalId": external_id, "payload": Json(payload)}
        )
        return ev.id
    except UniqueViolationError:
        return None


async def _done(event_id: str, error: str | None = None) -> None:
    await db.webhookevent.update(where={"id": event_id}, data={"processedAt": utcnow(), "error": error})


# ── Meta Lead Ads ──
@router.get("/meta")
async def meta_verify(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    if mode == "subscribe" and token == get_settings().meta_verify_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(403, "doğrulama başarısız")


async def _process_meta(event_id: str, leadgen_id: str) -> None:
    try:
        await crm.ingest_meta_lead(leadgen_id)
        dashboard.invalidate_cache()
        await _done(event_id)
    except Exception as e:
        log.exception("meta lead işlenemedi")
        await _done(event_id, str(e)[:500])


@router.post("/meta")
async def meta_leads(request: Request, bg: BackgroundTasks, x_hub_signature_256: str | None = Header(None)):
    body = await request.body()
    if not crm.verify_hmac_sha256(get_settings().meta_app_secret, body, x_hub_signature_256, prefix="sha256="):
        raise HTTPException(401, "imza geçersiz")
    payload = json.loads(body)
    queued = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            leadgen_id = str(change["value"]["leadgen_id"])
            event_id = await _store("meta", leadgen_id, change["value"])
            if event_id:
                # Meta 20 sn içinde 200 bekler; Graph çağrısı arka planda.
                bg.add_task(_process_meta, event_id, leadgen_id)
                queued += 1
    return {"queued": queued}


# ── Cal.com (deneme antrenmanı rezervasyonu) ──
@router.post("/calcom")
async def calcom(request: Request, x_cal_signature_256: str | None = Header(None)):
    body = await request.body()
    if not crm.verify_hmac_sha256(get_settings().calcom_webhook_secret, body, x_cal_signature_256):
        raise HTTPException(401, "imza geçersiz")
    data = json.loads(body)
    trigger = data.get("triggerEvent", "")
    payload = data.get("payload", {})
    event_id = await _store("calcom", f'{trigger}:{payload.get("uid")}', data)
    if event_id is None:
        return {"status": "duplicate"}
    if trigger not in ("BOOKING_CREATED", "BOOKING_CANCELLED", "BOOKING_RESCHEDULED"):
        await _done(event_id)
        return {"status": "ignored"}
    try:
        result = await crm.handle_calcom_booking(trigger, payload)
    except crm.CrmError as e:
        await _done(event_id, str(e))
        # 200 dön: Cal.com aynı hatalı olayı sonsuza dek tekrar denemesin; hata panelde görünür.
        return {"status": "rejected", "reason": str(e)}
    await _done(event_id)
    dashboard.invalidate_cache()
    return {"status": "ok", "result": result}
