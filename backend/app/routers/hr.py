"""Koç & İK: personel, vardiya, puantaj, bordro taslağı."""
from datetime import date, datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.db import get_conn, rows
from ..core.security import STAFF_ROLES, CurrentUser, Role, require
from ..services import scheduling

router = APIRouter(prefix="/hr", tags=["hr"])
HR_ROLES = (Role.ADMIN, Role.MANAGER)


class StaffIn(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None
    department: str = Field(pattern="^(COACHING|ADMINISTRATION|MARKETING|FINANCE|OPERATIONS)$")
    title: str
    employment_type: str = Field(pattern="^(FULL_TIME|PART_TIME|HOURLY)$")
    monthly_salary: float | None = None
    hourly_rate: float | None = None
    coach_license: str | None = None
    hire_date: date


class ShiftIn(BaseModel):
    staff_id: int
    facility_id: int | None = None
    type: str = Field(pattern="^(TRAINING|ADMIN_DESK|EVENT|GAME_DAY)$")
    starts_at: datetime
    ends_at: datetime
    note: str | None = None


class TimeEntryIn(BaseModel):
    staff_id: int
    clock_in: datetime
    clock_out: datetime


@router.get("/staff")
async def list_staff(department: str | None = None, _: CurrentUser = Depends(require(*STAFF_ROLES)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    # Maaş bilgisi bu listede yok — yalnız /payroll uçlarında, finans rolüne açık.
    return rows(await conn.fetch(
        """SELECT id, first_name, last_name, phone, email, department, title, employment_type, coach_license,
                  hire_date FROM staff
           WHERE terminated_at IS NULL AND ($1::department IS NULL OR department=$1)
           ORDER BY department, last_name""", department))


@router.post("/staff", status_code=201)
async def create_staff(data: StaffIn, _: CurrentUser = Depends(require(Role.ADMIN)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    if data.employment_type == "HOURLY" and not data.hourly_rate:
        raise HTTPException(422, "Saatlik çalışan için hourly_rate zorunlu")
    return {"id": await conn.fetchval(
        """INSERT INTO staff (first_name, last_name, phone, email, department, title, employment_type,
               monthly_salary, hourly_rate, coach_license, hire_date)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id""", *data.model_dump().values())}


@router.get("/staff/{staff_id}/workload")
async def workload(staff_id: int, weeks: int = 8, user: CurrentUser = Depends(require(*STAFF_ROLES)),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Koçun haftalık saha saati — tükenmişlik ve adil dağılım takibi."""
    if user.role == Role.COACH and user.staff_id != staff_id:
        raise HTTPException(403, "Yalnız kendi iş yükünüzü görebilirsiniz")
    return rows(await conn.fetch(
        """SELECT date_trunc('week', starts_at)::date AS week, COUNT(*) AS sessions,
                  SUM(EXTRACT(EPOCH FROM ends_at - starts_at)) / 3600 AS hours
           FROM training_sessions WHERE coach_id=$1 AND status <> 'CANCELLED'
             AND starts_at >= now() - make_interval(weeks => $2)
           GROUP BY 1 ORDER BY 1""", staff_id, weeks))


@router.post("/shifts", status_code=201)
async def create_shift(data: ShiftIn, _: CurrentUser = Depends(require(*HR_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO shifts (staff_id, facility_id, type, starts_at, ends_at, note)
           VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""", *data.model_dump().values())}


@router.get("/shifts")
async def list_shifts(date_from: date, date_to: date, staff_id: int | None = None,
                      user: CurrentUser = Depends(require(*STAFF_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    if user.role not in HR_ROLES:
        staff_id = user.staff_id
    return rows(await conn.fetch(
        """SELECT * FROM shifts WHERE starts_at::date BETWEEN $1 AND $2 AND ($3::int IS NULL OR staff_id=$3)
           ORDER BY starts_at""", date_from, date_to, staff_id))


@router.post("/time-entries", status_code=201)
async def manual_entry(data: TimeEntryIn, user: CurrentUser = Depends(require(*HR_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """İdari düzeltme (örn. turnuva günü). Girişi yapan onaylayan olarak kaydedilir."""
    minutes = int((data.clock_out - data.clock_in).total_seconds() // 60)
    return {"id": await conn.fetchval(
        """INSERT INTO time_entries (staff_id, clock_in, clock_out, minutes, source, approved_by_id, approved_at)
           VALUES ($1,$2,$3,$4,'MANUAL',$5,now()) RETURNING id""",
        data.staff_id, data.clock_in, data.clock_out, minutes, user.staff_id)}


@router.post("/timesheets/{period}/close")
async def close_month(period: date, _: CurrentUser = Depends(require(*HR_ROLES)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    return await scheduling.close_month(conn, period)


@router.get("/timesheets/{period}")
async def timesheets(period: date, _: CurrentUser = Depends(require(*HR_ROLES, Role.ACCOUNTANT)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT ts.*, s.first_name || ' ' || s.last_name AS name, s.employment_type,
                  round(ts.total_minutes / 60.0, 1) AS hours
           FROM timesheets ts JOIN staff s ON s.id = ts.staff_id WHERE ts.period=$1 ORDER BY s.last_name""",
        period.replace(day=1)))


@router.post("/payroll/{period}/draft")
async def draft_payroll(period: date, _: CurrentUser = Depends(require(Role.ADMIN, Role.ACCOUNTANT)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    return {"payrolls": await scheduling.draft_payrolls(conn, period)}


@router.get("/payroll/{period}")
async def payroll(period: date, _: CurrentUser = Depends(require(Role.ADMIN, Role.ACCOUNTANT)),
                  conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT p.*, s.first_name || ' ' || s.last_name AS name, s.department FROM payrolls p
           JOIN staff s ON s.id = p.staff_id WHERE p.period=$1 ORDER BY s.department, s.last_name""",
        period.replace(day=1)))


@router.post("/payroll/{payroll_id}/pay")
async def mark_paid(payroll_id: int, net_pay: float, _: CurrentUser = Depends(require(Role.ADMIN, Role.ACCOUNTANT)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Ödendi işaretle → gider olarak nakit akışına girer, puantaj kilitlenir."""
    async with conn.transaction():
        ts_id = await conn.fetchval(
            """UPDATE payrolls SET status='PAID', paid_at=now(), net_pay=$2
               WHERE id=$1 AND status <> 'PAID' RETURNING COALESCE(timesheet_id, 0)""", payroll_id, net_pay)
        if ts_id is None:
            raise HTTPException(409, "Bordro bulunamadı ya da zaten ödenmiş")
        await conn.execute("UPDATE timesheets SET status='LOCKED' WHERE id=$1", ts_id)
    return {"paid": True}
