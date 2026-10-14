"""Prisma @db.Date alanları Python tarafında UTC gece yarısı datetime olarak taşınır."""

from datetime import UTC, date, datetime, time


def as_dt(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def as_date(dt: datetime | date) -> date:
    return dt.date() if isinstance(dt, datetime) else dt


def utcnow() -> datetime:
    return datetime.now(UTC)


def month_bounds(period: date) -> tuple[date, date]:
    start = period.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end


def add_months(d: date, months: int) -> date:
    """Ayın ilk günü için güvenli ay kaydırma."""
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)
