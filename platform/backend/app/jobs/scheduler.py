"""Zamanlanmış işler — ayrı `worker` konteynerinde TEK süreç olarak çalışır.

API çok worker'lı ölçeklense bile job'lar bir kez çalışır. Tüm job'lar idempotenttir
(unique kısıtlar + dedupeKey), yanlışlıkla iki kez tetiklenmeleri veri bozmaz.
"""

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..core.db import connect, disconnect
from ..core.timeutil import add_months
from ..services import ads_sync, billing, invoicing, notifications, reports

log = logging.getLogger("worker")
TZ = "Europe/Istanbul"


async def monthly_dues() -> None:
    r = await billing.generate_monthly_charges(date.today())
    log.info("aidat tahakkuku: %s", r)


async def monthly_reports() -> None:
    # Her ayın 1'inde bir önceki ayın raporları (taslak) üretilir; koç yorumlayıp yayınlar.
    n = await reports.generate_monthly_reports(add_months(date.today().replace(day=1), -1))
    log.info("aylık rapor taslağı: %s", n)


def build_scheduler() -> AsyncIOScheduler:
    s = AsyncIOScheduler(timezone=TZ)
    s.add_job(monthly_dues, CronTrigger(day=1, hour=3, minute=0, timezone=TZ), id="monthly_dues")
    s.add_job(monthly_reports, CronTrigger(day=1, hour=4, minute=0, timezone=TZ), id="monthly_reports")
    s.add_job(billing.process_overdue, CronTrigger(hour=9, minute=30, timezone=TZ), id="overdue")
    s.add_job(ads_sync.sync_recent, CronTrigger(hour=5, minute=15, timezone=TZ), id="ads_sync")
    s.add_job(invoicing.retry_failed_invoices, CronTrigger(minute="*/15", timezone=TZ), id="invoice_retry")
    # Bildirimler: gece 21:00-09:00 arası veliye mesaj atılmaz.
    s.add_job(notifications.dispatch_queued, CronTrigger(minute="*/2", hour="9-20", timezone=TZ), id="notify")
    return s


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await connect()
    sched = build_scheduler()
    sched.start()
    log.info("worker başladı: %s", [j.id for j in sched.get_jobs()])
    try:
        await asyncio.Event().wait()
    finally:
        sched.shutdown()
        await disconnect()


if __name__ == "__main__":
    asyncio.run(main())
