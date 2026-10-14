"""Finans & muhasebe: aidat planı, abonelik, tahakkuk, tahsilat, fatura, gider, gelir-gider."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from ..core.audit import audit
from ..core.db import db
from ..core.deps import Finance, Management
from ..core.timeutil import as_dt, utcnow
from ..domain.billing import sibling_discount_pct
from ..schemas.common import Page
from ..schemas.finance import ChargeIn, ChargeOut, ExpenseIn, FeePlanIn, PaymentIn, PaymentOut, SubscriptionIn, WaiveIn
from ..services import billing, dashboard, invoicing

router = APIRouter(prefix="/finance", tags=["Finans"])


# ── Aidat planları & abonelik ──
@router.get("/fee-plans")
async def fee_plans(_: Finance):
    return await db.feeplan.find_many(where={"isActive": True}, order={"monthlyAmount": "asc"})


@router.post("/fee-plans", status_code=status.HTTP_201_CREATED)
async def create_fee_plan(body: FeePlanIn, _: Management):
    return await db.feeplan.create(data=body.model_dump())


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(body: SubscriptionIn, user: Finance):
    pct, reason = body.discountPct, body.discountReason
    if pct is None:
        link = await db.athleteguardian.find_first(where={"athleteId": body.athleteId, "isBillingContact": True})
        siblings = 0
        if link:
            siblings = await db.subscription.count(
                where={
                    "status": "ACTIVE",
                    "athlete": {"is": {"guardians": {"some": {"guardianId": link.guardianId}}}},
                    "athleteId": {"not": body.athleteId},
                }
            )
        pct = sibling_discount_pct(siblings + 1)
        reason = "SIBLING" if pct else "NONE"
    sub = await db.subscription.create(
        data={
            "athleteId": body.athleteId,
            "feePlanId": body.feePlanId,
            "startsOn": as_dt(body.startsOn),
            "discountPct": pct,
            "discountReason": reason or "NONE",
        }
    )
    await audit(user.id, "subscription.create", "Subscription", sub.id, {"discountPct": str(pct)})
    return sub


# ── Tahakkuk ──
@router.post("/charges/generate-monthly")
async def generate_monthly(period: date, user: Finance):
    """Ayın aidatlarını üretir. Idempotent; job da her ayın 1'inde çağırır."""
    r = await billing.generate_monthly_charges(period)
    await audit(user.id, "charges.generate", "Charge", r.period.isoformat(), {"created": r.created})
    dashboard.invalidate_cache()
    return r


@router.get("/charges", response_model=Page[ChargeOut])
async def list_charges(
    _: Finance,
    status_: Annotated[str | None, Query(alias="status")] = None,
    guardian_id: Annotated[str | None, Query(alias="guardianId")] = None,
    period: date | None = None,
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
):
    where: dict = {}
    if status_:
        where["status"] = status_
    if guardian_id:
        where["guardianId"] = guardian_id
    if period:
        where["period"] = as_dt(period.replace(day=1))
    items = await db.charge.find_many(where=where, skip=skip, take=take, order=[{"dueDate": "asc"}, {"id": "asc"}])
    return Page(items=items, total=await db.charge.count(where=where), skip=skip, take=take)


@router.post("/charges", status_code=status.HTTP_201_CREATED)
async def create_charge(body: ChargeIn, user: Finance):
    """Tek seferlik kalem: kayıt ücreti, kamp, forma vb."""
    c = await db.charge.create(
        data={
            "athleteId": body.athleteId,
            "guardianId": body.guardianId,
            "type": body.type,
            "description": body.description,
            "grossAmount": body.amount,
            "netAmount": body.amount,
            "dueDate": as_dt(body.dueDate),
        }
    )
    await audit(user.id, "charge.create", "Charge", c.id)
    return c


@router.post("/charges/{charge_id}/waive")
async def waive(charge_id: str, body: WaiveIn, user: Management):
    """Borç silme yalnızca yönetici; neden zorunlu ve denetim kaydına düşer."""
    c = await db.charge.find_unique(where={"id": charge_id})
    if c is None:
        raise HTTPException(404, "Tahakkuk bulunamadı")
    if c.paidAmount > 0:
        raise HTTPException(409, "Kısmen ödenmiş kalem silinemez; kalan tutar için indirim kalemi açın")
    c = await db.charge.update(where={"id": charge_id}, data={"status": "WAIVED"})
    await audit(user.id, "charge.waive", "Charge", charge_id, {"reason": body.reason})
    dashboard.invalidate_cache()
    return c


