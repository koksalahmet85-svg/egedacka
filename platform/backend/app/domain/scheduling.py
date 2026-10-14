"""Haftalık şablondan antrenman seansı üretimi ve çakışma tespiti."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CLUB_TZ = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class Slot:
    id: str
    team_id: str
    court_id: str
    coach_id: str
    weekday: int  # 0=Pzt
    start_time: str  # "18:00"
    end_time: str
    valid_from: date
    valid_to: date | None = None


@dataclass(frozen=True)
class SessionDraft:
    slot_id: str | None
    team_id: str
    court_id: str
    coach_id: str
    starts_at: datetime  # UTC, naive değil
    ends_at: datetime


@dataclass(frozen=True)
class Conflict:
    kind: str  # "court" | "coach"
    draft: SessionDraft
    other_starts_at: datetime
    other_ends_at: datetime
    other_ref: str | None


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _local_to_utc(day: date, hhmm: str) -> datetime:
    t = time.fromisoformat(hhmm)
    return datetime.combine(day, t, tzinfo=CLUB_TZ).astimezone(UTC)


def expand_week(slots: list[Slot], week_start: date) -> list[SessionDraft]:
    """week_start (pazartesi) haftası için geçerli şablonlardan seans taslakları üretir."""
    if week_start.weekday() != 0:
        raise ValueError("week_start pazartesi olmalı")
    drafts: list[SessionDraft] = []
    for s in slots:
        day = week_start + timedelta(days=s.weekday)
        if day < s.valid_from or (s.valid_to and day > s.valid_to):
            continue
        drafts.append(
            SessionDraft(
                slot_id=s.id,
                team_id=s.team_id,
                court_id=s.court_id,
                coach_id=s.coach_id,
                starts_at=_local_to_utc(day, s.start_time),
                ends_at=_local_to_utc(day, s.end_time),
            )
        )
    return sorted(drafts, key=lambda d: d.starts_at)


def _overlaps(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    # Yarı açık aralık [start, end): 18:00-19:30 ile 19:30-21:00 çakışmaz.
    return a0 < b1 and b0 < a1


@dataclass(frozen=True)
class Booked:
    ref: str
    court_id: str
    coach_id: str
    starts_at: datetime
    ends_at: datetime


def find_conflicts(drafts: list[SessionDraft], existing: list[Booked]) -> list[Conflict]:
    """Taslakların hem mevcut seanslarla hem birbirleriyle saha/koç çakışmasını bulur."""
    conflicts: list[Conflict] = []
    pool: list[Booked] = list(existing)
    for i, d in enumerate(drafts):
        for b in pool:
            if not _overlaps(d.starts_at, d.ends_at, b.starts_at, b.ends_at):
                continue
            if b.court_id == d.court_id:
                conflicts.append(Conflict("court", d, b.starts_at, b.ends_at, b.ref))
            if b.coach_id == d.coach_id:
                conflicts.append(Conflict("coach", d, b.starts_at, b.ends_at, b.ref))
        pool.append(Booked(f"draft:{i}", d.court_id, d.coach_id, d.starts_at, d.ends_at))
    return conflicts
