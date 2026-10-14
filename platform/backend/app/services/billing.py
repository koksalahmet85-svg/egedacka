"""Aidat tahakkuku, tahsilat, gecikme alarmı."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from prisma import Json
from prisma.models import Payment

from ..core.db import db
from ..core.timeutil import as_date, as_dt, month_bounds, utcnow
from ..domain.billing import (
    OpenCharge,
    allocate_payment,
    charge_status,
    compute_charge_amounts,
    due_date_for,
    prorated_first_month,
    reminder_level,
)
from ..domain.money import ZERO, money

OPEN_STATUSES = ["PENDING", "PARTIALLY_PAID", "OVERDUE"]


class BillingError(Exception):
    pass


@dataclass
class GenerationResult:
    period: date
    created: int = 0
    already_existed: int = 0
    skipped_no_payer: list[str] = field(default_factory=list)
    credit_applied_guardians: int = 0


async def generate_monthly_charges(period: date) -> GenerationResult:
    """Aktif aboneliklerden ayın aidat tahakkuklarını üretir. Idempotent: tekrar çalıştırmak güvenli."""
    start, end = month_bounds(period)
    result = GenerationResult(period=start)

    subs = await db.subscription.find_many(
        where={
            "status": "ACTIVE",
            "startsOn": {"lt": as_dt(end)},
            "OR": [{"endsOn": None}, {"endsOn": {"gte": as_dt(start)}}],
        },
        include={"feePlan": True, "athlete": {"include": {"guardians": True}}},
    )
    if not subs:
        return result

    existing = await db.charge.find_many(
        where={"period": as_dt(start), "subscriptionId": {"in": [s.id for s in subs]}},
    )
    existing_ids = {c.subscriptionId for c in existing}
    result.already_existed = len(existing_ids)

    rows: list[dict] = []
    for s in subs:
        if s.id in existing_ids:
            continue
        links = s.athlete.guardians if s.athlete and s.athlete.guardians else []
        payer = next((g for g in links if g.isBillingContact), links[0] if links else None)
        if payer is None:
            result.skipped_no_payer.append(s.athleteId)
            continue

        amounts = compute_charge_amounts(s.feePlan.monthlyAmount, s.discountPct)
        net, gross, discount = amounts.net, amounts.gross, amounts.discount
        sub_start = as_date(s.startsOn)
        if start < sub_start < end:  # ay ortası kayıt → kıstelyevm
            net = prorated_first_month(net, sub_start)
            discount = gross - net

        rows.append(
            {
                "athleteId": s.athleteId,
                "guardianId": payer.guardianId,
                "subscriptionId": s.id,
                "type": "MONTHLY_DUES",
                "period": as_dt(start),
                "description": f"{start:%m/%Y} aidat — {s.feePlan.name}",
                "grossAmount": gross,
                "discountAmount": discount,
                "netAmount": net,
                "dueDate": as_dt(due_date_for(start, s.feePlan.dueDay)),
            }
        )

    if rows:
        # skip_duplicates + @@unique([subscriptionId, period]) eşzamanlı çalıştırmaya karşı korur.
        result.created = await db.charge.create_many(data=rows, skip_duplicates=True)

    # Önceki fazla ödemeleri (alacak bakiyesi) yeni tahakkuklara uygula.
    for guardian_id in {r["guardianId"] for r in rows}:
        if await apply_guardian_credit(guardian_id):
            result.credit_applied_guardians += 1
    return result


async def guardian_credit(guardian_id: str) -> Decimal:
    row = await db.query_first(
        """
        SELECT COALESCE(SUM(p."amount"), 0) - COALESCE((
            SELECT SUM(pa."amount") FROM "PaymentAllocation" pa
            JOIN "Payment" p2 ON p2."id" = pa."paymentId"
            WHERE p2."guardianId" = $1::uuid AND p2."status" = 'COMPLETED'
        ), 0) AS credit
        FROM "Payment" p
        WHERE p."guardianId" = $1::uuid AND p."status" = 'COMPLETED'
        """,
        guardian_id,
    )
    return money(row["credit"] if row else 0)


async def _allocate(
    tx, guardian_id: str, payment_id: str, amount: Decimal, only_charge_ids: list[str] | None
) -> Decimal:
    """Satırları kilitleyip ödemeyi FIFO dağıtır. Artan tutarı döner."""
    # Aynı veliye eşzamanlı iki ödeme gelirse ikincisi bekler (çift dağıtım engellenir).
    await tx.execute_raw(
        """SELECT 1 FROM "Charge" WHERE "guardianId" = $1::uuid
           AND "status" IN ('PENDING','PARTIALLY_PAID','OVERDUE') FOR UPDATE""",
        guardian_id,
    )
    where: dict = {"guardianId": guardian_id, "status": {"in": OPEN_STATUSES}}
    if only_charge_ids:
        where["id"] = {"in": only_charge_ids}
    open_charges = await tx.charge.find_many(where=where)
    by_id = {c.id: c for c in open_charges}

    allocations, leftover = allocate_payment(
        amount,
        [OpenCharge(c.id, as_date(c.dueDate), c.netAmount - c.paidAmount) for c in open_charges],
    )
    today = utcnow().date()
    for a in allocations:
        ch = by_id[a.charge_id]
        new_paid = ch.paidAmount + a.amount
        await tx.paymentallocation.upsert(
            where={"paymentId_chargeId": {"paymentId": payment_id, "chargeId": ch.id}},
            data={
                "create": {"paymentId": payment_id, "chargeId": ch.id, "amount": a.amount},
                "update": {"amount": {"increment": a.amount}},
            },
        )
        await tx.charge.update(
            where={"id": ch.id},
            data={
                "paidAmount": new_paid,
                "status": charge_status(ch.netAmount, new_paid, as_date(ch.dueDate), today),
            },
        )
    return leftover


async def apply_guardian_credit(guardian_id: str) -> bool:
    credit = await guardian_credit(guardian_id)
    if credit <= ZERO:
        return False
    # Alacak en eski kısmi dağıtılmamış ödemelerden gelir; dağıtımı o ödemelere bağla.
    payments = await db.query_raw(
        """
        SELECT p."id", p."amount" - COALESCE(SUM(pa."amount"), 0) AS free
        FROM "Payment" p LEFT JOIN "PaymentAllocation" pa ON pa."paymentId" = p."id"
        WHERE p."guardianId" = $1::uuid AND p."status" = 'COMPLETED'
        GROUP BY p."id" HAVING p."amount" - COALESCE(SUM(pa."amount"), 0) > 0
        ORDER BY p."paidAt"
        """,
        guardian_id,
    )
    async with db.tx() as tx:
        for p in payments:
            leftover = await _allocate(tx, guardian_id, p["id"], money(p["free"]), None)
            if leftover > ZERO:
                break
    return True


async def record_payment(
    *,
    guardian_id: str,
    amount: Decimal,
    method: str,
    paid_at: datetime | None,
    reference: str | None,
    provider_txn_id: str | None,
    received_by_staff_id: str | None,
    charge_ids: list[str] | None,
    note: str | None = None,
) -> tuple[Payment, Decimal]:
    amount = money(amount)
    if amount <= ZERO:
        raise BillingError("Tutar pozitif olmalı")
    if provider_txn_id:
        dup = await db.payment.find_unique(where={"providerTxnId": provider_txn_id})
        if dup:  # sağlayıcı callback'i iki kez gelirse aynı kaydı döndür
            return dup, ZERO

    async with db.tx() as tx:
        data: dict = {
            "guardianId": guardian_id,
            "amount": amount,
            "method": method,
            "reference": reference,
            "providerTxnId": provider_txn_id,
            "note": note,
        }
        if paid_at:
            data["paidAt"] = paid_at
        if received_by_staff_id:
            data["receivedById"] = received_by_staff_id
        payment = await tx.payment.create(data=data)
        leftover = await _allocate(tx, guardian_id, payment.id, amount, charge_ids)
    return payment, leftover


@dataclass
class OverdueResult:
    marked_overdue: int = 0
    notifications_queued: int = 0
    escalations: int = 0


TEMPLATES = {1: "dues_reminder_soft", 2: "dues_reminder_link", 3: "dues_escalation"}


async def process_overdue(today: date | None = None) -> OverdueResult:
    """Günlük job: vadesi geçenleri OVERDUE yap, kademeli hatırlatma kuyruğa al."""
    today = today or utcnow().date()
    res = OverdueResult()
    charges = await db.charge.find_many(
        where={"status": {"in": OPEN_STATUSES}, "dueDate": {"lt": as_dt(today)}},
        include={"guardian": {"include": {"user": True}}, "athlete": True},
    )
    notes: list[dict] = []
    for c in charges:
        level = reminder_level(as_date(c.dueDate), today)
        update: dict = {}
        if c.status != "OVERDUE":
            update["status"] = "OVERDUE"
            res.marked_overdue += 1
        if level > c.reminderLevel:
            update["reminderLevel"] = level
            g = c.guardian
            outstanding = c.netAmount - c.paidAmount
            payload = {
                "guardianName": f"{g.firstName} {g.lastName}",
                "athleteName": f"{c.athlete.firstName} {c.athlete.lastName}",
                "description": c.description,
                "amount": str(outstanding),
                "dueDate": as_date(c.dueDate).isoformat(),
                "daysLate": (today - as_date(c.dueDate)).days,
            }
            notes.append(
                {
                    "channel": g.preferredChannel if g.preferredChannel in ("WHATSAPP", "SMS", "EMAIL") else "WHATSAPP",
                    "toAddress": g.email if g.preferredChannel == "EMAIL" and g.email else g.phone,
                    "recipientUserId": g.userId,
                    "template": TEMPLATES[level],
                    "payload": Json(payload),
                    "dedupeKey": f"overdue:{c.id}:L{level}",
                }
            )
            if level == 3:
                res.escalations += 1
                notes.append(
                    {
                        "channel": "IN_APP",
                        "toAddress": "finance",
                        "template": "finance_escalation",
                        "payload": Json({**payload, "chargeId": c.id, "guardianPhone": g.phone}),
                        "dedupeKey": f"overdue:{c.id}:L3:finance",
                    }
                )
        if update:
            await db.charge.update(where={"id": c.id}, data=update)
    if notes:
        res.notifications_queued = await db.notification.create_many(data=notes, skip_duplicates=True)
    return res


async def guardian_statement(guardian_id: str) -> dict:
    charges = await db.charge.find_many(
        where={"guardianId": guardian_id, "status": {"not_in": ["CANCELLED"]}},
        order={"dueDate": "desc"},
        take=36,
        include={"athlete": True},
    )
    outstanding = sum((c.netAmount - c.paidAmount for c in charges if c.status in OPEN_STATUSES), ZERO)
    return {
        "guardianId": guardian_id,
        "outstanding": money(outstanding),
        "credit": await guardian_credit(guardian_id),
        "charges": charges,
    }
