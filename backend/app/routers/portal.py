"""Veli portalı — yalnız kendi çocuklarının verisi (guardian_id JWT'den gelir, parametreden değil)."""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from ..core.config import get_settings
from ..core.db import get_conn, rows
from ..core.security import CurrentUser, Role, require

router = APIRouter(prefix="/portal", tags=["portal"])
guardian_only = require(Role.GUARDIAN)


@router.get("/children")
async def children(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT a.id, a.first_name, a.last_name, a.birth_date, a.status, ct.team_name,
                  a.health_report_expires_at
           FROM athlete_guardians ag JOIN athletes a ON a.id = ag.athlete_id
           LEFT JOIN v_athlete_current_team ct ON ct.athlete_id = a.id
           WHERE ag.guardian_id = $1 ORDER BY a.birth_date""", user.guardian_id))


@router.get("/schedule")
async def schedule(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    """Çocukların önümüzdeki 14 günlük antrenman takvimi (iptaller dahil — veli bilgilensin)."""
    return rows(await conn.fetch(
        """SELECT s.id, s.starts_at, s.ends_at, s.status, s.cancel_reason, s.type, t.name AS team_name,
                  f.name AS facility, a.first_name AS child
           FROM athlete_guardians ag
           JOIN v_athlete_current_team ct ON ct.athlete_id = ag.athlete_id
           JOIN athletes a ON a.id = ag.athlete_id
           JOIN training_sessions s ON s.team_id = ct.team_id
           JOIN teams t ON t.id = s.team_id JOIN facilities f ON f.id = s.facility_id
           WHERE ag.guardian_id = $1 AND s.starts_at BETWEEN now() AND now() + interval '14 days'
           ORDER BY s.starts_at""", user.guardian_id))


@router.get("/reports")
async def report_list(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT r.id, r.athlete_id, r.period, r.published_at, r.pdf_url
           FROM performance_reports r JOIN athlete_guardians ag ON ag.athlete_id = r.athlete_id
           WHERE ag.guardian_id = $1 AND r.published_at IS NOT NULL ORDER BY r.period DESC""", user.guardian_id))


@router.get("/reports/{report_id}")
async def report(report_id: int, user: CurrentUser = Depends(guardian_only),
                 conn: asyncpg.Connection = Depends(get_conn)):
    r = await conn.fetchrow(
        """SELECT r.* FROM performance_reports r JOIN athlete_guardians ag ON ag.athlete_id = r.athlete_id
           WHERE r.id = $1 AND ag.guardian_id = $2 AND r.published_at IS NOT NULL""", report_id, user.guardian_id)
    if not r:
        raise HTTPException(404, "Rapor bulunamadı")
    return dict(r)


@router.get("/attendance")
async def attendance(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    """Çocuk başına son 12 haftanın haftalık devam oranı (grafik verisi)."""
    return rows(await conn.fetch(
        """SELECT a.athlete_id, date_trunc('week', s.starts_at AT TIME ZONE $2)::date AS week,
                  COUNT(*) FILTER (WHERE a.status IN ('PRESENT','LATE'))::float8 / COUNT(*) AS rate
           FROM attendances a JOIN training_sessions s ON s.id = a.session_id
           JOIN athlete_guardians ag ON ag.athlete_id = a.athlete_id
           WHERE ag.guardian_id = $1 AND s.status='COMPLETED' AND s.starts_at >= now() - interval '12 weeks'
           GROUP BY 1, 2 ORDER BY 1, 2""", user.guardian_id, get_settings().timezone))


@router.get("/invoices")
async def invoices(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT b.id, b.number, b.period, b.due_date, b.total, b.paid_amount, b.balance, b.status, b.is_overdue
           FROM v_invoice_balance b WHERE b.guardian_id = $1 ORDER BY b.due_date DESC""", user.guardian_id))


@router.get("/payments")
async def payments(user: CurrentUser = Depends(guardian_only), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        "SELECT receipt_no, amount, method, paid_at, invoice_id FROM payments WHERE guardian_id=$1 ORDER BY paid_at DESC",
        user.guardian_id))

