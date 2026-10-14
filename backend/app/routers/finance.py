"""Finans & muhasebe: aidat planları, abonelik, fatura, tahsilat, gider, nakit akışı."""
from datetime import UTC, date, datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.db import get_conn, rows
from ..core.security import FINANCE_ROLES, CurrentUser, Role, require
from ..services import billing

router = APIRouter(prefix="/finance", tags=["finance"])


class FeePlanIn(BaseModel):
    name: str
    monthly_amount: float = Field(ge=0)
    vat_rate: float = 20
    sibling_discount_pct: float = Field(10, ge=0, le=100)


class SubscriptionIn(BaseModel):
    athlete_id: int
    guardian_id: int
    fee_plan_id: int
    discount_pct: float = Field(0, ge=0, le=100)
    discount_reason: str | None = None
    billing_day: int = Field(1, ge=1, le=28)
    start_date: date


class PaymentIn(BaseModel):
    guardian_id: int
    invoice_id: int | None = None
    amount: float = Field(gt=0)
    method: str = Field(pattern="^(CASH|BANK_TRANSFER|CREDIT_CARD|ONLINE)$")
    paid_at: datetime | None = None
    note: str | None = None


class ExpenseIn(BaseModel):
    category: str = Field(pattern="^(FACILITY_RENT|EQUIPMENT|TRAVEL|LEAGUE_FEES|MARKETING|UTILITIES|TAX|OTHER)$")
    amount: float = Field(ge=0)
    vat_amount: float = 0
    spent_at: date
    vendor: str | None = None
    description: str | None = None
    campaign_id: int | None = None


