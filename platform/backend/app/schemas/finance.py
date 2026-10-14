from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from .common import ApiModel

PaymentMethod = Literal["CASH", "BANK_TRANSFER", "POS", "ONLINE_CARD", "AUTO_CHARGE"]


class FeePlanIn(ApiModel):
    name: str
    monthlyAmount: Decimal = Field(gt=0)
    vatRate: Decimal = Decimal("0")
    dueDay: int = Field(5, ge=1, le=28)


class SubscriptionIn(ApiModel):
    athleteId: str
    feePlanId: str
    startsOn: date
    discountPct: Decimal | None = Field(None, ge=0, le=100, description="Boşsa kardeş indirimi otomatik")
    discountReason: Literal["NONE", "SIBLING", "SCHOLARSHIP", "STAFF_CHILD", "ANNUAL_PREPAY", "CAMPAIGN"] | None = None


class ChargeIn(ApiModel):
    athleteId: str
    guardianId: str
    type: Literal["REGISTRATION", "CAMP", "EQUIPMENT", "TOURNAMENT", "OTHER"]
    description: str
    amount: Decimal = Field(gt=0)
    dueDate: date


class ChargeOut(ApiModel):
    id: str
    athleteId: str
    guardianId: str
    type: str
    period: datetime | None
    description: str
    netAmount: Decimal
    paidAmount: Decimal
    dueDate: datetime
    status: str
    reminderLevel: int


class PaymentIn(ApiModel):
    guardianId: str
    amount: Decimal = Field(gt=0)
    method: PaymentMethod
    paidAt: datetime | None = None
    reference: str | None = None
    chargeIds: list[str] | None = Field(None, description="Boşsa en eski borçtan FIFO kapatılır")
    note: str | None = None
    issueInvoice: bool = True


class PaymentOut(ApiModel):
    id: str
    guardianId: str
    amount: Decimal
    method: str
    paidAt: datetime
    unallocated: Decimal
    invoiceId: str | None


class ExpenseIn(ApiModel):
    category: Literal[
        "SALARY", "RENT", "EQUIPMENT", "TRANSPORT", "MARKETING", "UTILITIES", "TOURNAMENT", "LICENSE", "TAX", "OTHER"
    ]
    amount: Decimal = Field(ge=0)
    vatAmount: Decimal = Decimal("0")
    incurredOn: date
    vendor: str | None = None
    description: str | None = None
    courtId: str | None = None
    campaignId: str | None = None
    documentUrl: str | None = None


class WaiveIn(ApiModel):
    reason: str = Field(min_length=5)
