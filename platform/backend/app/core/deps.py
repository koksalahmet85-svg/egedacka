"""Kimlik doğrulama ve rol tabanlı yetki (RBAC) bağımlılıkları."""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import db
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str
    staff_id: str | None
    guardian_id: str | None
    athlete_id: str | None


async def get_current_user(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CurrentUser:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kimlik doğrulama gerekli")
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz veya süresi dolmuş token")
    user = await db.user.find_unique(
        where={"id": payload["sub"]},
        include={"staff": True, "guardian": True, "athlete": True},
    )
    if user is None or not user.isActive:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı pasif")
    return CurrentUser(
        id=user.id,
        role=user.role,
        staff_id=user.staff.id if user.staff else None,
        guardian_id=user.guardian.id if user.guardian else None,
        athlete_id=user.athlete.id if user.athlete else None,
    )


User = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(*roles: str):
    """ADMIN her zaman geçer."""
    allowed = set(roles) | {"ADMIN"}

    async def checker(user: User) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")
        return user

    return checker


# Sık kullanılan rol grupları
Staff = Annotated[CurrentUser, Depends(require_roles("MANAGER", "COACH", "FINANCE", "MARKETING"))]
Coaching = Annotated[CurrentUser, Depends(require_roles("MANAGER", "COACH"))]
Finance = Annotated[CurrentUser, Depends(require_roles("MANAGER", "FINANCE"))]
Marketing = Annotated[CurrentUser, Depends(require_roles("MANAGER", "MARKETING"))]
Management = Annotated[CurrentUser, Depends(require_roles("MANAGER"))]
Executive = Annotated[CurrentUser, Depends(require_roles("MANAGER", "FINANCE", "MARKETING"))]


async def assert_guardian_owns_athlete(user: CurrentUser, athlete_id: str) -> None:
    """Satır bazlı yetki: veli yalnızca kendi çocuğunu, sporcu yalnızca kendini görür."""
    if user.role in ("ADMIN", "MANAGER", "COACH"):
        return
    if user.role == "ATHLETE" and user.athlete_id == athlete_id:
        return
    if user.role == "GUARDIAN" and user.guardian_id:
        link = await db.athleteguardian.find_unique(
            where={"athleteId_guardianId": {"athleteId": athlete_id, "guardianId": user.guardian_id}}
        )
        if link:
            return
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Sporcu bulunamadı")
