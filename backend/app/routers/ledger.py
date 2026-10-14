"""Tahsilat defteri içe aktarma ve sezon karşılaştırma."""
from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..core.db import get_conn, rows
from ..core.security import FINANCE_ROLES, CurrentUser, Role, require
from ..services import ledger_store, season_analysis
from ..services.ledger_import import parse_workbook

router = APIRouter(tags=["ledger"])
MAX_UPLOAD = 15 * 1024 * 1024
ANALYSIS_ROLES = (*FINANCE_ROLES, Role.MANAGER)


class SeasonIn(BaseModel):
    name: str
    start_date: date
    end_date: date
    is_active: bool = False


@router.get("/seasons")
async def list_seasons(_: CurrentUser = Depends(require(*ANALYSIS_ROLES, Role.COACH, Role.MARKETING)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch("SELECT * FROM seasons ORDER BY start_date"))


@router.put("/seasons", status_code=200)
async def upsert_season(data: SeasonIn, _: CurrentUser = Depends(require(Role.ADMIN)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Sezon tanımı (ör. 2025-2026: 2025-07-01 → 2026-07-31). Analiz bu aralıkları kullanır."""
    async with conn.transaction():
        if data.is_active:
            await conn.execute("UPDATE seasons SET is_active=false WHERE name <> $1", data.name)
        sid = await conn.fetchval(
            """INSERT INTO seasons (name, start_date, end_date, is_active) VALUES ($1,$2,$3,$4)
               ON CONFLICT (name) DO UPDATE SET start_date=EXCLUDED.start_date, end_date=EXCLUDED.end_date,
                 is_active=EXCLUDED.is_active RETURNING id""",
            data.name, data.start_date, data.end_date, data.is_active)
    return {"id": sid}


@router.post("/ledger/import", status_code=201)
async def import_ledger(file: UploadFile = File(...), user: CurrentUser = Depends(require(*FINANCE_ROLES)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Excel tahsilat defterini içe aktar. Aynı dosyayı tekrar yüklemek güvenli (sayfa bazında değiştirir)."""
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "Yalnız .xlsx dosyası")
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Dosya 15 MB'tan büyük")
    try:
        parsed = parse_workbook(content)
    except Exception as exc:  # bozuk / şifreli xlsx
        raise HTTPException(422, f"Dosya okunamadı: {exc.__class__.__name__}") from None
    if not parsed.sheets:
        raise HTTPException(422, "'AY YY' adlı tahsilat sayfası bulunamadı")
    return await ledger_store.store(conn, parsed, file.filename or "defter.xlsx", content, user.id)


@router.get("/ledger/imports")
async def imports(_: CurrentUser = Depends(require(*ANALYSIS_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT id, file_name, sheets, row_count, jsonb_array_length(anomalies) AS anomaly_count, imported_at
           FROM ledger_imports ORDER BY id DESC LIMIT 50"""))


@router.get("/ledger/anomalies")
async def anomalies(import_id: int | None = None, _: CurrentUser = Depends(require(*FINANCE_ROLES)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Veri kalitesi listesi: düzeltilen tarih, tutar uyuşmazlığı, tanınmayan kanal …"""
    r = await conn.fetchval(
        "SELECT anomalies FROM ledger_imports WHERE ($1::int IS NULL OR id=$1) ORDER BY id DESC LIMIT 1", import_id)
    return r or []


@router.get("/ledger/compare")
async def compare(base: str, target: str, mode: str = Query("economic", pattern="^(economic|cash)$"),
                  _: CurrentUser = Depends(require(*ANALYSIS_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    """İki sezonun tahsilat karşılaştırması. mode=economic: sezonluk peşin ödeme ait olduğu sezona yazılır."""
    try:
        b0, b1 = await ledger_store.season_bounds(conn, base)
        t0, t1 = await ledger_store.season_bounds(conn, target)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    b_rows, t_rows = await ledger_store.load_rows(conn, b0, b1), await ledger_store.load_rows(conn, t0, t1)
    if not b_rows or not t_rows:
        raise HTTPException(404, "Seçilen sezonlarda defter kaydı yok")
    # Sezonluk plan 12 ay kapsar: sezon bitişinden geriye 12 ay.
    return season_analysis.compare(base, b_rows, target, t_rows, mode,
                                   season_analysis.coverage_months(b1), season_analysis.coverage_months(t1))


@router.get("/ledger/not-returned")
async def not_returned(base: str, target: str, _: CurrentUser = Depends(require(*ANALYSIS_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """Baz sezonun son 3 ayında ödeme yapıp hedef sezonda henüz ödemeyenler — geri kazanım arama listesi.
    Sezonluk peşin ödemesi baz dönemin son ayına düşenler (gelecek sezonu ödemiş) listeye girmez."""
    b0, b1 = await ledger_store.season_bounds(conn, base)
    t0, t1 = await ledger_store.season_bounds(conn, target)
    return rows(await conn.fetch(
        """WITH last3 AS (
             SELECT DISTINCT sheet_month FROM ledger_entries WHERE sheet_month BETWEEN $1 AND $2
             ORDER BY sheet_month DESC LIMIT 3),
           prepaid AS (
             SELECT DISTINCT player_key FROM ledger_entries
             WHERE sheet_month = (SELECT MAX(sheet_month) FROM last3)
               AND kind IN ('SEASON_UPFRONT','SEASON_INSTALLMENT') AND NOT cancelled),
           recent AS (
             SELECT player_key, MAX(player_name) AS player_name, MAX("group") AS "group",
                    MAX(paid_on) AS last_paid_on, SUM(amount)::float8 AS last3_amount
             FROM ledger_entries
             WHERE sheet_month IN (SELECT sheet_month FROM last3) AND NOT cancelled AND kind <> 'EVENT'
             GROUP BY player_key)
           SELECT r.* FROM recent r
           WHERE r.player_key NOT IN (SELECT player_key FROM prepaid)
             AND NOT EXISTS (SELECT 1 FROM ledger_entries t WHERE t.player_key = r.player_key
                             AND t.sheet_month BETWEEN $3 AND $4 AND NOT t.cancelled AND t.kind <> 'EVENT')
           ORDER BY r.last3_amount DESC""", b0, b1, t0, t1))
