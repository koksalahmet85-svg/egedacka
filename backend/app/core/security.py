from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import asyncpg
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import get_settings
from .db import get_conn


class Role(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    COACH = "COACH"
    ACCOUNTANT = "ACCOUNTANT"
    MARKETING = "MARKETING"
    GUARDIAN = "GUARDIAN"


# Rol grupları — router'larda tekrar tekrar yazmamak için.
STAFF_ROLES = (Role.ADMIN, Role.MANAGER, Role.COACH, Role.ACCOUNTANT, Role.MARKETING)
SPORT_ROLES = (Role.ADMIN, Role.MANAGER, Role.COACH)
FINANCE_ROLES = (Role.ADMIN, Role.ACCOUNTANT)
CRM_ROLES = (Role.ADMIN, Role.MARKETING, Role.MANAGER)
EXEC_ROLES = (Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT, Role.MARKETING)

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: Role
    staff_id: int | None
    guardian_id: int | None


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: CurrentUser) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "sid": user.staff_id,
        "gid": user.guardian_id,
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


async def current_user(
    token: str = Depends(oauth2), conn: asyncpg.Connection = Depends(get_conn)
) -> CurrentUser:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz oturum",
                                 headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorized from None
    # Pasif kullanıcı token süresi dolmadan da dışarıda kalsın.
    active = await conn.fetchval("SELECT is_active FROM users WHERE id = $1", int(payload["sub"]))
    if not active:
        raise unauthorized
    return CurrentUser(int(payload["sub"]), Role(payload["role"]), payload.get("sid"), payload.get("gid"))


def require(*roles: Role):
    """Rol tabanlı yetki dependency'si: Depends(require(Role.ADMIN, ...))."""

    async def checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")
        return user

    return checker


async def assert_athlete_access(conn: asyncpg.Connection, user: CurrentUser, athlete_id: int) -> None:
    """Veli yalnız kendi çocuğunu, koç yalnız kendi takımındaki sporcuyu görür."""
    if user.role in (Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT):
        return
    if user.role == Role.GUARDIAN:
        ok = await conn.fetchval(
            "SELECT 1 FROM athlete_guardians WHERE athlete_id=$1 AND guardian_id=$2",
            athlete_id, user.guardian_id)
    elif user.role == Role.COACH:
        ok = await conn.fetchval(
            """SELECT 1 FROM v_athlete_current_team ct
               LEFT JOIN team_coaches tc ON tc.team_id = ct.team_id AND tc.staff_id = $2
               WHERE ct.athlete_id = $1 AND (ct.head_coach_id = $2 OR tc.staff_id IS NOT NULL)""",
            athlete_id, user.staff_id)
    else:
        ok = None
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sporcu bulunamadı")
