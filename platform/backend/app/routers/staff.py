"""Koç & İK: personel, vardiya, puantaj, izin, bordro."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..core.audit import audit
from ..core.crypto import encrypt
from ..core.db import db
from ..core.deps import Finance, Management, Staff
from ..core.timeutil import as_dt, month_bounds, utcnow
from ..schemas.people import LeaveIn, PayrollBuild, ShiftIn, StaffIn, StaffOut
from ..services import payroll as payroll_svc
from ..services.training import clock

router = APIRouter(prefix="/hr", tags=["Koç & İK"])


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(_: Staff, department: str | None = None, active: bool = True):
    where: dict = {"isActive": active}
    if department:
        where["department"] = department
    return await db.staff.find_many(where=where, order=[{"department": "asc"}, {"lastName": "asc"}])


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def create_staff(body: StaffIn, user: Management):
    data = body.model_dump(exclude={"iban", "hireDate", "licenseExpiresOn"}, exclude_none=True)
    data["hireDate"] = as_dt(body.hireDate)
    if body.licenseExpiresOn:
        data["licenseExpiresOn"] = as_dt(body.licenseExpiresOn)
    if body.iban:
        data["ibanEncrypted"] = encrypt(body.iban.replace(" ", ""))
    s = await db.staff.create(data=data)
    await audit(user.id, "staff.create", "Staff", s.id)
    return s


@router.get("/staff/expiring-licenses")
async def expiring_licenses(_: Management, days: int = Query(60, ge=1, le=365)):
    """Antrenör lisans vizesi yaklaşanlar (federasyon cezası riskine karşı)."""
    limit = as_dt(date.today() + timedelta(days=days))
    return await db.staff.find_many(
        where={"isActive": True, "licenseExpiresOn": {"lte": limit}}, order={"licenseExpiresOn": "asc"}
    )


@router.get("/staff/{staff_id}/schedule")
async def staff_schedule(staff_id: str, _: Staff, week_start: Annotated[date, Query(alias="weekStart")]):
    """Koçun haftalık takvimi: antrenmanlar + vardiyalar tek listede."""
    lo, hi = as_dt(week_start), as_dt(week_start + timedelta(days=7))
    sessions = await db.trainingsession.find_many(
        where={"coachId": staff_id, "startsAt": {"gte": lo, "lt": hi}, "status": {"not": "CANCELLED"}},
        include={"team": True, "court": {"include": {"venue": True}}},
        order={"startsAt": "asc"},
    )
    shifts = await db.shift.find_many(
        where={"staffId": staff_id, "startsAt": {"gte": lo, "lt": hi}, "status": {"not": "CANCELLED"}},
        order={"startsAt": "asc"},
    )
    return {"sessions": sessions, "shifts": shifts}


@router.post("/shifts", status_code=status.HTTP_201_CREATED)
async def create_shift(body: ShiftIn, _: Management):
    if body.endsAt <= body.startsAt:
        raise HTTPException(422, "Bitiş başlangıçtan sonra olmalı")
    clash = await db.shift.find_first(
        where={
            "staffId": body.staffId,
            "status": {"not": "CANCELLED"},
            "startsAt": {"lt": body.endsAt},
            "endsAt": {"gt": body.startsAt},
        }
    )
    if clash:
        raise HTTPException(409, f"Personelin çakışan vardiyası var ({clash.startsAt:%d.%m %H:%M})")
    return await db.shift.create(data=body.model_dump(exclude_none=True))


@router.post("/timesheet/clock/{action}")
async def clock_in_out(action: str, user: Staff):
    if action not in ("in", "out") or not user.staff_id:
        raise HTTPException(400, "Geçersiz işlem")
    try:
        return await clock(user.staff_id, action)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/timesheet")
async def timesheet(
    _: Staff,
    period: date,
    staff_id: Annotated[str | None, Query(alias="staffId")] = None,
    pending_only: Annotated[bool, Query(alias="pendingOnly")] = False,
):
    start, end = month_bounds(period)
    where: dict = {"workDate": {"gte": as_dt(start), "lt": as_dt(end)}}
    if staff_id:
        where["staffId"] = staff_id
    if pending_only:
        where["approvedAt"] = None
    return await db.timeentry.find_many(where=where, include={"staff": True, "session": True}, order={"clockIn": "asc"})


@router.post("/timesheet/approve")
async def approve_entries(ids: list[str], user: Management):
    if not user.staff_id:
        raise HTTPException(400, "Onaylayan personel kaydı yok")
    n = await db.timeentry.update_many(
        where={"id": {"in": ids}, "approvedAt": None, "clockOut": {"not": None}},
        data={"approvedById": user.staff_id, "approvedAt": utcnow()},
    )
    return {"approved": n}


@router.post("/leave", status_code=status.HTTP_201_CREATED)
async def request_leave(body: LeaveIn, user: Staff):
    if not user.staff_id:
        raise HTTPException(400, "Personel kaydı yok")
    return await db.leaverequest.create(
        data={
            "staffId": user.staff_id,
            "type": body.type,
            "startDate": as_dt(body.startDate),
            "endDate": as_dt(body.endDate),
            "note": body.note,
        }
    )


@router.post("/leave/{leave_id}/{decision}")
async def decide_leave(leave_id: str, decision: str, _: Management):
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "approve | reject")
    return await db.leaverequest.update(
        where={"id": leave_id}, data={"status": "APPROVED" if decision == "approve" else "REJECTED"}
    )


@router.post("/payroll/build")
async def build_payroll(body: PayrollBuild, user: Finance):
    try:
        run = await payroll_svc.build_payroll(
            body.period,
            {k: str(v) for k, v in body.bonuses.items()},
            {k: str(v) for k, v in body.deductions.items()},
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    await audit(user.id, "payroll.build", "PayrollRun", run.id)
    return await db.payrollrun.find_unique(where={"id": run.id}, include={"payslips": {"include": {"staff": True}}})


@router.post("/payroll/{run_id}/approve")
async def approve_payroll(run_id: str, user: Management):
    run = await db.payrollrun.update(where={"id": run_id}, data={"status": "APPROVED", "approvedAt": utcnow()})
    await audit(user.id, "payroll.approve", "PayrollRun", run_id)
    return run


@router.post("/payroll/{run_id}/paid")
async def payroll_paid(run_id: str, user: Finance):
    try:
        run = await payroll_svc.mark_paid(run_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    await audit(user.id, "payroll.paid", "PayrollRun", run_id)
    return run


@router.get("/coach-load")
async def coach_load(_: Management, week_start: Annotated[date, Query(alias="weekStart")]):
    """Koç başına haftalık saat — aşırı yük / dengesiz dağılım tespiti."""
    return await db.query_raw(
        """
        SELECT st."id", st."firstName" || ' ' || st."lastName" AS name,
               COUNT(s."id")::int AS sessions,
               ROUND(COALESCE(SUM(EXTRACT(EPOCH FROM (s."endsAt" - s."startsAt")) / 3600), 0)::numeric, 1)::float8 AS hours
        FROM "Staff" st
        LEFT JOIN "TrainingSession" s ON s."coachId" = st."id" AND s."status" <> 'CANCELLED'
             AND s."startsAt" >= $1::timestamp AND s."startsAt" < $1::timestamp + interval '7 days'
        WHERE st."department" = 'COACHING' AND st."isActive"
        GROUP BY st."id" ORDER BY hours DESC
        """,
        datetime.combine(week_start, datetime.min.time()).isoformat(),
    )
