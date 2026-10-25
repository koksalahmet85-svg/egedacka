"""Drive gelir takibi: senkron, değişiklik günlüğü, özet (BİLANÇO karşılığı), opsiyonel geri yazma."""

from __future__ import annotations

import logging
import statistics
import time
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from prisma import Json

from ..core.config import get_settings
from ..core.db import db
from ..core.timeutil import add_months, as_date, as_dt, utcnow
from ..domain import drive_income as di
from ..domain.money import ZERO, money
from .google_sheets import GoogleSheetsClient, SheetsError, SheetsReader

log = logging.getLogger(__name__)
MAX_ISSUES_STORED = 300
PROGRAM_LABEL = {"SPOR_OKULU": "Spor Okulu", "ALTYAPI": "Altyapı", "MASA_TENISI": "Masa Tenisi", "DIGER": "Diğer"}

_cache: dict[str, tuple[float, dict]] = {}


def invalidate_cache() -> None:
    _cache.clear()


# ── Senkron ──────────────────────────────────────────────────────────────────


async def sync(
    reader: SheetsReader | None = None, *, trigger: str = "schedule", spreadsheet_id: str | None = None
) -> dict:
    s = get_settings()
    spreadsheet_id = spreadsheet_id or s.drive_income_spreadsheet_id
    if not spreadsheet_id:
        raise SheetsError("DRIVE_INCOME_SPREADSHEET_ID tanımlı değil")

    # Aynı anda iki senkron çalışmasın (worker + elle tetikleme).
    running = await db.drivesyncrun.find_first(
        where={"status": "RUNNING", "startedAt": {"gt": utcnow() - timedelta(minutes=10)}}
    )
    if running:
        return {"status": "skipped", "reason": "Devam eden senkron var", "runId": running.id}

    run = await db.drivesyncrun.create(data={"trigger": trigger})
    try:
        reader = reader or GoogleSheetsClient()
        titles = await reader.sheet_titles(spreadsheet_id)
        values = await reader.read_sheets(spreadsheet_id, titles)
        parsed, skipped = [], []
        for t in titles:
            p = di.parse_sheet(t, values.get(t, []))
            (parsed if p else skipped).append(p or t)
        total_rows = total_changes = 0
        for sheet in parsed:
            n_rows, n_changes = await _store_sheet(spreadsheet_id, sheet, run.id)
            total_rows += n_rows
            total_changes += n_changes
        await db.drivesyncrun.update(
            where={"id": run.id},
            data={
                "status": "OK",
                "finishedAt": utcnow(),
                "sheets": len(parsed),
                "rows": total_rows,
                "changes": total_changes,
            },
        )
    except Exception as e:
        if isinstance(e, SheetsError):  # yapılandırma/erişim hatası: traceback gereksiz
            log.warning("Drive senkronu başarısız: %s", e)
        else:
            log.exception("Drive senkronu başarısız")
        await db.drivesyncrun.update(
            where={"id": run.id}, data={"status": "FAILED", "finishedAt": utcnow(), "error": str(e)[:500]}
        )
        raise
    finally:
        invalidate_cache()
    return {
        "status": "ok",
        "runId": run.id,
        "sheets": [f"{p.title} ({PROGRAM_LABEL[p.program]} {p.season})" for p in parsed],
        "skippedSheets": skipped,
        "rows": total_rows,
        "changes": total_changes,
    }


