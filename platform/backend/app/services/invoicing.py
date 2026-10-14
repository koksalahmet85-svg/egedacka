"""Otomatik fatura / makbuz kesimi.

Kulübün hukuki yapısı belirleyicidir (mali müşavirle teyit edilmeli):
  * Dernek (spor kulübü derneği): üye aidatı KDV'siz → RECEIPT (alındı belgesi).
  * Şirket (SK A.Ş. / Ltd.): eğitim hizmeti → E_ARSIV fatura (%20 KDV, FeePlan.vatRate).

Sağlayıcı arayüzü soyuttur. Paraşüt adaptörü Paraşüt API v4 akışını izler
(sales_invoice → e_archive). Canlıya almadan önce Paraşüt sandbox'ında doğrulanmalıdır.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

from ..core.config import get_settings
from ..core.crypto import decrypt
from ..core.db import db
from ..core.timeutil import utcnow
from ..domain.money import ZERO, money

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class InvoiceRequest:
    invoice_id: str
    kind: str
    buyer_name: str
    buyer_tax_id: str | None  # TCKN; yoksa GİB kuralı gereği 11111111111
    buyer_email: str | None
    buyer_address: str | None
    description: str
    subtotal: Decimal
    vat_rate: Decimal
    total: Decimal


@dataclass(frozen=True)
class InvoiceResult:
    number: str
    provider_ref: str
    ettn: str | None
    pdf_url: str | None


class InvoiceProvider(Protocol):
    name: str

    async def issue(self, req: InvoiceRequest) -> InvoiceResult: ...


class MockProvider:
    """Geliştirme ve dernek makbuzları için: harici çağrı yapmaz."""

    name = "mock"

    async def issue(self, req: InvoiceRequest) -> InvoiceResult:
        ref = uuid.uuid4().hex[:12].upper()
        prefix = "MKB" if req.kind == "RECEIPT" else "EAS"
        return InvoiceResult(
            number=f"{prefix}{utcnow():%Y}{ref[:9]}",
            provider_ref=ref,
            ettn=str(uuid.uuid4()) if req.kind != "RECEIPT" else None,
            pdf_url=None,
        )


class ParasutProvider:
    name = "parasut"
    base = "https://api.parasut.com"

    def __init__(self) -> None:
        self.s = get_settings()
        self._token: str | None = None

    async def _auth(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        r = await client.post(
            f"{self.base}/oauth/token",
            data={
                "grant_type": "password",
                "client_id": self.s.parasut_client_id,
                "client_secret": self.s.parasut_client_secret,
                "username": self.s.parasut_username,
                "password": self.s.parasut_password,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            },
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    async def issue(self, req: InvoiceRequest) -> InvoiceResult:
        cid = self.s.parasut_company_id
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {await self._auth(client)}"}
            today = utcnow().date().isoformat()
            inv = await client.post(
                f"{self.base}/v4/{cid}/sales_invoices",
                headers=headers,
                json={
                    "data": {
                        "type": "sales_invoices",
                        "attributes": {
                            "item_type": "invoice",
                            "description": req.description,
                            "issue_date": today,
                            "due_date": today,
                            "currency": "TRL",
                            "billing_address": req.buyer_address or "",
                            "tax_number": req.buyer_tax_id or "11111111111",
                            "email": req.buyer_email,
                            "order_no": req.invoice_id,
                        },
                        "relationships": {
                            "details": {
                                "data": [
                                    {
                                        "type": "sales_invoice_details",
                                        "attributes": {
                                            "quantity": 1,
                                            "unit_price": str(req.subtotal),
                                            "vat_rate": str(req.vat_rate),
                                            "description": req.description,
                                        },
                                    }
                                ]
                            }
                        },
                    }
                },
            )
            inv.raise_for_status()
            invoice_ref = inv.json()["data"]["id"]
            arc = await client.post(
                f"{self.base}/v4/{cid}/e_archives",
                headers=headers,
                json={
                    "data": {
                        "type": "e_archives",
                        "relationships": {"sales_invoice": {"data": {"id": invoice_ref, "type": "sales_invoices"}}},
                    }
                },
            )
            arc.raise_for_status()
            # e-Arşiv oluşturma asenkron bir trackable_job döner; numara/ETTN sonraki
            # senkronda (retry_failed_invoices) sales_invoice üzerinden okunur.
            return InvoiceResult(number=f"PRS-{invoice_ref}", provider_ref=invoice_ref, ettn=None, pdf_url=None)


def get_provider(kind: str) -> InvoiceProvider:
    if kind == "RECEIPT" or get_settings().invoice_provider == "mock":
        return MockProvider()
    return ParasutProvider()


def split_vat(total: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    """KDV dahil tutardan matrah ve KDV'yi ayır."""
    if vat_rate <= ZERO:
        return money(total), ZERO
    subtotal = money(total / (1 + vat_rate / 100))
    return subtotal, money(total) - subtotal


