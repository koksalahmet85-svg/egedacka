"""Outbox worker: QUEUED bildirimleri kanal adaptörleriyle gönderir.

WhatsApp: Meta Cloud API şablon mesajı (şablonlar Meta Business'ta önceden onaylanmalı).
SMS/E-posta: sağlayıcı seçimi kulübe göre (Netgsm, Postmark vb.) — adaptör eklenir.
Ticari ileti değil, borç hatırlatması "bilgilendirme" mesajıdır; yine de İYS kuralları
pazarlama mesajları için Lead.marketingConsent / Consent.MARKETING ile kontrol edilir.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import httpx

from ..core.config import get_settings
from ..core.db import db
from ..core.timeutil import utcnow

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

Sender = Callable[[str, str, dict], Awaitable[None]]


async def _send_whatsapp(to: str, template: str, payload: dict) -> None:
    s = get_settings()
    if not s.meta_access_token:
        raise RuntimeError("META_ACCESS_TOKEN yok")
    params = [{"type": "text", "text": str(v)} for v in payload.values()]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"https://graph.facebook.com/v21.0/{s.whatsapp_phone_number_id}/messages",
            headers={"Authorization": f"Bearer {s.meta_access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to.lstrip("+"),
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": "tr"},
                    "components": [{"type": "body", "parameters": params}],
                },
            },
        )
        r.raise_for_status()


async def _log_only(to: str, template: str, payload: dict) -> None:
    log.info("bildirim [%s] → %s %s", template, to, payload)


SENDERS: dict[str, Sender] = {
    "WHATSAPP": _send_whatsapp,
    "SMS": _log_only,
    "EMAIL": _log_only,
    "PUSH": _log_only,
    "IN_APP": _log_only,  # panelde Notification tablosundan okunur
}


async def dispatch_queued(limit: int = 100) -> dict:
    queued = await db.notification.find_many(
        where={"status": "QUEUED", "scheduledFor": {"lte": utcnow()}}, order={"scheduledFor": "asc"}, take=limit
    )
    sent = failed = 0
    for n in queued:
        try:
            await SENDERS[n.channel](n.toAddress, n.template, dict(n.payload or {}))
        except Exception as exc:
            failed += 1
            give_up = n.attempts + 1 >= MAX_ATTEMPTS
            await db.notification.update(
                where={"id": n.id},
                data={
                    "attempts": {"increment": 1},
                    "error": str(exc)[:500],
                    "status": "FAILED" if give_up else "QUEUED",
                },
            )
            continue
        sent += 1
        await db.notification.update(where={"id": n.id}, data={"status": "SENT", "sentAt": utcnow()})
    return {"sent": sent, "failed": failed}
