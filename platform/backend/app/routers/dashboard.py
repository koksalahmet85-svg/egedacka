from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from ..core.deps import Executive
from ..core.timeutil import add_months
from ..schemas.dashboard import DashboardOverview
from ..services import dashboard as svc

router = APIRouter(prefix="/dashboard", tags=["Yönetim Paneli"])


@router.get("/overview", response_model=DashboardOverview)
async def overview(
    _: Executive,
    response: Response,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Hariç (yarı açık aralık)")] = None,
):
    """Finans + pazarlama ROI tek yanıtta. Varsayılan: son 6 ay (bu ay dahil)."""
    date_to = date_to or add_months(date.today().replace(day=1), 1)
    date_from = date_from or add_months(date_to.replace(day=1), -6)
    if date_from >= date_to:
        raise HTTPException(422, "from < to olmalı")
    if (date_to - date_from).days > 731:
        raise HTTPException(422, "En fazla 2 yıllık aralık")
    response.headers["Cache-Control"] = "private, max-age=30"
    return await svc.overview(date_from, date_to)
