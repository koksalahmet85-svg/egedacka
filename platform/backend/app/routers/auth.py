from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..core.db import db
from ..core.deps import User
from ..core.security import create_access_token, verify_password
from ..core.timeutil import utcnow

router = APIRouter(prefix="/auth", tags=["Kimlik"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    role: str


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn):
    user = await db.user.find_unique(where={"email": body.email.lower()})
    # Kullanıcı yoksa da hash doğrulaması yapılır → zamanlama ile e-posta keşfi engellenir.
    ok = verify_password(body.password, user.passwordHash if user else "$2b$12$" + "x" * 53)
    if not user or not ok or not user.isActive:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya şifre hatalı")
    await db.user.update(where={"id": user.id}, data={"lastLoginAt": utcnow()})
    return TokenOut(accessToken=create_access_token(user.id, user.role), role=user.role)


@router.get("/me")
async def me(user: User):
    return user
