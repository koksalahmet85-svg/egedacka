from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import get_settings
from .core.db import connect, db, disconnect
from .routers import (
    admin,
    athletes,
    auth,
    crm,
    dashboard,
    finance,
    income,
    performance,
    portal,
    staff,
    training,
    webhooks,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect()
    yield
    await disconnect()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.env != "production" else None,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

API = "/api/v1"
for r in (auth, athletes, staff, training, performance, income, crm, dashboard, admin):
    app.include_router(r.router, prefix=API)
# Şimdilik kapalı modüller: kod duruyor, ayar açılınca devreye girer.
if settings.enable_portal:
    app.include_router(portal.router, prefix=API)
if settings.enable_accounting:
    app.include_router(finance.router, prefix=API)
    app.include_router(admin.accounting_router, prefix=API)
app.include_router(webhooks.router)  # dış sistemler sabit URL'e çağırır: /webhooks/...


@app.get("/healthz", include_in_schema=False)
async def healthz():
    await db.query_raw("SELECT 1")
    return {"ok": True}
