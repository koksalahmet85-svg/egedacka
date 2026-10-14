from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import EmailStr, Field, model_validator

from .common import ApiModel
from .people import AthleteIn, GuardianIn

LeadStage = Literal["NEW", "CONTACTED", "TRIAL_SCHEDULED", "TRIAL_ATTENDED", "WON", "LOST"]
LeadSource = Literal[
    "META_LEAD_AD",
    "GOOGLE_LEAD_FORM",
    "WEBSITE",
    "INSTAGRAM_DM",
    "WHATSAPP",
    "REFERRAL",
    "WALK_IN",
    "SCHOOL_EVENT",
    "OTHER",
]


class CampaignIn(ApiModel):
    platform: Literal["META", "GOOGLE", "TIKTOK", "ORGANIC_SOCIAL", "OTHER"]
    externalId: str
    name: str
    objective: str | None = None
    startsOn: date | None = None
    endsOn: date | None = None


class SpendRow(ApiModel):
    campaignId: str
    date: date
    spend: Decimal = Field(ge=0)
    impressions: int = 0
    clicks: int = 0
    platformLeads: int = 0


class SpendImport(ApiModel):
    rows: list[SpendRow] = Field(min_length=1, max_length=5000)


class LeadIn(ApiModel):
    parentName: str
    phone: str
    email: EmailStr | None = None
    childName: str | None = None
    childBirthYear: int | None = Field(None, ge=2005, le=2025)
    source: LeadSource
    campaignId: str | None = None
    utmSource: str | None = None
    utmMedium: str | None = None
    utmCampaign: str | None = None
    utmContent: str | None = None
    referredByAthleteId: str | None = None
    marketingConsent: bool = False


class StageChange(ApiModel):
    stage: LeadStage
    note: str | None = None
    lostReason: str | None = None

    @model_validator(mode="after")
    def _lost(self):
        if self.stage == "LOST" and not self.lostReason:
            raise ValueError("LOST için lostReason zorunlu")
        return self


class ActivityIn(ApiModel):
    type: Literal["CALL", "WHATSAPP", "EMAIL", "NOTE"]
    note: str


class TrialIn(ApiModel):
    sessionId: str


class TrialResult(ApiModel):
    status: Literal["ATTENDED", "NO_SHOW", "CANCELLED"]
    coachRating: int | None = Field(None, ge=1, le=5)
    coachFeedback: str | None = None


class ConvertIn(ApiModel):
    athlete: AthleteIn
    guardian: GuardianIn
    teamId: str
    feePlanId: str
    startsOn: date
