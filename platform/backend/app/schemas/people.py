from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import EmailStr, Field

from .common import ApiModel

Gender = Literal["MALE", "FEMALE", "MIXED"]
AthleteStatus = Literal["TRIAL", "ACTIVE", "PAUSED", "LEFT"]


class GuardianIn(ApiModel):
    firstName: str
    lastName: str
    phone: str
    email: EmailStr | None = None
    billingAddress: str | None = None
    relation: str = "VELİ"
    taxId: str | None = Field(None, description="TCKN/VKN — şifrelenerek saklanır")


class AthleteIn(ApiModel):
    firstName: str
    lastName: str
    birthDate: date
    gender: Literal["MALE", "FEMALE"]
    position: str | None = None
    dominantHand: str | None = None
    licenseNo: str | None = None


class AthleteCreate(AthleteIn):
    teamId: str
    feePlanId: str
    startsOn: date
    guardian: GuardianIn


class AthleteUpdate(ApiModel):
    position: str | None = None
    status: AthleteStatus | None = None
    leaveReason: str | None = None
    medicalClearanceUntil: date | None = None
    photoUrl: str | None = None


class AthleteOut(ApiModel):
    id: str
    firstName: str
    lastName: str
    birthDate: datetime
    gender: str
    position: str | None
    status: str
    joinedOn: datetime
    medicalClearanceUntil: datetime | None


class StaffIn(ApiModel):
    firstName: str
    lastName: str
    phone: str | None = None
    department: Literal["COACHING", "ADMINISTRATION", "MARKETING", "FINANCE", "OPERATIONS", "HEALTH"]
    title: str
    employmentType: Literal["FULL_TIME", "PART_TIME", "FREELANCE"]
    payType: Literal["MONTHLY", "HOURLY", "PER_SESSION", "MIXED"]
    baseSalary: Decimal = Decimal("0")
    hourlyRate: Decimal | None = None
    sessionRate: Decimal | None = None
    coachLicenseLevel: str | None = None
    licenseExpiresOn: date | None = None
    hireDate: date
    iban: str | None = None


class StaffOut(ApiModel):
    id: str
    firstName: str
    lastName: str
    department: str
    title: str
    employmentType: str
    payType: str
    isActive: bool
    coachLicenseLevel: str | None
    licenseExpiresOn: datetime | None


class ShiftIn(ApiModel):
    staffId: str
    courtId: str | None = None
    type: Literal["TRAINING", "MATCH", "ADMIN", "EVENT"]
    startsAt: datetime
    endsAt: datetime
    note: str | None = None


class LeaveIn(ApiModel):
    type: Literal["ANNUAL", "SICK", "UNPAID", "EXCUSE"]
    startDate: date
    endDate: date
    note: str | None = None


class PayrollBuild(ApiModel):
    period: date
    bonuses: dict[str, Decimal] = {}
    deductions: dict[str, Decimal] = Field({}, description="staffId → SGK+vergi kesintisi (bordro yazılımından)")
