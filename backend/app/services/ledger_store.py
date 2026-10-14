"""Tahsilat defteri: veritabanına yazma ve sezon bazında okuma."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import date

import asyncpg

from .ledger_import import ParseResult
from .season_analysis import Row

_COLS = ("import_id", "sheet", "source_row", "sheet_month", "paid_on", "paid_on_inferred", "player_name",
         "player_key", "multi_player", "group", "period_label", "kind", "covered_months", "scholarship", "amount",
         "dues_amount", "textile_amount", "channel_raw", "channel", "method", "cancelled", "note")


async def store(conn: asyncpg.Connection, parsed: ParseResult, file_name: str, content: bytes,
                user_id: int | None) -> dict:
    """Dosyadaki sayfaları TAMAMEN değiştirir (sayfa bazında sil-yaz, tek transaction).

    Defter canlı bir belge: satır eklenir/düzeltilir. Sayfa bazında yeniden yazmak,
    satır kaymalarına karşı dayanıklı tek idempotent yöntem. Dosyada olmayan sayfalara dokunulmaz.
    """
    sha = hashlib.sha256(content).hexdigest()
    async with conn.transaction():
        import_id = await conn.fetchval(
            """INSERT INTO ledger_imports (file_name, sha256, sheets, row_count, anomalies, imported_by)
               VALUES ($1,$2,$3,$4,$5::jsonb,$6) RETURNING id""",
            file_name, sha, parsed.sheets, len(parsed.records), [asdict(a) for a in parsed.anomalies], user_id)
        removed = await conn.fetchval(
            "WITH d AS (DELETE FROM ledger_entries WHERE sheet = ANY($1::text[]) RETURNING 1) SELECT COUNT(*) FROM d",
            parsed.sheets)
        await conn.copy_records_to_table(
            "ledger_entries", columns=list(_COLS),
            records=[(import_id, r.sheet, r.source_row, r.sheet_month, r.paid_on, r.paid_on_inferred, r.player_name,
                      r.player_key, r.multi_player, r.group, r.period_label, r.kind, r.covered_months, r.scholarship,
                      r.amount, r.dues_amount, r.textile_amount, r.channel_raw, r.channel, r.method, r.cancelled,
                      r.note) for r in parsed.records])
        # Mevcut sporcu kayıtlarıyla ad eşleştirmesi (tam ad, tek eşleşme varsa).
        matched = await conn.fetchval(
            """WITH a AS (
                 SELECT id, upper(translate(first_name || ' ' || last_name, 'çğıiöşüÇĞİÖŞÜ', 'CGIIOSUCGIOSU')) AS k
                 FROM athletes),
               u AS (SELECT k, MIN(id) AS id FROM a GROUP BY k HAVING COUNT(*) = 1),
               upd AS (UPDATE ledger_entries le SET athlete_id = u.id FROM u
                       WHERE le.import_id = $1 AND le.player_key = u.k RETURNING 1)
               SELECT COUNT(*) FROM upd""", import_id)
    return {"import_id": import_id, "sheets": parsed.sheets, "rows": len(parsed.records),
            "replaced_rows": removed, "matched_athletes": matched,
            "anomalies": len(parsed.anomalies)}


async def season_bounds(conn: asyncpg.Connection, name: str) -> tuple[date, date]:
    r = await conn.fetchrow("SELECT start_date, end_date FROM seasons WHERE name=$1", name)
    if r is None:
        raise LookupError(f"Sezon tanımlı değil: {name}")
    return r["start_date"], r["end_date"]


async def load_rows(conn: asyncpg.Connection, start: date, end: date) -> list[Row]:
    recs = await conn.fetch(
        """SELECT sheet_month, paid_on, player_key, "group", kind::text, covered_months, scholarship,
                  amount::float8, dues_amount::float8, textile_amount::float8, channel, cancelled
           FROM ledger_entries WHERE sheet_month BETWEEN $1 AND $2""", start, end)
    return [Row(r["sheet_month"], r["paid_on"], r["player_key"], r["group"], r["kind"],
                tuple(r["covered_months"] or ()), r["scholarship"], r["amount"], r["dues_amount"],
                r["textile_amount"], r["channel"], r["cancelled"]) for r in recs]
