"""Dashboard yanıt sözleşmesi. Frontend'deki lib/types/dashboard.ts ile birebir aynı tutulur."""

from .common import ApiModel


class OverdueBlock(ApiModel):
    amount: float
    count: int
    families: int
    over30DaysAmount: float


class SeriesPoint(ApiModel):
    month: str
    income: float
    opex: float
    ad_spend: float
    net: float
    leads: int
    won: int


class FinanceBlock(ApiModel):
    revenue: float
    operatingExpenses: float
    adSpend: float
    totalExpenses: float
    net: float
    marginPct: float | None
    billed: float
    collectionRatePct: float | None
    overdue: OverdueBlock
    mrr: float
    activeAthletes: int
    avgMonthlyFee: float
    monthlyChurnPct: float
    series: list[SeriesPoint]


class FunnelBlock(ApiModel):
    leads: int
    contacted: int
    trialScheduled: int
    trialAttended: int
    won: int
    contactRate: float | None
    trialBookRate: float | None
    trialShowRate: float | None
    trialToMemberRate: float | None
    leadToMemberRate: float | None


class PaidBlock(ApiModel):
    leads: int
    won: int
    attributedRevenue: float
    spend: float
    cpl: float | None
    cac: float | None
    roas: float | None
    roi: float | None
    ltv: float
    ltvToCac: float | None
    paybackMonths: float | None


class ChannelRow(ApiModel):
    channel: str
    leads: int
    contacted: int
    trialScheduled: int
    trialAttended: int
    won: int
    lost: int
    leadToMemberPct: float | None
    medianResponseMin: float | None


class CampaignRow(ApiModel):
    id: str
    name: str
    platform: str
    spend: float
    impressions: int
    clicks: int
    ctrPct: float | None
    leads: int
    trials: int
    won: int
    revenue: float
    cpl: float | None
    cac: float | None
    roas: float | None
    roi: float | None
    ltvToCac: float | None


class MarketingBlock(ApiModel):
    funnel: FunnelBlock
    paid: PaidBlock
    expectedTenureMonths: float
    channels: list[ChannelRow]
    campaigns: list[CampaignRow]


class CombinedBlock(ApiModel):
    adSpendShareOfRevenuePct: float | None
    newMrrFromMarketing: float
    marketingPaybackMonths: float | None


class DashboardOverview(ApiModel):
    range: dict[str, str]
    generatedAt: str
    finance: FinanceBlock
    marketing: MarketingBlock
    combined: CombinedBlock
