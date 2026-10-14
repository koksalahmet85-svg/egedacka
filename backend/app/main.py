from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core import db, errors
from .core.config import get_settings
from .routers import (athletes, auth, crm, dashboard, finance, hr, ledger, performance, portal, teams, training,
                      webhooks)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(title="Ege Alfa Spor Kulübü API", version="1.0.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    for r in (auth, athletes, teams, training, hr, performance, finance, ledger, crm, dashboard, portal, webhooks):
        app.include_router(r.router, prefix="/api/v1")

    @app.get("/healthz", include_in_schema=False)
    async def health():
        async with db.pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"ok": True}

    return app


app = create_app()
