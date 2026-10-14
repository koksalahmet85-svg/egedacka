"""Dış sistem webhook'ları: Meta Lead Ads ve ödeme sağlayıcı (iyzico/PayTR).

Her ikisi de imza doğrular ve idempotenttir (external_lead_id / provider_ref unique).
"""
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..core.config import get_settings
from ..core.db import get_conn, pool
from ..services import billing
from .crm import LeadIn, upsert_lead

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"


def _valid_signature(secret: str, body: bytes, header: str | None, prefix: str = "sha256=") -> bool:
    if not secret or not header or not header.startswith(prefix):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len(prefix):])


@router.get("/meta", response_class=PlainTextResponse)
async def meta_verify(mode: str = Query(alias="hub.mode"), token: str = Query(alias="hub.verify_token"),
                      challenge: str = Query(alias="hub.challenge")):
    s = get_settings()
    if mode == "subscribe" and s.meta_verify_token and hmac.compare_digest(token, s.meta_verify_token):
        return challenge
    raise HTTPException(403, "verify token mismatch")


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("90") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+9" + digits
    if len(digits) == 10 and digits.startswith("5"):
        return "+90" + digits
    return "+" + digits


def lead_from_meta(lead: dict, campaign_id: int | None) -> LeadIn:
    """Meta form alanlarını iç modele çevirir. Form alan adları kulübün formuna göre ayarlanır."""
    f = {d["name"]: (d.get("values") or [""])[0] for d in lead.get("field_data", [])}
    birth = f.get("cocuk_dogum_yili") or f.get("child_birth_year")
    return LeadIn(
        child_name=f.get("cocuk_adi") or f.get("child_name") or "?",
        child_birth_year=int(birth) if birth and birth.isdigit() else None,
        guardian_name=f.get("full_name") or f.get("veli_adi") or "?",
        phone=normalize_phone(f.get("phone_number", "")),
        email=f.get("email"),
        channel="META_ADS", campaign_id=campaign_id, external_lead_id=lead["id"],
        utm_source="meta", utm_campaign=lead.get("campaign_name"), utm_content=lead.get("ad_name"),
        kvkk_consent=True,  # Meta formunda zorunlu KVKK onay kutusu (custom disclaimer) bulunmalı
    )


async def _fetch_and_store(leadgen_id: str) -> None:
    s = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{GRAPH}/{leadgen_id}", params={
            "access_token": s.meta_page_token, "fields": "id,created_time,field_data,campaign_id,campaign_name,ad_name"})
        r.raise_for_status()
        lead = r.json()
    async with pool().acquire() as conn, conn.transaction():
        campaign_id = await conn.fetchval(
            "SELECT id FROM campaigns WHERE channel='META_ADS' AND external_id=$1", lead.get("campaign_id"))
        await upsert_lead(conn, lead_from_meta(lead, campaign_id))


@router.post("/meta")
async def meta_leadgen(request: Request, background: BackgroundTasks,
                       x_hub_signature_256: str | None = Header(None)):
    """Meta 'leadgen' webhook'u. Hızlı 200 döneriz (Meta 20 sn'de timeout eder),
    lead detayı Graph API'den arka planda çekilir."""
    body = await request.body()
    if not _valid_signature(get_settings().meta_app_secret, body, x_hub_signature_256):
        raise HTTPException(401, "invalid signature")
    payload = await request.json()
    ids = [c["value"]["leadgen_id"] for e in payload.get("entry", []) for c in e.get("changes", [])
           if c.get("field") == "leadgen"]
    for lid in ids:
        background.add_task(_fetch_and_store, lid)
    return {"received": len(ids)}


@router.post("/payments")
async def payment_callback(request: Request, x_signature: str | None = Header(None),
                           conn: asyncpg.Connection = Depends(get_conn)):
    """Online/kayıtlı kart tahsilatı. Sağlayıcı aynı bildirimi tekrar gönderse de tek kayıt oluşur."""
    body = await request.body()
    if not _valid_signature(get_settings().payment_webhook_secret, body, x_signature, prefix=""):
        raise HTTPException(401, "invalid signature")
    p = await request.json()
    if p.get("status") != "SUCCESS":
        return {"ignored": True}
    inv = await conn.fetchrow("SELECT id, guardian_id FROM invoices WHERE number=$1", p["invoice_number"])
    if not inv:
        raise HTTPException(404, "invoice not found")
    rec = await billing.record_payment(
        conn, guardian_id=inv["guardian_id"], invoice_id=inv["id"], amount=Decimal(str(p["amount"])),
        method="ONLINE", paid_at=datetime.now(UTC), provider_ref=p["transaction_id"])
    return {"receipt_no": rec["receipt_no"], "duplicate": rec["duplicate"]}
