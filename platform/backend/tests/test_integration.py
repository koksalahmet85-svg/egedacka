"""Uçtan uca akış: gerçek PostgreSQL + seed verisi gerekir.

DATABASE_URL=... prisma migrate deploy && python -m app.seed --athletes 750
RUN_INTEGRATION=1 pytest tests/test_integration.py
"""

import os
import time
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio

pytestmark = [
    pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="RUN_INTEGRATION=1 ve seed'li DB gerekir"),
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client():
    from app.core.db import connect, disconnect
    from app.main import app

    await connect()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1") as c:
        yield c
    await disconnect()


async def _login(c, email):
    r = await c.post("/auth/login", json={"email": email, "password": "EgeAlfa!2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


async def test_auth_and_rbac(client):
    r = await client.post("/auth/login", json={"email": "admin@egealfa.com", "password": "yanlis"})
    assert r.status_code == 401
    coach = await _login(client, "koc@egealfa.com")
    # Koç finans paneline erişemez
    assert (await client.get("/dashboard/overview", headers=coach)).status_code == 403
    assert (await client.get("/finance/charges", headers=coach)).status_code == 403
    assert (await client.get("/athletes?take=5", headers=coach)).status_code == 200


async def test_weekly_plan_generation_is_idempotent_and_detects_conflicts(client):
    admin = await _login(client, "admin@egealfa.com")
    week = date.today() - timedelta(days=date.today().weekday())
    r = await client.post("/training/plans/generate", json={"weekStart": week.isoformat()}, headers=admin)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["created"] > 0 and first["conflicts"] == []
    r2 = await client.post("/training/plans/generate", json={"weekStart": week.isoformat()}, headers=admin)
    assert r2.json()["created"] == 0 and r2.json()["skippedExisting"] == first["created"]

    # Var olan bir seansın sahasına, aynı gün ve saate çakışan şablon ekle → bir sonraki hafta 409
    from datetime import datetime
    from zoneinfo import ZoneInfo

    sessions = (await client.get(f"/training/sessions?from={week}&to={week + timedelta(days=6)}", headers=admin)).json()
    ref = sessions[0]
    local = datetime.fromisoformat(ref["startsAt"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Istanbul"))
    teams = (await client.get("/training/teams", headers=admin)).json()
    other_team = next(t for t in teams if t["id"] != ref["teamId"])
    staff = (await client.get("/hr/staff?department=COACHING", headers=admin)).json()
    free_coach = next(c for c in staff if c["id"] != ref["coachId"])
    slot = {
        "teamId": other_team["id"],
        "courtId": ref["courtId"],
        "coachId": free_coach["id"],
        "weekday": local.weekday(),
        "startTime": f"{local.hour:02d}:30",
        "endTime": f"{local.hour + 1:02d}:00",
        "validFrom": week.isoformat(),
    }
    assert (await client.post("/training/slots", json=slot, headers=admin)).status_code == 201
    nxt = (week + timedelta(days=7)).isoformat()
    r3 = await client.post("/training/plans/generate", json={"weekStart": nxt}, headers=admin)
    assert r3.status_code == 409
    assert r3.json()["detail"]["conflicts"][0]["kind"] == "court"
    dry = await client.post("/training/plans/generate", json={"weekStart": nxt, "dryRun": True}, headers=admin)
    assert dry.status_code == 200 and dry.json()["created"] == 0


async def test_db_exclusion_constraint_blocks_double_booking(client):
    admin = await _login(client, "admin@egealfa.com")
    week = date.today() - timedelta(days=date.today().weekday())
    sessions = (await client.get(f"/training/sessions?from={week}&to={week + timedelta(days=6)}", headers=admin)).json()
    a, b = sessions[0], next(s for s in sessions if s["courtId"] != sessions[0]["courtId"])
    # b'yi a'nın sahasına ve saatine taşımaya çalış → veritabanı reddeder
    r = await client.patch(
        f"/training/sessions/{b['id']}",
        json={"courtId": a["courtId"], "startsAt": a["startsAt"], "endsAt": a["endsAt"]},
        headers=admin,
    )
    assert r.status_code == 409


async def test_session_completion_creates_timesheet(client):
    coach = await _login(client, "koc@egealfa.com")
    week = date.today() - timedelta(days=date.today().weekday())
    s = (await client.get(f"/training/sessions?from={week}&to={week + timedelta(days=6)}", headers=coach)).json()[0]
    roster = (await client.get(f"/training/teams/{s['teamId']}/roster", headers=coach)).json()
    marks = [
        {"athleteId": m["athleteId"], "status": "PRESENT" if i % 5 else "ABSENT", "rpe": 6}
        for i, m in enumerate(roster)
    ]
    r = await client.put(f"/training/sessions/{s['id']}/attendance", json={"marks": marks}, headers=coach)
    assert r.json()["marked"] == len(roster)
    r = await client.post(f"/training/sessions/{s['id']}/complete", headers=coach)
    assert r.status_code == 200 and r.json()["minutes"] == 90


async def test_billing_cycle(client):
    fin = await _login(client, "finans@egealfa.com")
    from app.core.timeutil import add_months

    period = add_months(date.today().replace(day=1), 1).isoformat()  # seed bu aya kadar üretti
    r = await client.post(f"/finance/charges/generate-monthly?period={period}", headers=fin)
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert created > 700
    again = (await client.post(f"/finance/charges/generate-monthly?period={period}", headers=fin)).json()
    assert again["created"] == 0 and again["already_existed"] == created  # idempotent

    charges = (await client.get("/finance/charges?take=3&status=PENDING", headers=fin)).json()["items"]
    ch = charges[0]
    net = float(ch["netAmount"])
    # Kısmi ödeme, belirli tahakkuka (chargeIds yoksa FIFO en eski borcu kapatır)
    r = await client.post(
        "/finance/payments",
        json={
            "guardianId": ch["guardianId"],
            "amount": str(net / 2),
            "method": "BANK_TRANSFER",
            "chargeIds": [ch["id"]],
            "issueInvoice": True,
        },
        headers=fin,
    )
    assert r.status_code == 201, r.text
    st = (await client.get(f"/finance/guardians/{ch['guardianId']}/statement", headers=fin)).json()
    mine = next(c for c in st["charges"] if c["id"] == ch["id"])
    assert mine["status"] == "PARTIALLY_PAID" and float(mine["paidAmount"]) == pytest.approx(net / 2)
    inv = (await client.get("/finance/invoices", headers=fin)).json()
    assert inv and inv[0]["status"] == "ISSUED" and inv[0]["kind"] == "RECEIPT"


async def test_overdue_escalation_is_deduplicated(client):
    admin = await _login(client, "admin@egealfa.com")
    from app.core.timeutil import add_months

    future = (add_months(date.today().replace(day=1), 1) + timedelta(days=4 + 21)).isoformat()  # vade + 21 gün
    r1 = (await client.post(f"/admin/jobs/overdue?today={future}", headers=admin)).json()
    assert r1["marked_overdue"] > 0 and r1["notifications_queued"] > 0 and r1["escalations"] > 0
    r2 = (await client.post(f"/admin/jobs/overdue?today={future}", headers=admin)).json()
    assert r2["notifications_queued"] == 0 and r2["marked_overdue"] == 0
    aging = (await client.get("/finance/aging", headers=admin)).json()
    assert isinstance(aging, list)


async def test_lead_to_member_conversion(client):
    mkt = await _login(client, "pazarlama@egealfa.com")
    admin = await _login(client, "admin@egealfa.com")
    camps = (await client.get("/crm/campaigns", headers=mkt)).json()
    r = await client.post(
        "/crm/leads",
        json={
            "parentName": "Test Veli",
            "phone": "0532 999 88 77",
            "source": "META_LEAD_AD",
            "campaignId": camps[0]["id"],
        },
        headers=mkt,
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["phone"] == "+905329998877"
    dup = await client.post(
        "/crm/leads", json={"parentName": "X", "phone": "+905329998877", "source": "WEBSITE"}, headers=mkt
    )
    assert dup.status_code == 409

    await client.post(f"/crm/leads/{lead['id']}/activities", json={"type": "CALL", "note": "arandı"}, headers=mkt)
    assert (await client.get(f"/crm/leads/{lead['id']}", headers=mkt)).json()["stage"] == "CONTACTED"

    # Geri gidiş yasak
    back = await client.post(f"/crm/leads/{lead['id']}/stage", json={"stage": "NEW"}, headers=mkt)
    assert back.status_code == 409

    teams = (await client.get("/training/teams", headers=admin)).json()
    team = teams[4]
    nxt = date.today() + timedelta(days=7 - date.today().weekday())
    await client.post(
        "/training/plans/generate", json={"weekStart": nxt.isoformat(), "teamIds": [team["id"]]}, headers=admin
    )
    sessions = (
        await client.get(
            f"/training/sessions?from={nxt}&to={nxt + timedelta(days=6)}&teamId={team['id']}", headers=admin
        )
    ).json()
    s = sessions[0]
    await client.patch(f"/training/sessions/{s['id']}", json={"trialSeats": 3}, headers=admin)
    b = await client.post(f"/crm/leads/{lead['id']}/trials", json={"sessionId": s["id"]}, headers=mkt)
    assert b.status_code == 201, b.text
    res = await client.post(
        f"/crm/trials/{b.json()['id']}/result", json={"status": "ATTENDED", "coachRating": 4}, headers=mkt
    )
    assert res.status_code == 200

    conv = await client.post(
        f"/crm/leads/{lead['id']}/convert",
        headers=mkt,
        json={
            "athlete": {"firstName": "Test", "lastName": "Sporcu", "birthDate": "2013-05-01", "gender": "MALE"},
            "guardian": {"firstName": "Test", "lastName": "Veli", "phone": "+905329998877"},
            "teamId": team["id"],
            "feePlanId": team["feePlanId"],
            "startsOn": date.today().isoformat(),
        },
    )
    assert conv.status_code == 201, conv.text
    final = (await client.get(f"/crm/leads/{lead['id']}", headers=mkt)).json()
    assert final["stage"] == "WON" and final["wonAt"] and final["trialAttendedAt"] and final["convertedAthleteId"]


async def test_dashboard_overview_fast_and_consistent(client):
    from app.services import dashboard

    admin = await _login(client, "admin@egealfa.com")
    dashboard.invalidate_cache()
    t0 = time.perf_counter()
    r = await client.get("/dashboard/overview", headers=admin)
    cold_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    d = r.json()
    f, m = d["finance"], d["marketing"]
    assert f["activeAthletes"] > 700 and f["mrr"] > 0 and f["monthlyChurnPct"] > 0
    assert f["net"] == pytest.approx(f["revenue"] - f["totalExpenses"])
    assert len(f["series"]) == 6
    assert m["funnel"]["leads"] >= m["funnel"]["contacted"] >= m["funnel"]["trialScheduled"] >= m["funnel"]["won"]
    assert m["paid"]["spend"] > 0 and m["paid"]["cpl"] > 0 and m["paid"]["attributedRevenue"] > 0
    assert {c["platform"] for c in m["campaigns"]} == {"META", "GOOGLE"}
    assert cold_ms < 1500, f"dashboard soğuk {cold_ms:.0f} ms"
    t1 = time.perf_counter()
    await client.get("/dashboard/overview", headers=admin)
    assert (time.perf_counter() - t1) * 1000 < cold_ms
    print(f"\n  dashboard: soğuk {cold_ms:.0f} ms")


async def test_reports_and_portal_isolation(client):
    coach = await _login(client, "koc@egealfa.com")
    r = await client.post(f"/performance/reports/generate?period={date.today().replace(day=1)}", headers=coach)
    assert r.status_code == 200 and r.json()["generated"] > 0

    from app.core.db import db
    from app.core.security import hash_password

    g1, g2 = await db.guardian.find_many(take=2, order={"createdAt": "asc"})
    u = await db.user.upsert(
        where={"email": "veli-test@egealfa.com"},
        data={
            "create": {
                "email": "veli-test@egealfa.com",
                "passwordHash": hash_password("EgeAlfa!2026"),
                "role": "GUARDIAN",
            },
            "update": {},
        },
    )
    await db.guardian.update(where={"id": g1.id}, data={"userId": u.id})
    veli = await _login(client, "veli-test@egealfa.com")
    kids = (await client.get("/portal/children", headers=veli)).json()
    assert kids
    other = await db.athleteguardian.find_first(where={"guardianId": g2.id})
    assert (await client.get(f"/athletes/{other.athleteId}", headers=veli)).status_code == 404
    assert (await client.get(f"/athletes/{kids[0]['id']}", headers=veli)).status_code == 200
    assert (await client.get("/portal/billing", headers=veli)).status_code == 200