@router.get("/guardians/{guardian_id}/statement")
async def statement(guardian_id: str, _: Finance):
    return await billing.guardian_statement(guardian_id)


# ── Tahsilat & fatura ──
@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(body: PaymentIn, user: Finance, bg: BackgroundTasks):
    try:
        payment, leftover = await billing.record_payment(
            guardian_id=body.guardianId,
            amount=body.amount,
            method=body.method,
            paid_at=body.paidAt,
            reference=body.reference,
            provider_txn_id=None,
            received_by_staff_id=user.staff_id,
            charge_ids=body.chargeIds,
            note=body.note,
        )
    except billing.BillingError as e:
        raise HTTPException(422, str(e))
    await audit(user.id, "payment.create", "Payment", payment.id, {"amount": str(body.amount)})
    dashboard.invalidate_cache()
    if body.issueInvoice:
        # Fatura entegratörü yavaş olabilir; yanıtı bekletmeden arka planda kes.
        bg.add_task(invoicing.create_invoice_for_payment, payment.id)
    return PaymentOut(
        id=payment.id,
        guardianId=payment.guardianId,
        amount=payment.amount,
        method=payment.method,
        paidAt=payment.paidAt,
        unallocated=leftover,
        invoiceId=None,
    )


@router.post("/payments/{payment_id}/refund")
async def refund(payment_id: str, user: Management):
    p = await db.payment.find_unique(where={"id": payment_id}, include={"allocations": True})
    if p is None or p.status != "COMPLETED":
        raise HTTPException(404, "İade edilecek ödeme yok")
    today = utcnow().date()
    async with db.tx() as tx:
        for a in p.allocations or []:
            ch = await tx.charge.find_unique(where={"id": a.chargeId})
            assert ch is not None
            new_paid = ch.paidAmount - a.amount
            await tx.charge.update(
                where={"id": ch.id},
                data={
                    "paidAmount": new_paid,
                    "status": billing.charge_status(ch.netAmount, new_paid, ch.dueDate.date(), today),
                },
            )
        await tx.paymentallocation.delete_many(where={"paymentId": p.id})
        p = await tx.payment.update(where={"id": p.id}, data={"status": "REFUNDED"})
    await audit(user.id, "payment.refund", "Payment", payment_id)
    dashboard.invalidate_cache()
    return p


@router.get("/invoices")
async def invoices(_: Finance, status_: Annotated[str | None, Query(alias="status")] = None, take: int = 50):
    where = {"status": status_} if status_ else {}
    return await db.invoice.find_many(where=where, order={"createdAt": "desc"}, take=min(take, 200))


@router.post("/invoices/{invoice_id}/retry")
async def retry_invoice(invoice_id: str, _: Finance):
    await invoicing.issue_invoice(invoice_id)
    return await db.invoice.find_unique(where={"id": invoice_id})


# ── Gider ──
@router.post("/expenses", status_code=status.HTTP_201_CREATED)
async def create_expense(body: ExpenseIn, user: Finance):
    data = body.model_dump(exclude_none=True)
    data["incurredOn"] = as_dt(body.incurredOn)
    if user.staff_id:
        data["createdById"] = user.staff_id
    e = await db.expense.create(data=data)
    dashboard.invalidate_cache()
    return e


@router.get("/pnl")
async def pnl(_: Finance, months: int = Query(12, ge=1, le=36)):
    """Aylık nakit esaslı gelir-gider (v_monthly_cashflow görünümü)."""
    return await db.query_raw(
        """SELECT to_char(month, 'YYYY-MM') AS month, income::float8, expense::float8, ad_spend::float8, net::float8
           FROM "v_monthly_cashflow"
           WHERE month >= date_trunc('month', now()) - make_interval(months => $1::int - 1)
           ORDER BY month""",
        months,
    )


@router.get("/aging")
async def aging(_: Finance):
    """Alacak yaşlandırma: 0-30 / 31-60 / 61-90 / 90+ gün."""
    return await db.query_raw(
        """
        SELECT CASE WHEN CURRENT_DATE - "dueDate" <= 30 THEN '0-30'
                    WHEN CURRENT_DATE - "dueDate" <= 60 THEN '31-60'
                    WHEN CURRENT_DATE - "dueDate" <= 90 THEN '61-90'
                    ELSE '90+' END AS bucket,
               COUNT(*)::int AS charges, COUNT(DISTINCT "guardianId")::int AS families,
               SUM("netAmount" - "paidAmount")::float8 AS amount
        FROM "Charge" WHERE "status" = 'OVERDUE'
        GROUP BY 1 ORDER BY MIN(CURRENT_DATE - "dueDate")
        """
    )
