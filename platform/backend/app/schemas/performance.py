from datetime import datetime

from pydantic import Field

from .common import ApiModel


class TestResultIn(ApiModel):
    athleteId: str
    testCode: str
    value: float
    attempt: int = 1
    measuredAt: datetime
    sessionId: str | None = None
    notes: str | None = None


class TestBatch(ApiModel):
    results: list[TestResultIn] = Field(min_length=1, max_length=500)


class GameIn(ApiModel):
    teamId: str
    opponent: str
    competition: str | None = None
    playedAt: datetime
    isHome: bool
    teamScore: int | None = None
    oppScore: int | None = None


class BoxScoreIn(ApiModel):
    athleteId: str
    seconds: int = 0
    points: int = 0
    fgm2: int = 0
    fga2: int = 0
    fgm3: int = 0
    fga3: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    foulsDrawn: int = 0
    blkAgainst: int = 0
    plusMinus: int | None = None


class ReportPublish(ApiModel):
    coachComment: str = Field(min_length=10, max_length=2000)
