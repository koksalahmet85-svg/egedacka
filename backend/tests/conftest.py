"""Entegrasyon testleri gerçek PostgreSQL'e karşı çalışır (iş kuralları DB'de zorlandığı için
mock DB anlamsız olurdu). TEST_DATABASE_URL verilmezse yerel sunucuda geçici DB açılır."""
import os
from pathlib import Path

import asyncpg
import httpx
import pytest

from app.core import db
from app.core.security import hash_password

ADMIN_DSN = os.getenv("TEST_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres")
TEST_DB = "egealfa_test"
MIGRATIONS = Path(__file__).resolve().parents[2] / "prisma" / "migrations"


@pytest.fixture(scope="session")
async def dsn():
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    await admin.execute(f"CREATE DATABASE {TEST_DB}")
    await admin.close()
    url = ADMIN_DSN.rsplit("/", 1)[0] + f"/{TEST_DB}"
    conn = await asyncpg.connect(url)
    for mig in sorted(p for p in MIGRATIONS.iterdir() if p.is_dir()):
        await conn.execute((mig / "migration.sql").read_text())
    pw = hash_password("pw")
    await conn.execute(
        """INSERT INTO staff (id, first_name, last_name, department, title, employment_type, hourly_rate, hire_date)
           VALUES (1,'Koç','Bir','COACHING','Antrenör','HOURLY',500,'2024-01-01'),
                  (2,'Koç','İki','COACHING','Antrenör','HOURLY',500,'2024-01-01');
           SELECT setval('staff_id_seq', 2);""")
    await conn.execute(
        """INSERT INTO users (email, password_hash, role, staff_id) VALUES
           ('admin@t', $1, 'ADMIN', NULL), ('coach1@t', $1, 'COACH', 1), ('coach2@t', $1, 'COACH', 2)""", pw)
    await conn.close()
    return url


@pytest.fixture(scope="session")
async def client(dsn):
    from app.main import app

    await db.connect(dsn)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1") as c:
        yield c
    await db.disconnect()


async def _token(client, email):
    r = await client.post("/auth/login", data={"username": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
async def admin(client):
    return await _token(client, "admin@t")


@pytest.fixture(scope="session")
async def login(client):
    async def _login(email):
        return await _token(client, email)
    return _login


@pytest.fixture(scope="session")
async def conn(dsn):
    c = await asyncpg.connect(dsn)
    await db._init_conn(c)  # uygulama havuzuyla aynı JSON codec'i
    yield c
    await c.close()