async def _store_sheet(spreadsheet_id: str, sheet: di.ParsedSheet, run_id: str) -> tuple[int, int]:
    source = await db.drivesheetsource.upsert(
        where={"spreadsheetId_sheetTitle": {"spreadsheetId": spreadsheet_id, "sheetTitle": sheet.title}},
        data={
            "create": {
                "spreadsheetId": spreadsheet_id,
                "sheetTitle": sheet.title,
                "program": sheet.program,
                "season": sheet.season,
                "seasonStart": sheet.season_start,
            },
            "update": {"program": sheet.program, "season": sheet.season, "seasonStart": sheet.season_start},
        },
    )
    first_sync = source.lastSyncedAt is None

    # Önceki durum → fark
    prev: dict[tuple[str, date], tuple[str, Decimal | None]] = {}
    if not first_sync:
        for r in await db.driveincomerow.find_many(where={"sourceId": source.id}, include={"cells": True}):
            for c in r.cells or []:
                prev[(r.rowKey, as_date(c.month))] = (c.status, c.amount)

    changes: list[dict] = []
    row_data: list[dict] = []
    cell_data: list[dict] = []
    for row in sheet.rows:
        rid = str(uuid.uuid4())
        row_data.append(
            {
                "id": rid,
                "sourceId": source.id,
                "rowKey": row.key,
                "rowNumber": row.row_number,
                "athleteName": row.name,
                "recordNo": row.record_no,
                "team": row.team,
                "coach": row.coach,
                "birthYear": row.birth_year,
                "rawPaymentType": row.raw_payment_type,
                "paymentType": row.payment_type,
                "textileFee": row.textile_fee,
                "typicalFee": row.typical_fee,
                "paidTotal": row.paid_total,
                "note": row.note,
                "isLeft": row.is_left,
            }
        )
        for c in row.cells:
            cell_data.append(
                {"rowId": rid, "month": as_dt(c.month), "status": c.status, "amount": c.amount, "raw": c.raw[:200]}
            )
            if first_sync:
                continue
            before = prev.get((row.key, c.month))
            if before is None and c.status in (di.EMPTY, di.PLACEHOLDER):
                continue
            if before is None or before[0] != c.status or before[1] != c.amount:
                changes.append(
                    {
                        "sourceId": source.id,
                        "syncRunId": run_id,
                        "rowKey": row.key,
                        "athleteName": row.name,
                        "month": as_dt(c.month),
                        "fromStatus": before[0] if before else None,
                        "toStatus": c.status,
                        "fromAmount": before[1] if before else None,
                        "toAmount": c.amount,
                    }
                )

    issues = [
        {"row": i.row_number, "name": i.name, "kind": i.kind, "detail": i.detail}
        for i in sheet.issues[:MAX_ISSUES_STORED]
    ]
    # Sayfa doğruluk kaynağıdır: satırlar her senkronda baştan yazılır (satır ekleme/silme/kaydırma güvenli).
    async with db.tx(timeout=timedelta(seconds=60), max_wait=timedelta(seconds=10)) as tx:
        await tx.driveincomerow.delete_many(where={"sourceId": source.id})
        if row_data:
            await tx.driveincomerow.create_many(data=[{k: v for k, v in r.items() if v is not None} for r in row_data])
            await tx.driveincomecell.create_many(
                data=[{k: v for k, v in c.items() if v is not None} for c in cell_data]
            )
        if changes:
            await tx.driveincomechange.create_many(
                data=[{k: v for k, v in c.items() if v is not None} for c in changes]
            )
        await tx.drivesheetsource.update(
            where={"id": source.id},
            data={"lastSyncedAt": utcnow(), "rowCount": len(row_data), "issues": Json(issues)},
        )
    return len(row_data), len(changes)


# ── Okuma modeli ─────────────────────────────────────────────────────────────


async def seasons() -> list[str]:
    rows = await db.drivesheetsource.find_many(order={"seasonStart": "desc"})
    return sorted({r.season for r in rows}, reverse=True)


async def _load(season: str) -> list[tuple[object, di.ParsedSheet]]:
    sources = await db.drivesheetsource.find_many(
        where={"season": season}, include={"rows": {"include": {"cells": True}}}, order={"sheetTitle": "asc"}
    )
    out = []
    for src in sources:
        sheet = di.ParsedSheet(title=src.sheetTitle, program=src.program, season_start=src.seasonStart, months=[])
        months: set[date] = set()
        for r in src.rows or []:
            cells = sorted(
                (di.Cell(as_date(c.month), c.status, c.amount, c.raw) for c in r.cells or []), key=lambda c: c.month
            )
            months.update(c.month for c in cells)
            sheet.rows.append(
                di.IncomeRow(
                    row_number=r.rowNumber,
                    key=r.rowKey,
                    name=r.athleteName,
                    record_no=r.recordNo,
                    team=r.team,
                    coach=r.coach,
                    birth_year=r.birthYear,
                    raw_payment_type=r.rawPaymentType,
                    payment_type=r.paymentType,
                    textile_fee=r.textileFee,
                    note=r.note,
                    is_left=r.isLeft,
                    cells=cells,
                )
            )
        sheet.months = sorted(months)
        out.append((src, sheet))
    return out


def _f(d: Decimal | None) -> float | None:
    return None if d is None else float(d)


