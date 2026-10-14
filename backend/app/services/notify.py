"""Transactional outbox. Mesajlar iş transaction'ı ile birlikte yazılır, worker gönderir.

Böylece "fatura kesildi ama SMS gitmedi" ya da "SMS gitti ama transaction geri
alındı" durumları oluşmaz. dedupe_key aynı mesajın iki kez kuyruğa girmesini engeller.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

import asyncpg

log = logging.getLogger(__name__)


async def enqueue(conn: asyncpg.Connection, channel: str, recipient: str | None, template: str,
                  payload: dict[str, Any], dedupe_key: str) -> bool:
    if not recipient:
        return False
    inserted = await conn.fetchval(
        """INSERT INTO notification_outbox (channel, recipient, template, payload, dedupe_key)
           VALUES ($1,$2,$3,$4::jsonb,$5) ON CONFLICT (dedupe_key) DO NOTHING RETURNING id""",
        channel, recipient, template, payload, dedupe_key)
    return inserted is not None


class Sender(Protocol):
    async def send(self, channel: str, recipient: str, template: str, payload: dict) -> None: ...


class LogSender:
    """Geliştirme ortamı: gerçek SMS/WhatsApp sağlayıcısı (Netgsm, İleti Merkezi,
    WhatsApp Cloud API) bu arayüzü uygulayarak takılır."""

    async def send(self, channel: str, recipient: str, template: str, payload: dict) -> None:
        log.info("NOTIFY %s → %s [%s] %s", channel, recipient, template, payload)


async def dispatch_outbox(conn: asyncpg.Connection, sender: Sender, batch: int = 100) -> int:
    """SKIP LOCKED → birden fazla worker paralel çalışsa da aynı mesaj tek kez işlenir."""
    sent = 0
    async with conn.transaction():
        items = await conn.fetch(
            """SELECT id, channel, recipient, template, payload FROM notification_outbox
               WHERE status IN ('PENDING','FAILED') AND attempts < 5
               ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED""", batch)
        for it in items:
            try:
                await sender.send(it["channel"], it["recipient"], it["template"], it["payload"])
                await conn.execute(
                    "UPDATE notification_outbox SET status='SENT', sent_at=now(), attempts=attempts+1 WHERE id=$1",
                    it["id"])
                sent += 1
            except Exception as exc:  # noqa: BLE001 — sağlayıcı hatası kuyrukta tekrar denenir
                await conn.execute(
                    "UPDATE notification_outbox SET status='FAILED', attempts=attempts+1, last_error=$2 WHERE id=$1",
                    it["id"], str(exc)[:500])
    return sent
