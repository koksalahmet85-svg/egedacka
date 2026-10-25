"""Drive gelir takibi. Gelir Drive'daki ödeme tablosuna işlenir; burada okunur, özetlenir, izlenir."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..core.audit import audit
from ..core.deps import Executive, Finance, Management
from ..services import drive_income as svc
from ..services.google_sheets import SheetsError

router = APIRouter(prefix="/income", tags=["Drive Gelir Takibi"])


@router.get("/overview")
async def overview(
    _: Executive,
    season: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="Örn. 2026-27; boşsa en güncel sezon"),
    today: Annotated[date | None, Query(include_in_schema=False)] = None,
):
    """Tek yanıtta: aylık gelir (BİLANÇO karşılığı), ödemeyenler, takım kırılımı, son işlenen ödemeler, sorunlar."""
    return await svc.overview(season, today)


@router.post("/sync")
async def sync_now(user: Finance):
    """Drive'dan hemen okur (worker zaten her 15 dk'da bir okuyor)."""
    try:
        result = await svc.sync(trigger="manual")
    except SheetsError as e:
        raise HTTPException(503, str(e))
    await audit(user.id, "income.sync", "DriveSyncRun", result.get("runId", "-"))
    return result


@router.post("/bilanco/{season}/write")
async def write_bilanco(season: str, user: Management):
    """Hesaplanan aylık toplamları Drive'daki 'BİLANÇO yy-yy' sayfasına yazar (DRIVE_WRITE_BILANCO açıksa)."""
    try:
        out = await svc.write_bilanco(season)
    except SheetsError as e:
        raise HTTPException(409, str(e))
    await audit(user.id, "income.bilanco_write", "DriveSheetSource", out["sheet"])
    return out
