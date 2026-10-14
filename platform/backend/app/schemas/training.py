from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .common import ApiModel

SessionType = Literal["TECHNICAL", "TACTICAL", "CONDITIONING", "MATCH", "RECOVERY", "TRIAL"]


class VenueIn(ApiModel):
    name: str
    address: str | None = None
    isOwned: bool = False


class CourtIn(ApiModel):
    venueId: str
    name: str
    type: Literal["INDOOR_HALL", "OUTDOOR_COURT", "GYM", "MEETING_ROOM"]
    capacity: int = 20
    hourlyCost: Decimal = Decimal("0")


class TeamIn(ApiModel):
    seasonId: str
    name: str
    ageGroup: str
    gender: Literal["MALE", "FEMALE", "MIXED"]
    level: Literal["SCHOOL", "DEVELOPMENT", "PERFORMANCE"]
    capacity: int = 20
    headCoachId: str | None = None
    feePlanId: str | None = None


class SlotIn(ApiModel):
    teamId: str
    courtId: str
    coachId: str
    weekday: int = Field(ge=0, le=6, description="0=Pazartesi")
    startTime: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    endTime: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    validFrom: date
    validTo: date | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.endTime <= self.startTime:
            raise ValueError("endTime > startTime olmalı")
        return self


class GenerateWeek(ApiModel):
    weekStart: date
    teamIds: list[str] | None = None
    dryRun: bool = False


class ConflictOut(ApiModel):
    kind: str
    teamId: str
    courtId: str
    coachId: str
    startsAt: datetime
    endsAt: datetime
    otherRef: str | None


class GenerateWeekOut(ApiModel):
    weekStart: date
    plans: int
    created: int
    skippedExisting: int
    conflicts: list[ConflictOut]


class SessionPatch(ApiModel):
    courtId: str | None = None
    coachId: str | None = None
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    type: SessionType | None = None
    focus: str | None = None
    plannedRpe: int | None = Field(None, ge=0, le=10)
    trialSeats: int | None = Field(None, ge=0)
    status: Literal["SCHEDULED", "CANCELLED"] | None = None


class DrillIn(ApiModel):
    order: int
    name: str
    durationMin: int = Field(gt=0)
    intensity: int | None = Field(None, ge=1, le=10)
    videoUrl: str | None = None


class AttendanceMark(ApiModel):
    athleteId: str
    status: Literal["PRESENT", "LATE", "ABSENT", "EXCUSED", "INJURED"]
    rpe: int | None = Field(None, ge=0, le=10, description="Seans sonrası CR-10 RPE (sRPE için)")
    minutes: int | None = Field(None, ge=0)
    note: str | None = None


class AttendanceBulk(ApiModel):
    marks: list[AttendanceMark]
