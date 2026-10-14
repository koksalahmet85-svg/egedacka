"""Zamanlanmış işler. Ayrı container olarak çalışır: `python -m app.worker`.

Her iş idempotent olduğundan worker yeniden başlasa ya da bir işi iki kez
çalıştırsa veri bozulmaz. Saatler Europe/Istanbul.
"""
import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .core import db
from .core.config import get_settings
from .services import billing, reports, scheduling
from .services.notify import LogSender, dispatch_outbox

log = logging.getLogger("worker")
sender = LogSender()


async def _with_conn(fn, *args):
    async with db.pool().acquire() as conn:
        result = await fn(conn, *args)
    log.info("%s%s → %s", fn.__name__, args, result)
    return result


async def monthly_invoices():
    await _with_conn(billing.generate_monthly_invoices, date.today().replace(day=1))


async def reminders():
    await _with_conn(billing.run_payment_reminders, date.today())


async def next_week_sessions():
    # 2 hafta ileriyi üret: veliler ve koçlar programı önceden görsün.
    today = date.today()
    for weeks in (1, 2):
        await _with_conn(scheduling.generate_week, today + timedelta(weeks=weeks))


async def close_previous_month():
    prev = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    await _with_conn(scheduling.close_month, prev)
    await _with_conn(scheduling.draft_payrolls, prev)


async def monthly_reports():
    prev = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    async with db.pool().acquire() as conn:
        ids = [r["athlete_id"] for r in await conn.fetch(
            "SELECT athlete_id FROM v_athlete_current_team ct JOIN athletes a ON a.id=ct.athlete_id WHERE a.status='ACTIVE'")]
        for aid in ids:
            await reports.build_monthly_report(conn, aid, prev)
    log.info("monthly report drafts: %s", len(ids))


async def outbox():
    await _with_conn(dispatch_outbox, sender)


async def main():
    logging.basicConfig(level=logging.INFO)
    await db.connect()
    tz = get_settings().tz
    s = AsyncIOScheduler(timezone=tz)
    s.add_job(outbox, "interval", seconds=30, max_instances=1, coalesce=True)
    s.add_job(monthly_invoices, "cron", day=1, hour=6, minute=0)
    s.add_job(reminders, "cron", hour=10, minute=0)  # mesaj saati: mesai içi
    s.add_job(next_week_sessions, "cron", day_of_week="sun", hour=20)
    s.add_job(close_previous_month, "cron", day=1, hour=7)
    s.add_job(monthly_reports, "cron", day=2, hour=7)  # koç notu eklemesi için taslak; yayın elle
    s.start()
    try:
        await asyncio.Event().wait()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