async def overview(season: str | None = None, today: date | None = None) -> dict:
    today = today or utcnow().date()
    all_seasons = await seasons()
    season = season or (all_seasons[0] if all_seasons else None)
    key = f"{season}:{today.isoformat()}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < get_settings().dashboard_cache_seconds:
        return hit[1]

    last_run = await db.drivesyncrun.find_first(order={"startedAt": "desc"})
    base = {
        "season": season,
        "seasons": all_seasons,
        "today": today.isoformat(),
        "lastSync": None
        if last_run is None
        else {
            "at": (last_run.finishedAt or last_run.startedAt).isoformat(),
            "status": last_run.status,
            "trigger": last_run.trigger,
            "error": last_run.error,
            "changes": last_run.changes,
        },
    }
    if season is None:
        return {**base, "empty": True}

    loaded = await _load(season)
    sheets = [s for _, s in loaded]
    rows = [(s, r) for s in sheets for r in s.rows]
    this_month = today.replace(day=1)
    prev_month = add_months(this_month, -1)

    totals = di.monthly_totals(sheets, today)
    programs = sorted({s.program for s in sheets}, key=lambda p: list(PROGRAM_LABEL).index(p))

    # Program bazlı olağan aidat (satırın kendi ödemesi yoksa tahmin için)
    fees_by_prog: dict[str, list[Decimal]] = defaultdict(list)
    for s, r in rows:
        if r.payment_type == di.MONTHLY and r.typical_fee:
            fees_by_prog[s.program].append(r.typical_fee)
    median_fee = {p: money(statistics.median(v)) for p, v in fees_by_prog.items() if v}

    unpaid = []
    for s, r in rows:
        due_months, pending_months = [], []
        for m in s.months:
            st = di.expected_status(r, m, today)
            if st == di.DUE:
                due_months.append(m)
            elif st == di.PENDING_INSTALLMENT:
                pending_months.append(m)
        if not (due_months or pending_months):
            continue
        fee = r.typical_fee or median_fee.get(s.program)
        last_paid = max((c.month for c in r.cells if c.amount), default=None)
        unpaid.append(
            {
                "name": r.name,
                "program": s.program,
                "sheet": s.title,
                "rowNumber": r.row_number,
                "team": r.team,
                "coach": r.coach,
                "paymentType": r.payment_type,
                "kind": "DUE" if due_months else "PENDING_INSTALLMENT",
                "months": [m.strftime("%Y-%m") for m in (due_months or pending_months)],
                "overdueMonths": sum(1 for m in due_months if m < this_month),
                "typicalFee": _f(r.typical_fee),
                "estimatedAmount": _f(fee * len(due_months)) if fee and due_months else None,
                "lastPaidMonth": last_paid.strftime("%Y-%m") if last_paid else None,
                "note": r.note,
            }
        )
    unpaid.sort(key=lambda u: (u["kind"] != "DUE", -u["overdueMonths"], -(u["estimatedAmount"] or 0), u["name"]))

    by_team: dict[tuple[str, str | None, str | None], dict] = {}
    for s, r in rows:
        k = (s.program, r.team, r.coach if s.program == "ALTYAPI" else None)
        t = by_team.setdefault(
            k,
            {
                "program": s.program,
                "team": r.team or PROGRAM_LABEL[s.program],
                "coach": k[2],
                "athletes": 0,
                "seasonRevenue": ZERO,
                "monthRevenue": ZERO,
                "dueThisMonth": 0,
            },
        )
        if not r.is_left and r.payment_type not in (di.PROSPECT, di.UNKNOWN):
            t["athletes"] += 1
        t["seasonRevenue"] += r.paid_total
        t["monthRevenue"] += next((c.amount for c in r.cells if c.month == this_month and c.amount), ZERO)
        if di.expected_status(r, this_month, today) == di.DUE:
            t["dueThisMonth"] += 1
    teams = sorted(
        (
            {**t, "seasonRevenue": float(t["seasonRevenue"]), "monthRevenue": float(t["monthRevenue"])}
            for t in by_team.values()
        ),
        key=lambda t: (t["program"], -t["seasonRevenue"]),
    )

    cur = next((t for t in totals if t.month == this_month), None)
    prv = next((t for t in totals if t.month == prev_month), None)
    textile = defaultdict(lambda: ZERO)
    for s, r in rows:
        if r.textile_fee:
            textile[s.program] += r.textile_fee
    due_rows = [u for u in unpaid if u["kind"] == "DUE"]

    since = utcnow() - timedelta(days=14)
    source_ids = [src.id for src, _ in loaded]
    changes = await db.driveincomechange.find_many(
        where={"sourceId": {"in": source_ids}, "detectedAt": {"gte": since}},
        order={"detectedAt": "desc"},
        take=50,
        include={"source": True},
    )
    issues = [{**i, "sheet": src.sheetTitle} for src, _ in loaded for i in (src.issues or []) if isinstance(i, dict)]

    result = {
        **base,
        "empty": False,
        "currentMonth": this_month.strftime("%Y-%m"),
        "programs": [{"key": p, "label": PROGRAM_LABEL[p]} for p in programs],
        "sources": [
            {
                "title": src.sheetTitle,
                "program": src.program,
                "rows": src.rowCount,
                "lastSyncedAt": src.lastSyncedAt.isoformat() if src.lastSyncedAt else None,
                "issues": len(src.issues or []),
            }
            for src, _ in loaded
        ],
        "kpis": {
            "seasonTotal": float(sum((t.total for t in totals), ZERO)),
            "monthTotal": _f(cur.total) if cur else 0.0,
            "prevMonthTotal": _f(prv.total) if prv else 0.0,
            "monthPayers": cur.payers if cur else 0,
            "monthNonPayers": cur.non_payers if cur else 0,
            "overdueAthletes": sum(1 for u in due_rows if u["overdueMonths"] > 0),
            "estimatedOpen": float(
                sum((Decimal(str(u["estimatedAmount"])) for u in due_rows if u["estimatedAmount"]), ZERO)
            ),
            "pendingInstallments": sum(1 for u in unpaid if u["kind"] == "PENDING_INSTALLMENT"),
            "textileTotal": float(sum(textile.values(), ZERO)),
        },
        "counts": di.head_counts([r for _, r in rows]),
        "months": [
            {
                "month": t.month.strftime("%Y-%m"),
                "byProgram": {p: float(t.by_program.get(p, ZERO)) for p in programs},
                "total": float(t.total),
                "payers": t.payers,
                "nonPayers": t.non_payers,
                "pendingInstallments": t.pending_installments,
                "isFuture": t.month > this_month,
            }
            for t in totals
        ],
        "textileByProgram": {p: float(v) for p, v in textile.items()},
        "unpaid": unpaid,
        "teams": teams,
        "recentChanges": [
            {
                "at": c.detectedAt.isoformat(),
                "name": c.athleteName,
                "sheet": c.source.sheetTitle if c.source else None,
                "month": as_date(c.month).strftime("%Y-%m"),
                "from": c.fromStatus,
                "to": c.toStatus,
                "fromAmount": _f(c.fromAmount),
                "toAmount": _f(c.toAmount),
            }
            for c in changes
        ],
        "issues": issues[:100],
        "issueCount": len(issues),
    }
    if len(_cache) > 16:
        _cache.clear()
    _cache[key] = (time.monotonic(), result)
    return result