async def create_invoice_for_payment(payment_id: str) -> str:
    """Ödeme kaydından fatura taslağı oluşturur ve keser. Hata olursa FAILED + retry."""
    payment = await db.payment.find_unique(
        where={"id": payment_id},
        include={
            "guardian": True,
            "invoice": True,
            "allocations": {"include": {"charge": {"include": {"subscription": {"include": {"feePlan": True}}}}}},
        },
    )
    if payment is None:
        raise ValueError("ödeme bulunamadı")
    if payment.invoice:
        return payment.invoice.id

    rates = {
        a.charge.subscription.feePlan.vatRate
        for a in payment.allocations or []
        if a.charge and a.charge.subscription and a.charge.subscription.feePlan
    }
    vat_rate = max(rates) if rates else ZERO
    kind = "RECEIPT" if vat_rate == ZERO else "E_ARSIV"
    subtotal, vat = split_vat(payment.amount, vat_rate)
    descr = (
        "; ".join(sorted({a.charge.description for a in payment.allocations or [] if a.charge})) or "Aidat tahsilatı"
    )

    invoice = await db.invoice.create(
        data={
            "number": f"TMP-{payment.id}",
            "kind": kind,
            "guardianId": payment.guardianId,
            "paymentId": payment.id,
            "subtotal": subtotal,
            "vatRate": vat_rate,
            "vatAmount": vat,
            "total": payment.amount,
        }
    )
    await issue_invoice(invoice.id, descr)
    return invoice.id


async def issue_invoice(invoice_id: str, description: str | None = None) -> None:
    inv = await db.invoice.find_unique(where={"id": invoice_id}, include={"guardian": True})
    if inv is None or inv.status in ("ISSUED", "SENT", "CANCELLED"):
        return
    g = inv.guardian
    provider = get_provider(inv.kind)
    req = InvoiceRequest(
        invoice_id=inv.id,
        kind=inv.kind,
        buyer_name=f"{g.firstName} {g.lastName}",
        buyer_tax_id=decrypt(g.taxIdEncrypted) if g.taxIdEncrypted else None,
        buyer_email=g.email,
        buyer_address=g.billingAddress,
        description=description or "Aidat tahsilatı",
        subtotal=inv.subtotal,
        vat_rate=inv.vatRate,
        total=inv.total,
    )
    try:
        out = await provider.issue(req)
    except Exception as exc:  # sağlayıcı hatası faturayı kaybettirmemeli
        log.exception("fatura kesilemedi %s", inv.id)
        await db.invoice.update(
            where={"id": inv.id},
            data={"status": "FAILED", "error": str(exc)[:500], "attempts": {"increment": 1}, "provider": provider.name},
        )
        return
    await db.invoice.update(
        where={"id": inv.id},
        data={
            "status": "ISSUED",
            "number": out.number,
            "provider": provider.name,
            "providerRef": out.provider_ref,
            "ettn": out.ettn,
            "pdfUrl": out.pdf_url,
            "issuedAt": utcnow(),
            "error": None,
            "attempts": {"increment": 1},
        },
    )


async def retry_failed_invoices() -> int:
    failed = await db.invoice.find_many(where={"status": "FAILED", "attempts": {"lt": MAX_ATTEMPTS}}, take=50)
    for inv in failed:
        await issue_invoice(inv.id)
    return len(failed)
