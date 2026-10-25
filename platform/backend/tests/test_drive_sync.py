"""Drive senkronu uçtan uca: gerçek PostgreSQL, sahte Sheets okuyucu.

RUN_INTEGRATION=1 pytest tests/test_drive_sync.py
"""

import copy
import os
from datetime import date

import httpx
import pytest
import pytest_asyncio

from . import drive_fixtures as fx

pytestmark = [
    pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="RUN_INTEGRATION=1 gerekir"),
    pytest.mark.asyncio(loop_scope="module"),
]

TODAY = date(2026, 10, 25)
SHEET_ID = "TEST-SPREADSHEET"


class FakeReader:
    def __init__(self, data: dict):
        self.data = data

    async def sheet_titles(self, spreadsheet_id):
        return list(self.data)

    async def read_sheets(self, spreadsheet_id, titles):
        return {t: copy.deepcopy(self.data[t]) for t in titles}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db():
    from app.core.db import connect, db, disconnect

    await connect()
    await db.drivesyncrun.delete_many()
    await db.drivesheetsource.delete_many()
    yield db
    await disconnect()


async def _overview():
    from app.services import drive_income as svc

    svc.invalidate_cache()
    return await svc.overview("2026-27", TODAY)


async def test_first_sync_parses_payment_sheets_only(db):
    from app.services import drive_income as svc

    r = await svc.sync(FakeReader(fx.SPREADSHEET), trigger="manual", spreadsheet_id=SHEET_ID)
    assert r["status"] == "ok"
    assert len(r["sheets"]) == 3
    assert set(r["skippedSheets"]) == {fx.BILANCO_TITLE, fx.OLD_TITLE}
    assert r["changes"] == 0  # ilk senkronda geçmiş "değişiklik" sayılmaz
    assert await db.driveincomerow.count() == r["rows"]
    assert await db.driveincomecell.count() == r["rows"] * 14


async def test_overview_matches_sheet(db):
    o = await _overview()
    months = {m["month"]: m for m in o["months"]}
    assert months["2026-07"]["byProgram"]["SPOR_OKULU"] == 135000.0
    assert months["2026-09"]["byProgram"]["SPOR_OKULU"] == 78300.0
    assert months["2026-09"]["byProgram"]["MASA_TENISI"] == 22000.0
    assert months["2026-10"]["nonPayers"] == 4 and months["2026-11"]["isFuture"]
    assert o["kpis"]["monthNonPayers"] == 4
    assert o["kpis"]["pendingInstallments"] == 1
    assert o["kpis"]["seasonTotal"] == sum(m["total"] for m in o["months"])
    names = {u["name"]: u for u in o["unpaid"]}
    assert names["EGE BORÇLU"]["months"] == ["2026-09", "2026-10"] and names["EGE BORÇLU"]["overdueMonths"] == 1
    # Hiç ödemesi olmayan aylık sporcu için program medyanı ile tahmin
    assert names["EGE BORÇLU"]["estimatedAmount"] == pytest.approx(2 * 8100.0)
    assert "ARDA GİTTİ" not in names and "BORA ADAY" not in names
    assert names["VELİ ÖRNEK"]["kind"] == "PENDING_INSTALLMENT"
    assert o["counts"]["scholarship"] == 1 and o["counts"]["left"] == 1
    assert o["issueCount"] >= 2
    teams = {(t["program"], t["team"]) for t in o["teams"]}
    assert ("ALTYAPI", "EGE ALFA U-10 A") in teams


async def test_resync_detects_new_payment_even_when_rows_shift(db):
    from app.services import drive_income as svc

    data = copy.deepcopy(fx.SPREADSHEET)
    so = data[fx.SPOR_OKULU_TITLE]
    deniz = next(r for r in so if len(r) > 9 and r[9] == "DENİZ BOŞ")
    deniz[13] = 9000.0  # UNFORMATTED_VALUE gibi sayı olarak
    # Araya yeni satır eklendi: satır numaraları kayar, eşleşme isimle yapılmalı
    so.insert(
        4,
        ["", "", "", "", "-", "SPOR OKULU", "2019", "SEZONLUK", "9", "YENİ SEZONLUK", "70.000,00 TRY"]
        + ["SEZONLUK"] * 13,
    )

    r = await svc.sync(FakeReader(data), trigger="manual", spreadsheet_id=SHEET_ID)
    assert r["status"] == "ok"
    # DENİZ'in Ekim ödemesi + yeni sporcunun Temmuz ödemesi ve 13 SEZONLUK hücresi
    assert r["changes"] == 1 + 14
    o = await _overview()
    assert "DENİZ BOŞ" not in {u["name"] for u in o["unpaid"]}
    deniz_change = next(c for c in o["recentChanges"] if c["name"] == "DENİZ BOŞ")
    assert deniz_change["month"] == "2026-10" and deniz_change["to"] == "PAID" and deniz_change["toAmount"] == 9000.0
    assert o["kpis"]["monthNonPayers"] == 3


async def test_concurrent_sync_is_skipped(db):
    from app.services import drive_income as svc

    run = await db.drivesyncrun.create(data={"trigger": "manual"})
    r = await svc.sync(FakeReader(fx.SPREADSHEET), trigger="manual", spreadsheet_id=SHEET_ID)
    assert r["status"] == "skipped"
    await db.drivesyncrun.update(where={"id": run.id}, data={"status": "OK"})


async def test_http_endpoints_and_rbac(db):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1") as c:

        async def login(email):
            r = await c.post("/auth/login", json={"email": email, "password": "EgeAlfa!2026"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}

        fin = await login("finans@egealfa.com")
        r = await c.get("/income/overview?season=2026-27&today=2026-10-25", headers=fin)
        assert r.status_code == 200 and r.json()["season"] == "2026-27"
        coach = await login("koc@egealfa.com")
        assert (await c.get("/income/overview", headers=coach)).status_code == 403
        # Spreadsheet id tanımlı değil → anlaşılır 503
        assert (await c.post("/income/sync", headers=fin)).status_code == 503
        # BİLANÇO geri yazma varsayılan kapalı
        admin = await login("admin@egealfa.com")
        assert (await c.post("/income/bilanco/2026-27/write", headers=admin)).status_code == 409
