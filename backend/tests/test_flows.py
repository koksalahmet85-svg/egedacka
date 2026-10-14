"""Uçtan uca iş akışları — testler sırayla çalışır ve aynı veritabanı durumunu paylaşır."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Europe/Istanbul")
NEXT_MONDAY = date.today() + timedelta(days=7 - date.today().weekday())
S = {}  # testler arası paylaşılan id'ler


def athlete_payload(first, phone, team_id, birth="2012-05-05"):
    return {"first_name": first, "last_name": "TEST", "birth_date": birth, "gender": "MALE", "team_id": team_id,
            "guardian": {"full_name": "Veli Test", "phone": phone, "kvkk_consent": True}}


async def test_setup_catalog(client, admin, conn):
    r = await client.post("/facilities", json={"name": "Saha 1", "type": "COURT", "capacity": 30, "hourly_cost": 1000},
                          headers=admin)
    assert r.status_code == 201
    S["fac"] = r.json()["id"]
    S["season"] = await conn.fetchval(
        "INSERT INTO seasons (name, start_date, end_date, is_active) VALUES ('T', CURRENT_DATE - 60, CURRENT_DATE + 300, true) RETURNING id")
    r = await client.post("/finance/fee-plans", json={"name": "Altyapı", "monthly_amount": 4500}, headers=admin)
    S["plan"] = r.json()["id"]
    for name, coach in (("U 14-A", 1), ("U 12-A", 2)):
        r = await client.post("/teams", json={"season_id": S["season"], "name": name, "age_group": name[:4].replace(" ", ""),
                                              "level": "DEVELOPMENT", "head_coach_id": coach,
                                              "default_fee_plan_id": S["plan"]}, headers=admin)
        assert r.status_code == 201, r.text
        S[name] = r.json()["id"]


async def test_kvkk_consent_required(client, admin):
    p = athlete_payload("ALİ", "+905000000001", S["U 14-A"])
    p["guardian"]["kvkk_consent"] = False
    r = await client.post("/athletes", json=p, headers=admin)
    assert r.status_code == 422


async def test_create_athletes_with_siblings(client, admin):
    for key, first, phone, team in (("a1", "KUZEY", "+905000000010", "U 14-A"), ("a2", "EGE", "+905000000010", "U 12-A"),
                                    ("a3", "DENİZ", "+905000000020", "U 14-A")):
        r = await client.post("/athletes", json=athlete_payload(first, phone, S[team]), headers=admin)
        assert r.status_code == 201, r.text
        S[key] = r.json()["id"]


async def test_week_generation_is_idempotent_and_reports_conflicts(client, admin):
    plan = {"team_id": S["U 14-A"], "coach_id": 1, "facility_id": S["fac"], "weekday": 2, "start_time": "17:00",
            "duration_min": 90, "valid_from": str(date.today() - timedelta(days=30))}
    assert (await client.post("/training/plans", json=plan, headers=admin)).status_code == 201
    # Aynı saha + kesişen saat, farklı takım/koç → çakışma
    clash = plan | {"team_id": S["U 12-A"], "coach_id": 2, "start_time": "18:00"}
    assert (await client.post("/training/plans", json=clash, headers=admin)).status_code == 201

    r1 = (await client.post(f"/training/weeks/{NEXT_MONDAY}/generate", headers=admin)).json()
    assert r1["created"] == 1 and len(r1["conflicts"]) == 1
    assert r1["conflicts"][0]["reason"] == "training_sessions_no_facility_overlap"
    r2 = (await client.post(f"/training/weeks/{NEXT_MONDAY}/generate", headers=admin)).json()
    assert r2["created"] == 0 and r2["already_existed"] == 1


async def test_manual_session_overlap_returns_409(client, admin):
    start = datetime.combine(NEXT_MONDAY + timedelta(days=1), datetime.min.time(), TZ).replace(hour=17, minute=30)
    r = await client.post("/training/sessions", json={
        "team_id": S["U 12-A"], "coach_id": 1, "facility_id": S["fac"],
        "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=1)).isoformat()}, headers=admin)
    assert r.status_code == 409
    assert "dolu" in r.json()["detail"] or "Koç" in r.json()["detail"]


async def test_attendance_creates_timesheet_entry(client, admin, login, conn):
    start = datetime.now(TZ) - timedelta(days=2, hours=3)
    r = await client.post("/training/sessions", json={
        "team_id": S["U 14-A"], "coach_id": 1, "facility_id": S["fac"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=90)).isoformat()}, headers=admin)
    sid = r.json()["id"]
    S["past_session"] = sid
    # Başka koç bu seansa yoklama giremez
    other = await login("coach2@t")
    assert (await client.put(f"/training/sessions/{sid}/attendance", json=[], headers=other)).status_code == 403

    coach = await login("coach1@t")
    roster = (await client.get(f"/training/sessions/{sid}/attendance", headers=coach)).json()
    assert {x["athlete_id"] for x in roster} == {S["a1"], S["a3"]}
    items = [{"athlete_id": S["a1"], "status": "PRESENT", "rpe": 7}, {"athlete_id": S["a3"], "status": "ABSENT"}]
    r = await client.put(f"/training/sessions/{sid}/attendance", json=items, headers=coach)
    assert r.status_code == 200 and r.json()["minutes"] == 90
    # Tekrar göndermek ikinci puantaj satırı üretmez
    await client.put(f"/training/sessions/{sid}/attendance", json=items, headers=coach)
    assert await conn.fetchval("SELECT COUNT(*) FROM time_entries WHERE session_id=$1", sid) == 1


async def test_invoices_idempotent_with_sibling_discount(client, admin, conn):
    period = date.today().replace(day=1)
    r1 = (await client.post(f"/finance/invoices/run/{period}", headers=admin)).json()
    assert r1["created"] == 3
    r2 = (await client.post(f"/finance/invoices/run/{period}", headers=admin)).json()
    assert r2["created"] == 0
    totals = {r["athlete_id"]: r["total"] for r in await conn.fetch("SELECT athlete_id, total FROM invoices")}
    assert float(totals[S["a1"]]) == 4500 and float(totals[S["a2"]]) == 4050  # 2. kardeş %10
    assert float(totals[S["a3"]]) == 4500


async def test_payment_updates_invoice_via_trigger(client, admin, conn):
    inv = await conn.fetchrow("SELECT id, guardian_id, total FROM invoices WHERE athlete_id=$1", S["a3"])
    r = await client.post("/finance/payments", json={"guardian_id": inv["guardian_id"], "invoice_id": inv["id"],
                                                     "amount": 2000, "method": "CASH"}, headers=admin)
    assert r.status_code == 201 and r.json()["receipt_no"].startswith("MKB")
    assert await conn.fetchval("SELECT status FROM invoices WHERE id=$1", inv["id"]) == "PARTIALLY_PAID"
    await client.post("/finance/payments", json={"guardian_id": inv["guardian_id"], "invoice_id": inv["id"],
                                                 "amount": 2500, "method": "CASH"}, headers=admin)
    assert await conn.fetchval("SELECT status FROM invoices WHERE id=$1", inv["id"]) == "PAID"
    # Başka velinin faturasına tahsilat reddedilir
    other = await conn.fetchval("SELECT id FROM invoices WHERE athlete_id=$1", S["a1"])
    r = await client.post("/finance/payments", json={"guardian_id": inv["guardian_id"], "invoice_id": other,
                                                     "amount": 10, "method": "CASH"}, headers=admin)
    assert r.status_code == 422


async def test_overdue_reminders_sent_once(conn):
    from app.services.billing import run_payment_reminders

    await conn.execute("UPDATE invoices SET issue_date = CURRENT_DATE - 20, due_date = CURRENT_DATE - 8 WHERE status='ISSUED'")
    r1 = await run_payment_reminders(conn, date.today())
    assert r1["sent"] == 2  # a1 + a2 faturaları; a3 ödendi
    assert await conn.fetchval("SELECT COUNT(*) FROM payment_reminders WHERE level='OVERDUE_7'") == 2
    assert await conn.fetchval("SELECT COUNT(*) FROM payment_reminders WHERE level='OVERDUE_1'") == 0  # seviye atlandı
    r2 = await run_payment_reminders(conn, date.today())
    assert r2["sent"] == 0


async def test_guardian_portal_isolation(client, admin, conn):
    from app.core.security import hash_password

    gid = await conn.fetchval("SELECT guardian_id FROM athlete_guardians WHERE athlete_id=$1", S["a1"])
    await conn.execute("INSERT INTO users (email, password_hash, role, guardian_id) VALUES ('veli@t',$1,'GUARDIAN',$2)",
                       hash_password("pw"), gid)
    r = await client.post("/auth/login", data={"username": "veli@t", "password": "pw"})
    veli = {"Authorization": f"Bearer {r.json()['access_token']}"}
    kids = (await client.get("/portal/children", headers=veli)).json()
    assert {k["id"] for k in kids} == {S["a1"], S["a2"]}
    assert (await client.get(f"/athletes/{S['a1']}/progress", headers=veli)).status_code == 200
    assert (await client.get(f"/athletes/{S['a3']}/progress", headers=veli)).status_code == 404  # başkasının çocuğu
    assert (await client.get("/dashboard/executive", headers=veli)).status_code == 403
    assert (await client.get("/finance/invoices", headers=veli)).status_code == 403
    assert len((await client.get("/portal/invoices", headers=veli)).json()) == 2


async def test_coach_sees_only_own_athletes(client, login):
    coach2 = await login("coach2@t")
    ids = {a["id"] for a in (await client.get("/athletes", headers=coach2)).json()["items"]}
    assert ids == {S["a2"]}
    assert (await client.get(f"/athletes/{S['a1']}", headers=coach2)).status_code == 404


async def test_lead_dedupe_trial_and_conversion(client, admin, conn):
    lead = {"child_name": "Mert", "child_birth_year": 2014, "guardian_name": "Ayşe", "phone": "+905000000099",
            "channel": "META_ADS", "kvkk_consent": True}
    r1 = (await client.post("/crm/leads", json=lead, headers=admin)).json()
    r2 = (await client.post("/crm/leads", json=lead | {"channel": "GOOGLE_ADS"}, headers=admin)).json()
    assert r1["created"] and not r2["created"] and r1["id"] == r2["id"]
    lid = r1["id"]

    await client.post(f"/crm/leads/{lid}/activities", json={"type": "CALL"}, headers=admin)
    row = await conn.fetchrow("SELECT stage, first_contact_at FROM leads WHERE id=$1", lid)
    assert row["stage"] == "CONTACTED" and row["first_contact_at"] is not None

    future = await conn.fetchval("SELECT id FROM training_sessions WHERE starts_at > now() AND status='PLANNED' LIMIT 1")
    r = await client.post(f"/crm/leads/{lid}/trials", json={"session_id": future}, headers=admin)
    assert r.status_code == 201
    await client.patch(f"/crm/trials/{r.json()['id']}", json={"status": "ATTENDED", "coach_rating": 4}, headers=admin)
    assert await conn.fetchval("SELECT stage FROM leads WHERE id=$1", lid) == "TRIAL_ATTENDED"

    assert (await client.patch(f"/crm/leads/{lid}/stage", json={"stage": "WON"}, headers=admin)).status_code == 422
    r = await client.post(f"/crm/leads/{lid}/convert",
                          json=athlete_payload("MERT", "+905000000099", S["U 12-A"], "2014-03-03"), headers=admin)
    assert r.status_code == 201
    assert await conn.fetchval("SELECT athlete_id FROM leads WHERE id=$1", lid) == r.json()["athlete_id"]
    assert (await client.post(f"/crm/leads/{lid}/convert",
                              json=athlete_payload("MERT", "+905000000099", S["U 12-A"]), headers=admin)).status_code == 409


async def test_assessment_and_progress(client, admin):
    for when, cmj in (("2026-01-10", 30.0), ("2026-04-10", 36.0)):
        r = await client.post("/performance/assessments", json={"athlete_id": S["a1"], "assessed_at": when,
                                                                 "measurements": []}, headers=admin)
        assert r.status_code == 201
    r = await client.post("/performance/assessments", json={
        "athlete_id": S["a1"], "assessed_at": "2026-05-01", "measurements": [{"code": "yok", "value": 1}]}, headers=admin)
    assert r.status_code == 422


async def test_box_score_validation(client, admin):
    g = (await client.post("/performance/games", json={"team_id": S["U 14-A"], "opponent": "Rakip",
                                                       "played_at": datetime.now(TZ).isoformat(), "is_home": True},
                           headers=admin)).json()["id"]
    bad = [{"athlete_id": S["a1"], "pts": 10, "fgm": 3, "fga": 8, "tpm": 1, "tpa": 3, "ftm": 0, "fta": 0}]
    assert (await client.put(f"/performance/games/{g}/stats", json=bad, headers=admin)).status_code == 422
    ok = [{"athlete_id": S["a1"], "pts": 9, "fgm": 3, "fga": 8, "tpm": 1, "tpa": 3, "ftm": 2, "fta": 2, "ast": 4, "tov": 2}]
    assert (await client.put(f"/performance/games/{g}/stats", json=ok, headers=admin)).status_code == 200
    games = (await client.get(f"/athletes/{S['a1']}/progress", headers=admin)).json()["games"]
    assert games["games"] == 1 and games["pts"] == 9.0 and games["ast_tov"] == 2


async def test_executive_dashboard_shape(client, admin):
    r = await client.get("/dashboard/executive", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["finance"]["collected"] == pytest.approx(4500)
    assert d["finance"]["overdue"]["count"] == 2
    m = d["marketing"]
    assert m["leads"] == 1 and m["won"] == 1
    assert [s["stage"] for s in m["funnel"]] == ["LEAD", "CONTACTED", "TRIAL_BOOKED", "TRIAL_ATTENDED", "WON"]
    assert (await client.get("/dashboard/executive?date_from=2026-05-01&date_to=2026-01-01",
                             headers=admin)).status_code == 422


async def test_month_close_and_payroll(client, admin, conn):
    period = (datetime.now(TZ) - timedelta(days=2, hours=3)).date().replace(day=1)
    ts = (await client.post(f"/hr/timesheets/{period}/close", headers=admin)).json()
    mine = next(t for t in ts if t["staff_id"] == 1)
    assert mine["total_minutes"] == 90 and mine["session_count"] == 1
    assert (await client.post(f"/hr/payroll/{period}/draft", headers=admin)).json()["payrolls"] >= 1
    hourly = await conn.fetchval("SELECT hourly_gross FROM payrolls WHERE staff_id=1 AND period=$1", period)
    assert float(hourly) == 750.0  # 1.5 saat × 500 TL
