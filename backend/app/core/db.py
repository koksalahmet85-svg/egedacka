"""asyncpg bağlantı havuzu.

Neden ORM değil: Prisma Client Python artık bakım görmüyor (repo arşivlendi).
Şemanın sahibi Prisma (migration'lar), sorguların sahibi bu katman. 750 sporcu
ölçeğinde analitik sorgular zaten SQL'de en hızlı ve en okunur halde.
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    for typ in ("json", "jsonb"):
        await conn.set_type_codec(typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect(dsn: str | None = None) -> asyncpg.Pool:
    global _pool
    s = get_settings()
    _pool = await asyncpg.create_pool(
        dsn or s.database_url, min_size=s.db_pool_min, max_size=s.db_pool_max, init=_init_conn
    )
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool


async def get_conn() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency: istek başına bir bağlantı."""
    async with pool().acquire() as conn:
        yield conn


def rows(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(r) for r in records]


def row(record: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(record) if record else None