# ── BİLANÇO sayfasına geri yazma (opsiyonel) ─────────────────────────────────

BILANCO_MONTHS = 12  # Temmuz → Haziran (sayfadaki tablo)


async def write_bilanco(season: str) -> dict:
    """'BİLANÇO yy-yy' sayfasında C4:D15 (Spor Okulu, Altyapı) ve G4:H15 (ödeyen, ödemeyen) doldurulur.

    Tekstil sütunlarına dokunulmaz (tabloda tekstil ödemesinin ayı kayıtlı değil).
    """
    s = get_settings()
    if not s.drive_write_bilanco:
        raise SheetsError("DRIVE_WRITE_BILANCO kapalı")
    data = await overview(season)
    if data.get("empty"):
        raise SheetsError("Bu sezon için veri yok")
    start = int(season[:4])
    title = f"BİLANÇO {str(start)[2:]}-{str(start + 1)[2:]}"
    months = [m for m in data["months"] if m["month"] < f"{start + 1}-07"][:BILANCO_MONTHS]
    amounts = [[m["byProgram"].get("SPOR_OKULU", 0), m["byProgram"].get("ALTYAPI", 0)] for m in months]
    counts = [[m["payers"], m["nonPayers"]] for m in months]
    client = GoogleSheetsClient(write=True)
    await client.write_range(s.drive_income_spreadsheet_id, f"'{title}'!C4:D{3 + len(months)}", amounts)
    await client.write_range(s.drive_income_spreadsheet_id, f"'{title}'!G4:H{3 + len(months)}", counts)
    return {"sheet": title, "months": len(months)}
