"""Yönetim paneli: finans + pazarlama ROI tek ekranda, tek istekte."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from ..core.security import EXEC_ROLES, CurrentUser, require
from ..services import dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/executive")
async def executive(response: Response, date_from: date | None = None, date_to: date | None = None,
                    _: CurrentUser = Depends(require(*EXEC_ROLES))):
    d_from, d_to = (date_from, date_to) if date_from and date_to else dashboard.default_range()
    if d_from > d_to:
        raise HTTPException(422, "date_from > date_to")
    if (d_to - d_from).days > 731:
        raise HTTPException(422, "En fazla 2 yıllık aralık")
    # Kısa tarayıcı önbelleği; sunucu tarafında da 60 sn TTL cache var.
    response.headers["Cache-Control"] = "private, max-age=30"
    return await dashboard.executive_summary(d_from, d_to)
