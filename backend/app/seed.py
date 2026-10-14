"""Gerçekçi ölçekte SENTETİK demo verisi: 750 sporcu, 35 personel, 28 takım, ~6 ay geçmiş.

Kişi adları rastgele üretilir — gerçek çocuk verisi asla seed'e konmaz (KVKK).
Fatura/puantaj/seans üretimi uygulamanın kendi servisleriyle yapılır (dogfooding).
Kullanım: python -m app.seed  (boş veritabanı üzerinde)
"""
import asyncio
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from .core import db
from .core.config import get_settings
from .core.security import hash_password
from .services import billing, scheduling

R = random.Random(42)
TODAY = date.today()
START = (TODAY.replace(day=1) - timedelta(days=150)).replace(day=1)

FIRST_M = ["Can", "Ege", "Kuzey", "Arda", "Deniz", "Emir", "Mert", "Efe", "Bora", "Alp", "Kaan", "Yiğit", "Ata",
           "Toprak", "Rüzgar", "Batu", "Doruk", "Eren", "Berk", "Umut", "Çınar", "Aras", "Demir", "Poyraz"]
FIRST_F = ["Ela", "Zeynep", "Defne", "Elif", "Ada", "Nehir", "Duru", "Lina", "Mira", "Asya", "Ece", "Derin"]
LAST = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk", "Arslan", "Doğan", "Kılıç",
        "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek", "Polat", "Erdem", "Güneş", "Tekin", "Aksoy"]
TEAMS = ["U 10-A", "U 10-B", "U 10-C", "U 10-D", "U 11-A", "U 11-B", "U 11-C", "U 12-A", "U 12-B", "U 12-C",
         "U 13-A", "U 13-B", "U 13-C", "U 14-A", "U 14-B", "U 14-C", "U 15-A", "U 15-B", "U 15-C", "U 16-A",
         "U 16-B", "U 16-C", "U 17-A", "U 17-B", "U 17-C", "U 18-A", "U 18-B", "U 18-C"]
METRICS = [  # code, name, unit, category, higher_is_better, typical_error (literatür yaklaşığı — yerelde ölçülmeli)
    ("boy", "Boy", "cm", "ANTHROPOMETRIC", True, 0.3), ("kilo", "Kilo", "kg", "ANTHROPOMETRIC", True, 0.3),
    ("kulac", "Kulaç", "cm", "ANTHROPOMETRIC", True, 0.5),
    ("oturma_boyu", "Oturma Boyu", "cm", "ANTHROPOMETRIC", True, 0.4),
    ("sprint10", "Sprint 10m", "s", "ATHLETIC", False, 0.04), ("sprint20", "Sprint 20m", "s", "ATHLETIC", False, 0.05),
    ("cmj", "CMJ", "cm", "ATHLETIC", True, 1.5), ("ttest", "T-Test", "s", "ATHLETIC", False, 0.15),
    ("vcut", "V-Cut", "s", "ATHLETIC", False, 0.15),
    *[(c, n, "puan", "FUNDAMENTAL", True, 0.5) for c, n in [
        ("dribbling", "Dribbling"), ("pas", "Pas"), ("sut", "Şut"), ("footwork", "Footwork"), ("savunma", "Savunma"),
        ("hiz_cabukluk", "Hız/Çabukluk"), ("rebound", "Rebound"), ("oyun_gorusu", "Oyun Görüşü")]],
]


def phone() -> str:
    return f"+905{R.randint(30, 59)}{R.randint(1000000, 9999999)}"


