"""Aylık bordro taslağı: onaylı puantaj + tamamlanan seanslardan."""

from __future__ import annotations

from datetime import date

from prisma import Json

from ..core.db import db
from ..core.timeutil import as_dt, month_bounds, utcnow
from ..domain.money import ZERO
from ..domain.payroll import PayInput, compute_payslip


async def build_payroll(period: date, bonuses: dict[str, str] | None = None, deductions: dict[str, str] | None = None):
    start, end = month_bounds(period)
    run = await db.payrollrun.upsert(
        where={"period": as_dt(start)},
        data={"create": {"period": as_dt(start)}, "update": {}},
    )
    if run.status != "DRAFT":
        raise ValueError("Onaylanmış bordro yeniden hesaplanamaz")

    # Puantaj ve seans sayıları tek sorguda (N+1 yok).
    agg = await db.query_raw(
        """
        SELECT "staffId" AS staff_id,
               COALESCE(SUM("minutes"), 0)::int AS minutes,
               COUNT(*) FILTER (WHERE "source" = 'SESSION_AUTO')::int AS sessions
        FROM "TimeEntry"
        WHERE "approvedAt" IS NOT NULL AND "workDate" >= $1::date AND "workDate" < $2::date
        GROUP BY "staffId"
        """,
        start.isoformat(),
        end.isoformat(),
    )
    by_staff = {r["staff_id"]: r for r in agg}
    staff = await db.staff.find_many(where={"isActive": True, "hireDate": {"lt": as_dt(end)}})
    bonuses, deductions = bonuses or {}, deductions or {}
    total_gross = total_net = ZERO
    async with db.tx() as tx:
        await tx.payslip.delete_many(where={"payrollRunId": run.id})
        for s in staff:
            a = by_staff.get(s.id, {"minutes": 0, "sessions": 0})
            r = compute_payslip(
                PayInput(
                    pay_type=s.payType,
                    base_salary=s.baseSalary,
                    hourly_rate=s.hourlyRate,
                    session_rate=s.sessionRate,
                    worked_minutes=a["minutes"],
                    session_count=a["sessions"],
                    bonus=bonuses.get(s.id, "0"),
                    deductions=deductions.get(s.id, "0"),
                )
            )
            await tx.payslip.create(
                data={
                    "payrollRunId": run.id,
                    "staffId": s.id,
                    "workedMinutes": a["minutes"],
                    "sessionCount": a["sessions"],
                    "baseAmount": r.base_amount,
                    "variableAmount": r.variable_amount,
                    "bonus": r.gross - r.base_amount - r.variable_amount,
                    "deductions": r.gross - r.net,
                    "gross": r.gross,
                    "net": r.net,
                    "lines": Json(r.lines),
                }
            )
            total_gross += r.gross
            total_net += r.net
        run = await tx.payrollrun.update(where={"id": run.id}, data={"totalGross": total_gross, "totalNet": total_net})
    return run


async def mark_paid(run_id: str):
    """Ödenen bordro gider tablosuna SALARY olarak yansır → kulüp gelir-gider dengesi otomatik."""
    run = await db.payrollrun.find_unique(where={"id": run_id})
    if run is None or run.status != "APPROVED":
        raise ValueError("Yalnızca onaylı bordro ödenebilir")
    async with db.tx() as tx:
        await tx.expense.create(
            data={
                "category": "SALARY",
                "amount": run.totalGross,
                "incurredOn": run.period,
                "description": f"{run.period:%m/%Y} personel maaşları",
                "payrollRunId": run.id,
            }
        )
        return await tx.payrollrun.update(where={"id": run.id}, data={"status": "PAID", "paidAt": utcnow()})
