"""Aidat faturalandırma, tahsilat ve gecikme alarmları.

Her fonksiyon idempotent: aynı dönem için iki kez çalıştırmak ikinci fatura,
ikinci makbuz ya da ikinci hatırlatma üretmez (DB unique kısıtları garanti eder).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import asyncpg

from ..core.config import get_settings
from .analytics import invoice_amounts
from .notify import enqueue

MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
             "Eylül", "Ekim", "Kasım", "Aralık"]


def first_of_month(d: date) -> date:
    return d.replace(day=1)


async def next_invoice_number(conn: asyncpg.Connection, year: int) -> str:
    seq = await conn.fetchval("SELECT nextval('invoice_number_seq')")
    return f"EAF{year}{seq:09d}"


async def next_receipt_number(conn: asyncpg.Connection, year: int) -> str:
    seq = await conn.fetchval("SELECT nextval('receipt_number_seq')")
    return f"MKB{year}{seq:08d}"


# Aktif abonelikler + kardeş sırası tek sorguda. Kardeş sırası: aynı velinin o dönem
# faturalanacak abonelikleri içinde, en eski kayıt 1. çocuk sayılır.
_BILLABLE_SQL = """
WITH billable AS (
  SELECT s.*, fp.monthly_amount, fp.vat_rate, fp.sibling_discount_pct, fp.name AS plan_name,
         a.first_name || ' ' || a.last_name AS athlete_name,
         row_number() OVER (PARTITION BY s.guardian_id ORDER BY s.start_date, s.id) AS sibling_rank
  FROM subscriptions s
  JOIN fee_plans fp ON fp.id = s.fee_plan_id
  JOIN athletes a   ON a.id = s.athlete_id
  WHERE s.start_date <= $2                         -- dönem sonuna kadar başlamış
    AND (s.end_date IS NULL OR s.end_date >= $1)   -- dönem başından önce bitmemiş
    AND (s.paused_until IS NULL OR s.paused_until < $1)
    AND a.status IN ('ACTIVE', 'FROZEN')
)
SELECT b.* FROM billable b
WHERE NOT EXISTS (SELECT 1 FROM invoices i WHERE i.subscription_id = b.id AND i.period = $1)
"""


async def generate_monthly_invoices(conn: asyncpg.Connection, period: date) -> dict:
    """Dönem (ayın 1'i) için tüm aidat faturalarını keser. Tekrar çalıştırmak güvenlidir."""
    period = first_of_month(period)
    period_end = (period + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    due_days = get_settings().invoice_due_days
    created: list[int] = []
    async with conn.transaction():
        subs = await conn.fetch(_BILLABLE_SQL, period, period_end)
        for s in subs:
            amt = invoice_amounts(s["monthly_amount"], s["vat_rate"], s["discount_pct"],
                                  s["sibling_discount_pct"], s["sibling_rank"])
            issue = max(period.replace(day=s["billing_day"]), period)
            number = await next_invoice_number(conn, period.year)
            inv_id = await conn.fetchval(
                """INSERT INTO invoices (number, subscription_id, guardian_id, athlete_id, period,
                       issue_date, due_date, subtotal, vat_amount, total, status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'ISSUED')
                   ON CONFLICT (subscription_id, period) DO NOTHING RETURNING id""",
                number, s["id"], s["guardian_id"], s["athlete_id"], period, issue,
                issue + timedelta(days=due_days), amt.subtotal, amt.vat, amt.total)
            if inv_id is None:
                continue
            desc = f"{s['athlete_name']} — {MONTHS_TR[period.month - 1]} {period.year} aidatı ({s['plan_name']})"
            unit_ex_vat = (amt.gross / (1 + s["vat_rate"] / 100)).quantize(Decimal("0.01"))
            await conn.execute(
                """INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price, discount,
                       vat_rate, line_total) VALUES ($1,$2,1,$3,$4,$5,$6)""",
                inv_id, desc, unit_ex_vat, unit_ex_vat - amt.subtotal, s["vat_rate"], amt.total)
            created.append(inv_id)
    return {"period": period.isoformat(), "created": len(created), "invoice_ids": created}


async def record_payment(conn: asyncpg.Connection, *, guardian_id: int, amount: Decimal, method: str,
                         paid_at: datetime, invoice_id: int | None = None, provider_ref: str | None = None,
                         note: str | None = None, recorded_by: int | None = None) -> dict:
    """Tahsilat kaydeder ve makbuz no üretir. provider_ref tekrar gelirse mevcut kaydı döner."""
    async with conn.transaction():
        if provider_ref:
            existing = await conn.fetchrow("SELECT * FROM payments WHERE provider_ref=$1", provider_ref)
            if existing:
                return dict(existing) | {"duplicate": True}
        if invoice_id is not None:
            inv = await conn.fetchrow(
                "SELECT guardian_id, status FROM invoices WHERE id=$1 FOR UPDATE", invoice_id)
            if inv is None or inv["guardian_id"] != guardian_id:
                raise ValueError("Fatura bu veliye ait değil")
            if inv["status"] == "CANCELLED":
                raise ValueError("İptal edilmiş faturaya tahsilat yapılamaz")
        receipt = await next_receipt_number(conn, paid_at.year)
        rec = await conn.fetchrow(
            """INSERT INTO payments (invoice_id, guardian_id, amount, method, paid_at, receipt_no,
                   provider_ref, note, recorded_by_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
            invoice_id, guardian_id, amount, method, paid_at, receipt, provider_ref, note, recorded_by)
        phone = await conn.fetchval("SELECT phone FROM guardians WHERE id=$1", guardian_id)
        await enqueue(conn, "SMS", phone, "payment_receipt",
                      {"receipt_no": receipt, "amount": str(amount)}, f"receipt:{receipt}")
    return dict(rec) | {"duplicate": False}


# Hatırlatma takvimi: vade gününe göre gün farkı → seviye.
REMINDER_SCHEDULE: list[tuple[int, str, str]] = [
    (-3, "DUE_SOON", "WHATSAPP"),
    (1, "OVERDUE_1", "WHATSAPP"),
    (7, "OVERDUE_7", "SMS"),
    (15, "OVERDUE_15", "SMS"),
    (30, "OVERDUE_30", "EMAIL"),  # + yöneticiye eskalasyon
]


async def run_payment_reminders(conn: asyncpg.Connection, today: date) -> dict:
    """Gecikme alarmları. Ödeme hatırlatması işlemsel iletidir (İYS onayı gerekmez).

    Bir job günü kaçırırsa ertesi gün seviyeyi yine yakalar (>= karşılaştırma),
    ama aynı seviye asla iki kez gönderilmez (payment_reminders unique).
    """
    sent = 0
    escalations: list[int] = []
    async with conn.transaction():
        for offset, level, channel in REMINDER_SCHEDULE:
            # Bir sonraki seviyenin eşiğine gelmiş faturaya eski seviye gönderilmez.
            nxt = next((o for o, *_ in REMINDER_SCHEDULE if o > offset), None)
            rows = await conn.fetch(
                """SELECT b.id, b.number, b.balance, b.due_date, g.phone, g.email, g.full_name
                   FROM v_invoice_balance b JOIN guardians g ON g.id = b.guardian_id
                   WHERE b.balance > 0 AND b.status IN ('ISSUED','PARTIALLY_PAID')
                     AND ($1::date - b.due_date) >= $2
                     AND ($3::int IS NULL OR ($1::date - b.due_date) < $3)""",
                today, offset, nxt)
            for r in rows:
                inserted = await conn.fetchval(
                    """INSERT INTO payment_reminders (invoice_id, level, channel) VALUES ($1,$2,$3)
                       ON CONFLICT (invoice_id, level) DO NOTHING RETURNING id""",
                    r["id"], level, channel)
                if not inserted:
                    continue
                # E-postası olmayan veliye e-posta seviyesi SMS'e düşer.
                if channel == "EMAIL" and not r["email"]:
                    channel_used, recipient = "SMS", r["phone"]
                else:
                    channel_used, recipient = channel, r["email"] if channel == "EMAIL" else r["phone"]
                await enqueue(conn, channel_used, recipient, f"payment_{level.lower()}",
                              {"name": r["full_name"], "invoice": r["number"], "balance": str(r["balance"]),
                               "due_date": r["due_date"].isoformat()},
                              f"reminder:{r['id']}:{level}")
                sent += 1
                if level == "OVERDUE_30":
                    escalations.append(r["id"])
    return {"sent": sent, "escalated_invoice_ids": escalations}
