import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..core.db import get_conn
from ..core.security import CurrentUser, Role, create_token, current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), conn: asyncpg.Connection = Depends(get_conn)):
    u = await conn.fetchrow(
        "SELECT id, password_hash, role, staff_id, guardian_id, is_active FROM users WHERE email = lower($1)",
        form.username)
    if not u or not u["is_active"] or not verify_password(form.password, u["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya şifre hatalı")
    await conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", u["id"])
    user = CurrentUser(u["id"], Role(u["role"]), u["staff_id"], u["guardian_id"])
    return {"access_token": create_token(user), "token_type": "bearer", "role": user.role}


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)):
    return user