async def seed() -> None:
    await db.connect()
    tz = get_settings().tz
    async with db.pool().acquire() as c:
        if await c.fetchval("SELECT COUNT(*) FROM athletes"):
            print("Veritabanı dolu, seed atlandı.")
            return
        pw = hash_password("demo1234")

        # ── Personel (35) ──
        staff_spec = ([("COACHING", "Antrenör", "PART_TIME")] * 18 + [("COACHING", "Baş Antrenör", "FULL_TIME")] * 4 +
                      [("COACHING", "Kondisyoner", "HOURLY")] * 2 + [("ADMINISTRATION", "İdari Personel", "FULL_TIME")] * 5 +
                      [("MARKETING", "Dijital Pazarlama", "FULL_TIME")] * 3 + [("FINANCE", "Muhasebe", "FULL_TIME")] * 2 +
                      [("OPERATIONS", "Tesis Sorumlusu", "FULL_TIME")])
        staff_ids: dict[str, list[int]] = {}
        for i, (dept, title, emp) in enumerate(staff_spec):
            sid = await c.fetchval(
                """INSERT INTO staff (first_name, last_name, department, title, employment_type, monthly_salary,
                       hourly_rate, hire_date, email, coach_license)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id""",
                R.choice(FIRST_M + FIRST_F), R.choice(LAST), dept, title, emp,
                {"FULL_TIME": Decimal(R.choice([38000, 45000, 55000])), "PART_TIME": Decimal(22000)}.get(emp),
                Decimal(R.choice([450, 550, 650])) if emp != "FULL_TIME" else None,
                date(2023, 9, 1), f"personel{i + 1}@egealfa.com",
                R.choice(["1. Kademe", "2. Kademe", "3. Kademe"]) if dept == "COACHING" else None)
            staff_ids.setdefault(dept, []).append(sid)
        coaches = staff_ids["COACHING"][:22]

        users = [("admin@egealfa.com", "ADMIN", None), ("direktor@egealfa.com", "MANAGER", coaches[18]),
                 ("koc@egealfa.com", "COACH", coaches[0]), ("muhasebe@egealfa.com", "ACCOUNTANT", staff_ids["FINANCE"][0]),
                 ("pazarlama@egealfa.com", "MARKETING", staff_ids["MARKETING"][0])]
        for email, role, sid in users:
            await c.execute("INSERT INTO users (email, password_hash, role, staff_id) VALUES ($1,$2,$3,$4)",
                            email, pw, role, sid)

        # ── Tesis, sezon, aidat planı, takımlar ──
        facilities = [await c.fetchval(
            "INSERT INTO facilities (name, type, capacity, hourly_cost) VALUES ($1,$2,$3,$4) RETURNING id",
            n, t, cap, Decimal(cost)) for n, t, cap, cost in [
            ("Ana Salon - Saha 1", "COURT", 30, 1500), ("Ana Salon - Saha 2", "COURT", 30, 1500),
            ("Okul Salonu", "COURT", 30, 900), ("Belediye Spor Salonu", "COURT", 30, 1100),
            ("Kuvvet Salonu", "GYM", 16, 400)]]
        courts = facilities[:4]
        season = await c.fetchval(
            "INSERT INTO seasons (name, start_date, end_date, is_active) VALUES ('2026-2027',$1,$2,true) RETURNING id",
            START, START + timedelta(days=364))
        plans = {n: await c.fetchval(
            "INSERT INTO fee_plans (name, monthly_amount) VALUES ($1,$2) RETURNING id", n, Decimal(a))
            for n, a in [("Basketbol Okulu", 3500), ("Altyapı Gelişim", 4500), ("Performans Takımı", 5500)]}
        teams = []
        for i, name in enumerate(TEAMS):
            age = int(name[2:4])
            level, plan = (("SCHOOL", "Basketbol Okulu") if age <= 11 else
                           ("PERFORMANCE", "Performans Takımı") if name.endswith("-A") else ("DEVELOPMENT", "Altyapı Gelişim"))
            tid = await c.fetchval(
                """INSERT INTO teams (season_id, name, age_group, level, head_coach_id, max_athletes, default_fee_plan_id)
                   VALUES ($1,$2,$3,$4,$5,30,$6) RETURNING id""",
                season, name, f"U{age}", level, coaches[i % 22], plans[plan])
            teams.append((tid, name, age, coaches[i % 22]))

        # ── Haftalık şablonlar: saha/koç çakışmasız açgözlü yerleşim ──
        slots = [(wd, t) for wd in range(1, 6) for t in ("16:00", "17:30", "19:00", "20:30")] + \
                [(6, t) for t in ("09:00", "10:30", "12:00", "13:30", "15:00", "16:30")]
        used_fac, used_coach = set(), set()
        for tid, _, age, coach in teams:
            placed, wd_used = 0, set()
            for wd, t in R.sample(slots, len(slots)):
                if placed == 3:
                    break
                if wd in wd_used or (wd, t, coach) in used_coach:
                    continue
                fac = next((f for f in courts if (wd, t, f) not in used_fac), None)
                if fac is None:
                    continue
                used_fac.add((wd, t, fac))
                used_coach.add((wd, t, coach))
                wd_used.add(wd)
                await c.execute(
                    """INSERT INTO training_plans (team_id, coach_id, facility_id, weekday, start_time, duration_min,
                           valid_from, focus) VALUES ($1,$2,$3,$4,$5,90,$6,$7)""",
                    tid, coach, fac, wd, t, START, R.choice(["Şut mekaniği", "Savunma", "Hücum setleri", "Fundamental"]))
                placed += 1

        await c.executemany(
            "INSERT INTO drills (name, category, description) VALUES ($1,$2,$3)",
            [("Mikan Drill", "ŞUT", "Çember altı iki el bitiriş ritmi"), ("Form Shooting", "ŞUT", "Tek el mekanik, 1-2 m"),
             ("Zig-Zag Savunma", "SAVUNMA", "Kayma adımı + yön değiştirme"), ("Closeout 1v1", "SAVUNMA", "Kapanış ve top yönlendirme"),
             ("3v2 / 2v1 Geçiş", "OYUN", "Hızlı hücum karar verme"), ("Small-Sided 3v3", "OYUN", "Yarım saha kısıtlı oyun"),
             ("Dinamik Isınma (FIFA 11+ uyarlaması)", "ISINMA", "Sakatlık önleme ısınma protokolü"),
             ("Pliometrik Seri", "ATLETİK", "Düşük hacimli sıçrama-iniş mekaniği")])

        # ── Kampanyalar + günlük harcama ──
        camps = []
        for name, ch, ext, daily in [("Meta - Okul Kayıt", "META_ADS", "120201", 900), ("Meta - Altyapı Seçmeleri", "META_ADS", "120202", 600),
                                     ("Google - Basketbol Kursu İzmir", "GOOGLE_ADS", "9001", 700),
                                     ("TikTok - Yaz Kampı", "TIKTOK_ADS", "7001", 350),
                                     ("Okul Tanıtım Turu", "SCHOOL_EVENT", None, 0), ("Veli Tavsiye Programı", "REFERRAL", None, 0)]:
            cid = await c.fetchval(
                "INSERT INTO campaigns (name, channel, external_id, start_date) VALUES ($1,$2,$3,$4) RETURNING id",
                name, ch, ext, START)
            camps.append((cid, ch, daily))
            if daily:
                await c.executemany(
                    """INSERT INTO ad_spend_daily (campaign_id, date, spend, impressions, clicks, platform_leads)
                       VALUES ($1,$2,$3,$4,$5,$6)""",
                    [(cid, START + timedelta(days=d), Decimal(round(daily * R.uniform(0.7, 1.3), 2)),
                      int(daily * R.uniform(80, 120)), int(daily * R.uniform(1.2, 2.2)), R.randint(0, 4))
                     for d in range((TODAY - START).days)])
            else:
                await c.execute(
                    "INSERT INTO expenses (category, amount, spent_at, description, campaign_id) VALUES ('MARKETING',$1,$2,$3,$4)",
                    Decimal(R.choice([8000, 12000])), START + timedelta(days=20), f"{name} giderleri", cid)

        # ── Sporcular (750), veliler, abonelik ──
        guardians: list[int] = []
        athlete_rows = []
        for n in range(750):
            tid, tname, age, _ = teams[n % len(teams)]
            gender = "FEMALE" if R.random() < 0.15 else "MALE"
            # %12 kardeş: mevcut veliyi tekrar kullan → kardeş indirimi senaryosu.
            if guardians and R.random() < 0.12:
                gid = R.choice(guardians)
            else:
                gid = await c.fetchval(
                    """INSERT INTO guardians (full_name, phone, kvkk_consent_at, marketing_consent_at)
                       VALUES ($1,$2, now(), CASE WHEN $3 THEN now() END) ON CONFLICT (phone) DO NOTHING RETURNING id""",
                    f"{R.choice(FIRST_M + FIRST_F)} {R.choice(LAST)}", phone(), R.random() < 0.6)
                if gid is None:
                    continue
                guardians.append(gid)
            birth = date(TODAY.year - age + 1, R.randint(1, 12), R.randint(1, 28))
            joined = START - timedelta(days=R.randint(0, 900))
            aid = await c.fetchval(
                """INSERT INTO athletes (first_name, last_name, birth_date, gender, status, joined_at,
                       health_report_expires_at, photo_consent)
                   VALUES ($1,$2,$3,$4,'ACTIVE',$5,$6,$7) RETURNING id""",
                R.choice(FIRST_F if gender == "FEMALE" else FIRST_M).upper(), R.choice(LAST).upper(), birth, gender,
                joined, TODAY + timedelta(days=R.randint(-20, 300)), R.random() < 0.7)
            await c.execute("INSERT INTO athlete_guardians (athlete_id, guardian_id, relation, is_primary) VALUES ($1,$2,'VELİ',true)",
                            aid, gid)
            await c.execute("INSERT INTO team_memberships (athlete_id, team_id, start_date) VALUES ($1,$2,$3)", aid, tid, START)
            fp = await c.fetchval("SELECT default_fee_plan_id FROM teams WHERE id=$1", tid)
            await c.execute(
                """INSERT INTO subscriptions (athlete_id, guardian_id, fee_plan_id, discount_pct, start_date, billing_day)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                aid, gid, fp, Decimal(R.choice([0] * 9 + [25, 50])), START, R.choice([1, 5, 10, 15]))
            athlete_rows.append((aid, tid, gender, age, birth))

        # ── Seanslar (servisle üretim) + yoklama + puantaj ──
        week = scheduling.week_start(START)
        while week <= TODAY + timedelta(days=7):
            await scheduling.generate_week(c, week)
            week += timedelta(days=7)
        roster: dict[int, list[int]] = {}
        for aid, tid, *_ in athlete_rows:
            roster.setdefault(tid, []).append(aid)
        past = await c.fetch("SELECT id, team_id FROM training_sessions WHERE ends_at < now() AND status='PLANNED'")
        att = []
        for s in past:
            if R.random() < 0.03:
                await c.execute("UPDATE training_sessions SET status='CANCELLED', cancel_reason='Salon arızası' WHERE id=$1", s["id"])
                continue
            for aid in roster.get(s["team_id"], []):
                p = R.random()
                st = "PRESENT" if p < 0.82 else "LATE" if p < 0.86 else "EXCUSED" if p < 0.93 else "ABSENT"
                att.append((s["id"], aid, st, R.randint(4, 8) if st in ("PRESENT", "LATE") else None))
        await c.copy_records_to_table("attendances", records=att, columns=["session_id", "athlete_id", "status", "rpe"])
        for s in past:
            try:
                await scheduling.complete_session(c, s["id"])
            except ValueError:
                pass

        # ── Ölçümler: 2 test günü (sezon başı + ara dönem) ──
        mids = {r["code"]: r["id"] for r in [await c.fetchrow(
            """INSERT INTO metric_definitions (code, name, unit, category, higher_is_better, typical_error)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING id, code""", code, n, u, cat, hib, Decimal(str(te)))
            for code, n, u, cat, hib, te in METRICS]}
        for aid, _, gender, age, _ in athlete_rows:
            h0 = 120 + (age - 9) * 6.5 + R.gauss(0, 6) - (4 if gender == "FEMALE" else 0)
            base = {"boy": h0, "kilo": h0 * 0.33 + R.gauss(0, 4), "kulac": h0 + R.gauss(1, 3), "oturma_boyu": h0 * 0.52,
                    "sprint10": 2.4 - (age - 9) * 0.1 + R.gauss(0, .12), "sprint20": 4.2 - (age - 9) * 0.13 + R.gauss(0, .15),
                    "cmj": 20 + (age - 9) * 2.6 + R.gauss(0, 4), "ttest": 13 - (age - 9) * 0.3 + R.gauss(0, .5),
                    "vcut": 9 - (age - 9) * 0.2 + R.gauss(0, .4)}
            for k in ("dribbling", "pas", "sut", "footwork", "savunma", "hiz_cabukluk", "rebound", "oyun_gorusu"):
                base[k] = R.randint(2, 7)
            for j, when in enumerate((START + timedelta(days=14), START + timedelta(days=120))):
                if when > TODAY:
                    continue
                asm = await c.fetchval(
                    "INSERT INTO assessments (athlete_id, assessed_at, context) VALUES ($1,$2,$3) RETURNING id",
                    aid, when, "Sezon başı" if j == 0 else "Ara dönem")
                vals = []
                for code, v in base.items():
                    hib = next(m[4] for m in METRICS if m[0] == code)
                    if j == 1:
                        drift = {"boy": 2.5, "kilo": 1.5, "kulac": 2.5, "oturma_boyu": 1.2}.get(code)
                        v = v + drift if drift else (min(10, v + R.choice([0, 0, 1, 1, 2])) if isinstance(v, int)
                                                     else v * (1 + (R.gauss(0.03, 0.03) * (1 if hib else -1))))
                    vals.append((asm, mids[code], Decimal(str(round(v, 2)))))
                await c.executemany("INSERT INTO measurements (assessment_id, metric_id, value) VALUES ($1,$2,$3)", vals)

        # ── Faturalar (servisle) + tahsilatlar ──
        period = START
        while period <= TODAY:
            await billing.generate_monthly_invoices(c, period)
            period = (period + timedelta(days=32)).replace(day=1)
        invs = await c.fetch("SELECT id, guardian_id, total, due_date FROM invoices ORDER BY id")
        for inv in invs:
            r = R.random()
            if inv["due_date"] > TODAY and r < 0.6:
                continue
            if r < 0.86 or (inv["due_date"] < TODAY - timedelta(days=60) and r < 0.95):
                paid_on = inv["due_date"] + timedelta(days=R.randint(-8, 12))
                amt = inv["total"] if R.random() < 0.95 else (inv["total"] / 2).quantize(Decimal("0.01"))
                await billing.record_payment(
                    c, guardian_id=inv["guardian_id"], invoice_id=inv["id"], amount=amt,
                    method=R.choice(["BANK_TRANSFER", "CREDIT_CARD", "ONLINE", "CASH"]),
                    paid_at=datetime.combine(min(paid_on, TODAY), time(12), tzinfo=tz))
        await c.execute("UPDATE notification_outbox SET status='SENT', sent_at=now()")  # demo: geçmiş bildirimler gitmiş say

        # ── Giderler + bordrolar ──
        period = START
        while period < TODAY.replace(day=1):
            for cat, amt in [("FACILITY_RENT", 160000), ("UTILITIES", 22000), ("EQUIPMENT", 15000),
                             ("TRAVEL", 18000), ("LEAGUE_FEES", 12000)]:
                await c.execute("INSERT INTO expenses (category, amount, spent_at, vendor) VALUES ($1,$2,$3,$4)",
                                cat, Decimal(round(amt * R.uniform(0.85, 1.15), 2)), period + timedelta(days=R.randint(2, 25)),
                                "Demo tedarikçi")
            await scheduling.close_month(c, period)
            await scheduling.draft_payrolls(c, period)
            await c.execute(
                """UPDATE payrolls SET status='PAID', paid_at=$2, net_pay=ROUND((base_gross + hourly_gross) * 0.71, 2)
                   WHERE period=$1""", period, datetime.combine(period + timedelta(days=35), time(10), tzinfo=UTC))
            period = (period + timedelta(days=32)).replace(day=1)

        # ── Lead'ler: kanal bazlı farklı dönüşüm profili ──
        profile = {"META_ADS": (3.5, .40, .55), "GOOGLE_ADS": (5, .50, .60), "TIKTOK_ADS": (4, .25, .35),
                   "SCHOOL_EVENT": (2, .60, .55), "REFERRAL": (1.5, .75, .70)}  # günlük lead, deneme oranı, kayıt oranı
        upcoming = await c.fetch(
            "SELECT id FROM training_sessions WHERE starts_at > now() AND status='PLANNED' ORDER BY starts_at LIMIT 40")
        past_sessions = [s["id"] for s in past]
        for cid, ch, _ in camps:
            per_day, p_trial, p_won = profile[ch]
            for d in range((TODAY - START).days):
                for _ in range(int(per_day) + (1 if R.random() < per_day % 1 else 0)):
                    created = datetime.combine(START + timedelta(days=d), time(R.randint(8, 22), R.randint(0, 59)), tzinfo=tz)
                    by = R.randint(2010, 2018)
                    contacted = created + timedelta(minutes=R.choice([4, 15, 45, 180, 600, 1500])) if R.random() < .85 else None
                    lid = await c.fetchval(
                        """INSERT INTO leads (child_name, child_birth_year, guardian_name, phone, channel, campaign_id,
                               created_at, first_contact_at, stage, kvkk_consent_at, utm_source)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$7,$10) RETURNING id""",
                        R.choice(FIRST_M), by, f"{R.choice(FIRST_F)} {R.choice(LAST)}", phone(), ch, cid, created,
                        contacted, "CONTACTED" if contacted else "NEW", ch.lower())
                    if not contacted or R.random() > p_trial or created.date() > TODAY - timedelta(days=3):
                        if contacted and R.random() < 0.5 and created.date() < TODAY - timedelta(days=14):
                            await c.execute("UPDATE leads SET stage='LOST', lost_reason=$2 WHERE id=$1", lid,
                                            R.choice(["Fiyat", "Mesafe", "Saat uyumu", "Ulaşılamadı", "Başka kulüp"]))
                        continue
                    sess = R.choice(past_sessions) if created.date() < TODAY - timedelta(days=10) else R.choice(upcoming)["id"]
                    attended = sess in past_sessions and R.random() < 0.8
                    await c.execute("INSERT INTO trial_bookings (lead_id, session_id, status) VALUES ($1,$2,$3)",
                                    lid, sess, "ATTENDED" if attended else ("NO_SHOW" if sess in past_sessions else "BOOKED"))
                    await c.execute(
                        """INSERT INTO lead_activities (lead_id, type, to_stage, created_at)
                           VALUES ($1,'STAGE_CHANGE','TRIAL_SCHEDULED',$2)""", lid, created + timedelta(days=R.randint(1, 4)))
                    stage = "TRIAL_ATTENDED" if attended else "TRIAL_SCHEDULED"
                    if attended and R.random() < p_won:
                        # Kazanılan lead'i, aynı yaş grubundaki bir mevcut sporcuya bağla (demo atıf zinciri).
                        aid = await c.fetchval(
                            """SELECT a.id FROM athletes a LEFT JOIN leads l ON l.athlete_id = a.id
                               WHERE l.id IS NULL ORDER BY random() LIMIT 1""")
                        await c.execute(
                            """UPDATE leads SET stage='WON', athlete_id=$2, converted_at=$3 WHERE id=$1""",
                            lid, aid, created + timedelta(days=R.randint(5, 12)))
                    else:
                        await c.execute("UPDATE leads SET stage=$2 WHERE id=$1", lid, stage)
        print("Seed tamam:", await c.fetchval("SELECT COUNT(*) FROM athletes"), "sporcu,",
              await c.fetchval("SELECT COUNT(*) FROM leads"), "lead,",
              await c.fetchval("SELECT COUNT(*) FROM invoices"), "fatura,",
              await c.fetchval("SELECT COUNT(*) FROM training_sessions"), "seans")
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