@router.get("/fee-plans")
async def fee_plans(_: CurrentUser = Depends(require(*FINANCE_ROLES, Role.MANAGER)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch("SELECT * FROM fee_plans WHERE is_active ORDER BY monthly_amount"))


@router.post("/fee-plans", status_code=201)
async def create_fee_plan(data: FeePlanIn, _: CurrentUser = Depends(require(Role.ADMIN)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO fee_plans (name, monthly_amount, vat_rate, sibling_discount_pct)
           VALUES ($1,$2,$3,$4) RETURNING id""", *data.model_dump().values())}


@router.post("/subscriptions", status_code=201)
async def create_subscription(data: SubscriptionIn, _: CurrentUser = Depends(require(*FINANCE_ROLES)),
                              conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO subscriptions (athlete_id, guardian_id, fee_plan_id, discount_pct, discount_reason,
               billing_day, start_date) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        *data.model_dump().values())}


@router.post("/subscriptions/{sub_id}/pause")
async def pause(sub_id: int, until: date, _: CurrentUser = Depends(require(*FINANCE_ROLES)),
                conn: asyncpg.Connection = Depends(get_conn)):
    """Dondurma (sakatlık/sınav): until tarihine kadar fatura kesilmez."""
    await conn.execute("UPDATE subscriptions SET paused_until=$2 WHERE id=$1", sub_id, until)
    return {"paused_until": until}


@router.post("/invoices/run/{period}")
async def run_invoices(period: date, _: CurrentUser = Depends(require(*FINANCE_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """Dönem faturalarını kes. Worker her ayın 1'inde otomatik çağırır; elle tekrar çağırmak güvenli."""
    return await billing.generate_monthly_invoices(conn, period)


@router.get("/invoices")
async def list_invoices(status: str | None = None, overdue: bool = False, guardian_id: int | None = None,
                        period: date | None = None, limit: int = Query(100, le=500), offset: int = 0,
                        _: CurrentUser = Depends(require(*FINANCE_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT b.*, g.full_name AS guardian, g.phone, a.first_name || ' ' || a.last_name AS athlete
           FROM v_invoice_balance b JOIN guardians g ON g.id = b.guardian_id
           LEFT JOIN athletes a ON a.id = b.athlete_id
           WHERE ($1::invoice_status IS NULL OR b.status=$1) AND (NOT $2 OR b.is_overdue)
             AND ($3::int IS NULL OR b.guardian_id=$3) AND ($4::date IS NULL OR b.period=$4)
           ORDER BY b.days_overdue DESC, b.due_date LIMIT $5 OFFSET $6""",
        status, overdue, guardian_id, period, limit, offset))


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, _: CurrentUser = Depends(require(*FINANCE_ROLES)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    inv = await conn.fetchrow("SELECT * FROM invoices WHERE id=$1", invoice_id)
    if not inv:
        raise HTTPException(404, "Fatura yok")
    return dict(inv) | {
        "lines": rows(await conn.fetch("SELECT * FROM invoice_lines WHERE invoice_id=$1", invoice_id)),
        "payments": rows(await conn.fetch("SELECT * FROM payments WHERE invoice_id=$1 ORDER BY paid_at", invoice_id)),
        "reminders": rows(await conn.fetch("SELECT * FROM payment_reminders WHERE invoice_id=$1", invoice_id)),
    }


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: int, reason: str, user: CurrentUser = Depends(require(Role.ADMIN)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """Tahsilatı olan fatura iptal edilemez (önce iade). İz kaydı tutulur."""
    async with conn.transaction():
        ok = await conn.fetchval(
            "UPDATE invoices SET status='CANCELLED' WHERE id=$1 AND paid_amount = 0 AND status <> 'CANCELLED' RETURNING id",
            invoice_id)
        if not ok:
            raise HTTPException(409, "Tahsilatı olan veya zaten iptal edilmiş fatura")
        await conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity, entity_id, diff) VALUES ($1,'invoice.cancel','invoice',$2,$3::jsonb)",
            user.id, str(invoice_id), {"reason": reason})
    return {"cancelled": True}


@router.post("/payments", status_code=201)
async def create_payment(data: PaymentIn, user: CurrentUser = Depends(require(*FINANCE_ROLES)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """Elden/havale tahsilat → makbuz no üretilir, veliye SMS kuyruğa girer, fatura statüsü trigger ile güncellenir."""
    try:
        return await billing.record_payment(
            conn, guardian_id=data.guardian_id, invoice_id=data.invoice_id, amount=data.amount,
            method=data.method, paid_at=data.paid_at or datetime.now(UTC), note=data.note, recorded_by=user.staff_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/reminders/run")
async def run_reminders(_: CurrentUser = Depends(require(*FINANCE_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return await billing.run_payment_reminders(conn, date.today())


@router.get("/overdue/guardians")
async def overdue_by_guardian(_: CurrentUser = Depends(require(*FINANCE_ROLES)),
                              conn: asyncpg.Connection = Depends(get_conn)):
    """Tahsilat ekibinin arama listesi: veli bazında toplam borç, en eski gecikme önde."""
    return rows(await conn.fetch(
        """SELECT g.id, g.full_name, g.phone, COUNT(*) AS invoices, SUM(b.balance)::float8 AS balance,
                  MAX(b.days_overdue) AS max_days
           FROM v_invoice_balance b JOIN guardians g ON g.id = b.guardian_id
           WHERE b.is_overdue AND b.balance > 0 GROUP BY g.id ORDER BY max_days DESC, balance DESC"""))


@router.post("/expenses", status_code=201)
async def create_expense(data: ExpenseIn, _: CurrentUser = Depends(require(*FINANCE_ROLES, Role.MARKETING)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO expenses (category, amount, vat_amount, spent_at, vendor, description, campaign_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""", *data.model_dump().values())}


@router.get("/cashflow")
async def cashflow(date_from: date, date_to: date, _: CurrentUser = Depends(require(*FINANCE_ROLES, Role.MANAGER)),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Aylık gelir-gider dengesi, kategori kırılımlı (nakit esaslı)."""
    return rows(await conn.fetch(
        """SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS month, direction, category,
                  SUM(amount)::float8 AS amount
           FROM v_cash_movements WHERE day BETWEEN $1 AND $2 GROUP BY 1,2,3 ORDER BY 1,2,3""",
        date_from, date_to))


@router.get("/team-profitability")
async def team_profitability(date_from: date, date_to: date, _: CurrentUser = Depends(require(Role.ADMIN)),
                             conn: asyncpg.Connection = Depends(get_conn)):
    """Takım bazında katkı payı: tahsil edilen aidat − (koç saat maliyeti + saha maliyeti).
    Hangi yaş grubunun kulübü sübvanse ettiğini gösterir (fiyatlama kararı için)."""
    return rows(await conn.fetch(
        """WITH rev AS (
             SELECT ct.team_id, SUM(p.amount) AS revenue
             FROM payments p JOIN invoices i ON i.id = p.invoice_id
             JOIN v_athlete_current_team ct ON ct.athlete_id = i.athlete_id
             WHERE p.paid_at::date BETWEEN $1 AND $2 GROUP BY 1),
           cost AS (
             SELECT s.team_id,
                    SUM(EXTRACT(EPOCH FROM s.ends_at - s.starts_at) / 3600 * f.hourly_cost) AS facility_cost,
                    SUM(EXTRACT(EPOCH FROM s.ends_at - s.starts_at) / 3600 *
                        COALESCE(st.hourly_rate, st.monthly_salary / 160, 0)) AS coach_cost
             FROM training_sessions s JOIN facilities f ON f.id = s.facility_id JOIN staff st ON st.id = s.coach_id
             WHERE s.status = 'COMPLETED' AND s.starts_at::date BETWEEN $1 AND $2 GROUP BY 1)
           SELECT t.id, t.name, COALESCE(r.revenue,0)::float8 AS revenue,
                  COALESCE(c.facility_cost,0)::float8 AS facility_cost, COALESCE(c.coach_cost,0)::float8 AS coach_cost,
                  (COALESCE(r.revenue,0) - COALESCE(c.facility_cost,0) - COALESCE(c.coach_cost,0))::float8 AS contribution
           FROM teams t LEFT JOIN rev r ON r.team_id = t.id LEFT JOIN cost c ON c.team_id = t.id
           JOIN seasons se ON se.id = t.season_id AND se.is_active
           ORDER BY contribution""", date_from, date_to))
