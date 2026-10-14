"""Demo verisi. `python -m app.seed --athletes 750` gerçek kulüp ölçeğinde veri üretir.

Varsayılan kullanıcılar (şifre: EgeAlfa!2026 — ilk girişten sonra değiştirin):
  admin@egealfa.com, koc@egealfa.com, finans@egealfa.com, pazarlama@egealfa.com
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from prisma import Prisma

from .core.security import hash_password
from .core.timeutil import add_months, as_dt

PASSWORD = "EgeAlfa!2026"
FIRST = [
    "Ali",
    "Ece",
    "Can",
    "Deniz",
    "Eren",
    "Zeynep",
    "Mert",
    "Elif",
    "Kaan",
    "Defne",
    "Arda",
    "Ada",
    "Emir",
    "Nehir",
]
LAST = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Aydın", "Öztürk", "Arslan", "Doğan", "Koç", "Kurt", "Polat"]
TEST_TYPES = [
    ("HEIGHT", "Boy", "ANTHROPOMETRIC", "cm", True, "0.5"),
    ("SITTING_HEIGHT", "Oturma boyu", "ANTHROPOMETRIC", "cm", True, "0.5"),
    ("WEIGHT", "Kilo", "ANTHROPOMETRIC", "kg", True, "0.3"),
    ("WINGSPAN", "Kanat açıklığı", "ANTHROPOMETRIC", "cm", True, "0.8"),
    ("CMJ", "Countermovement jump", "POWER", "cm", True, "1.5"),
    ("SPRINT_20M", "20 m sprint", "SPEED", "s", False, "0.04"),
    ("LANE_AGILITY", "Lane agility", "AGILITY", "s", False, "0.15"),
    ("YOYO_IR1", "Yo-Yo IR1", "ENDURANCE", "m", True, "60"),
    ("FT_PCT", "Serbest atış (50 atış)", "SKILL", "%", True, "5"),
]
TEAMS = [  # ad, yaş grubu, cinsiyet, seviye, plan
    ("U8 Karma Okul", "U8", "MIXED", "SCHOOL", "Okul 2x"),
    ("U10 Karma Okul", "U10", "MIXED", "SCHOOL", "Okul 2x"),
    ("U12 Erkek", "U12", "MALE", "DEVELOPMENT", "Gelişim 3x"),
    ("U12 Kız", "U12", "FEMALE", "DEVELOPMENT", "Gelişim 3x"),
    ("U14 Erkek A", "U14", "MALE", "PERFORMANCE", "Performans 4x"),
    ("U14 Kız A", "U14", "FEMALE", "PERFORMANCE", "Performans 4x"),
    ("U16 Erkek A", "U16", "MALE", "PERFORMANCE", "Performans 4x"),
    ("U16 Kız A", "U16", "FEMALE", "PERFORMANCE", "Performans 4x"),
    ("U18 Erkek", "U18", "MALE", "PERFORMANCE", "Performans 4x"),
]
BIRTH_BASE = {"U8": 2019, "U10": 2017, "U12": 2015, "U14": 2013, "U16": 2011, "U18": 2009}


async def seed(db: Prisma, athletes: int, rnd: random.Random) -> dict:
    today = date.today()
    season = await db.season.create(
        data={
            "name": f"{today.year}-{today.year + 1}",
            "startsOn": as_dt(date(today.year, 9, 1)),
            "endsOn": as_dt(date(today.year + 1, 6, 30)),
            "isActive": True,
        }
    )
    venue = await db.venue.create(data={"name": "Ege Alfa Spor Salonu", "address": "İzmir", "isOwned": False})
    courts = [
        await db.court.create(
            data={"venueId": venue.id, "name": n, "type": "INDOOR_HALL", "hourlyCost": Decimal("1200")}
        )
        for n in ("Salon A - Yarı 1", "Salon A - Yarı 2", "Salon B")
    ]
    gym = await db.court.create(data={"venueId": venue.id, "name": "Kondisyon", "type": "GYM", "capacity": 12})
    plans = {
        n: await db.feeplan.create(data={"name": n, "monthlyAmount": Decimal(a), "vatRate": Decimal("0"), "dueDay": 5})
        for n, a in (("Okul 2x", "2000"), ("Gelişim 3x", "2750"), ("Performans 4x", "3500"))
    }
    pw = hash_password(PASSWORD)
    users = {}
    for email, role, dept, title in (
        ("admin@egealfa.com", "ADMIN", "ADMINISTRATION", "Kulüp Müdürü"),
        ("finans@egealfa.com", "FINANCE", "FINANCE", "Muhasebe Uzmanı"),
        ("pazarlama@egealfa.com", "MARKETING", "MARKETING", "Dijital Pazarlama"),
    ):
        u = await db.user.create(data={"email": email, "passwordHash": pw, "role": role})
        users[role] = await db.staff.create(
            data={
                "userId": u.id,
                "firstName": title.split()[0],
                "lastName": "Ege",
                "department": dept,
                "title": title,
                "employmentType": "FULL_TIME",
                "payType": "MONTHLY",
                "baseSalary": Decimal("45000"),
                "hireDate": as_dt(date(2023, 1, 1)),
            }
        )
    coaches = []
    for i in range(12):
        data = {
            "firstName": FIRST[i % len(FIRST)],
            "lastName": LAST[i % len(LAST)],
            "department": "COACHING",
            "title": "Antrenör",
            "employmentType": "FULL_TIME" if i < 6 else "PART_TIME",
            "payType": "MIXED" if i < 6 else "PER_SESSION",
            "baseSalary": Decimal("30000") if i < 6 else Decimal(0),
            "sessionRate": Decimal("450"),
            "coachLicenseLevel": str(2 + i % 3),
            "licenseExpiresOn": as_dt(today + timedelta(days=30 * (i + 1))),
            "hireDate": as_dt(date(2022, 9, 1)),
        }
        if i == 0:
            u = await db.user.create(data={"email": "koc@egealfa.com", "passwordHash": pw, "role": "COACH"})
            data["userId"] = u.id
        coaches.append(await db.staff.create(data=data))

    teams = []
    for i, (name, ag, g, lvl, plan) in enumerate(TEAMS):
        t = await db.team.create(
            data={
                "seasonId": season.id,
                "name": name,
                "ageGroup": ag,
                "gender": g,
                "level": lvl,
                "headCoachId": coaches[i % len(coaches)].id,
                "feePlanId": plans[plan].id,
                "capacity": 90,
            }
        )
        teams.append((t, plan, ag))
        # Haftalık şablon: takım başına 2-4 gün, saha/koç çakışmasız saat ızgarası.
        days = {"Okul 2x": (1, 3), "Gelişim 3x": (0, 2, 4), "Performans 4x": (0, 1, 3, 4)}[plan]
        hour = 16 + (i // 3) * 2 if i < 9 else 20
        for wd in days:
            await db.recurringslot.create(
                data={
                    "teamId": t.id,
                    "courtId": courts[i % 3].id,
                    "coachId": coaches[i % len(coaches)].id,
                    "weekday": wd,
                    "startTime": f"{hour:02d}:00",
                    "endTime": f"{hour + 1:02d}:30",
                    "validFrom": as_dt(date(today.year, 9, 1)),
                }
            )
    for code, name, cat, unit, hib, te in TEST_TYPES:
        await db.physicaltesttype.create(
            data={
                "code": code,
                "name": name,
                "category": cat,
                "unit": unit,
                "higherIsBetter": hib,
                "typicalError": Decimal(te),
            }
        )

    # Sporcular + veliler (~%12 kardeş)
    guardians: list = []
    for n in range(athletes):
        team, plan, ag = teams[n % len(teams)]
        if guardians and rnd.random() < 0.12:
            g = rnd.choice(guardians)
        else:
            g = await db.guardian.create(
                data={
                    "firstName": rnd.choice(FIRST),
                    "lastName": rnd.choice(LAST),
                    "phone": f"+90532{1000000 + n:07d}",
                    "email": f"veli{n}@ornek.com",
                }
            )
            guardians.append(g)
        siblings = await db.athleteguardian.count(where={"guardianId": g.id})
        joined = add_months(today.replace(day=1), -rnd.randint(1, 18))
        gender = team.gender if team.gender != "MIXED" else rnd.choice(["MALE", "FEMALE"])
        a = await db.athlete.create(
            data={
                "firstName": rnd.choice(FIRST),
                "lastName": g.lastName,
                "gender": gender,
                "birthDate": as_dt(date(BIRTH_BASE[ag] + rnd.randint(0, 1), rnd.randint(1, 12), rnd.randint(1, 28))),
                "joinedOn": as_dt(joined),
            }
        )
        await db.athleteguardian.create(
            data={"athleteId": a.id, "guardianId": g.id, "relation": "ANNE", "isBillingContact": True}
        )
        await db.teammembership.create(data={"athleteId": a.id, "teamId": team.id, "joinedOn": as_dt(joined)})
        disc = Decimal({0: 0, 1: 10}.get(siblings, 15))
        await db.subscription.create(
            data={
                "athleteId": a.id,
                "feePlanId": plans[plan].id,
                "startsOn": as_dt(joined),
                "discountPct": disc,
                "discountReason": "SIBLING" if disc else "NONE",
            }
        )

    # Kampanyalar + 6 aylık harcama + lead'ler
    camps = [
        await db.adcampaign.create(data={"platform": p, "externalId": x, "name": nm, "objective": "LEAD_GENERATION"})
        for p, x, nm in (
            ("META", "120201", "Yaz Okulu Lead Form"),
            ("META", "120202", "Instagram Reels Deneme"),
            ("GOOGLE", "g-881", "Arama: izmir basketbol kursu"),
        )
    ]
    start = add_months(today.replace(day=1), -5)
    d = start
    spend_rows = []
    while d < today:
        for c, base in zip(camps, (450, 300, 250), strict=True):
            spend_rows.append(
                {
                    "campaignId": c.id,
                    "date": as_dt(d),
                    "spend": Decimal(base + rnd.randint(-80, 80)),
                    "impressions": rnd.randint(3000, 9000),
                    "clicks": rnd.randint(40, 160),
                }
            )
        d += timedelta(days=1)
    await db.adspenddaily.create_many(data=spend_rows)

    sources = ["META_LEAD_AD"] * 5 + ["GOOGLE_LEAD_FORM"] * 2 + ["REFERRAL", "WEBSITE", "WALK_IN", "INSTAGRAM_DM"]
    for n in range(max(60, athletes // 3)):
        src = rnd.choice(sources)
        camp = camps[rnd.randint(0, 1)] if src == "META_LEAD_AD" else camps[2] if src == "GOOGLE_LEAD_FORM" else None
        created = datetime.combine(
            start + timedelta(days=rnd.randint(0, (today - start).days - 1)), datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=rnd.randint(8, 21))
        r = rnd.random()
        stage = (
            "NEW"
            if r < 0.10
            else "LOST"
            if r < 0.45
            else "CONTACTED"
            if r < 0.55
            else "TRIAL_SCHEDULED"
            if r < 0.65
            else "TRIAL_ATTENDED"
            if r < 0.75
            else "WON"
        )
        order = ["NEW", "CONTACTED", "TRIAL_SCHEDULED", "TRIAL_ATTENDED", "WON"]
        reached = order.index(stage) if stage != "LOST" else rnd.randint(1, 3)
        ms = {}
        for i, f in enumerate(("firstContactAt", "trialScheduledAt", "trialAttendedAt", "wonAt"), start=1):
            if reached >= i:
                ms[f] = created + timedelta(minutes=rnd.randint(5, 240) * i)
        await db.lead.create(
            data={
                "parentName": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
                "phone": f"+90533{2000000 + n:07d}",
                "source": src,
                "campaignId": camp.id if camp else None,
                "stage": stage,
                "lostReason": rnd.choice(["fiyat", "mesafe", "saat uymuyor", "ulaşılamadı"])
                if stage == "LOST"
                else None,
                "createdAt": created,
                **ms,
            }
        )
    await _history(db, start, today, rnd)
    return {
        "season": season.id,
        "teams": len(teams),
        "coaches": len(coaches),
        "athletes": athletes,
        "courts": len(courts) + 1,
        "gym": gym.id,
    }


async def _history(db: Prisma, start: date, today: date, rnd: random.Random) -> None:
    """6 aylık finans geçmişi: tahakkuk → %93 tahsilat, giderler, churn, lead → sporcu atfı."""
    from .services.billing import generate_monthly_charges

    m = start
    while m <= today:
        await generate_monthly_charges(m)
        m = add_months(m, 1)
    await db.execute_raw("SELECT setseed(0.42)")
    await db.execute_raw(
        """
        WITH paid AS (
          SELECT c."id", c."guardianId", c."netAmount", c."dueDate", gen_random_uuid() AS pid
          FROM "Charge" c
          WHERE random() < CASE WHEN c."period" < date_trunc('month', CURRENT_DATE) THEN 0.93 ELSE 0.80 END
        ), pay AS (
          INSERT INTO "Payment" ("id", "guardianId", "amount", "method", "status", "paidAt")
          SELECT pid, "guardianId", "netAmount", 'BANK_TRANSFER', 'COMPLETED',
                 "dueDate" - (floor(random() * 6))::int * interval '1 day' FROM paid
        ), alloc AS (
          INSERT INTO "PaymentAllocation" ("paymentId", "chargeId", "amount") SELECT pid, "id", "netAmount" FROM paid
        )
        UPDATE "Charge" c SET "paidAmount" = c."netAmount", "status" = 'PAID' FROM paid WHERE paid."id" = c."id"
        """
    )
    await db.execute_raw(
        """UPDATE "Charge" SET "status" = 'OVERDUE'
           WHERE "status" = 'PENDING' AND "dueDate" < CURRENT_DATE"""
    )
    rows = []
    m = start
    while m <= today:
        for cat, amount, vendor in (
            ("SALARY", 1_250_000, None),
            ("RENT", 420_000, "Belediye Spor Tesisleri"),
            ("UTILITIES", 45_000, None),
            ("TOURNAMENT", 30_000, "İzmir İl Temsilciliği"),
            ("EQUIPMENT", rnd.randint(20_000, 60_000), "Spor malzemesi"),
        ):
            rows.append({"category": cat, "amount": Decimal(amount), "incurredOn": as_dt(m), "vendor": vendor})
        m = add_months(m, 1)
    await db.expense.create_many(data=rows)
    # Churn: son 90 günde ayrılan ~%2
    await db.execute_raw(
        """
        WITH gone AS (SELECT "id" FROM "Athlete" WHERE "joinedOn" < CURRENT_DATE - 120 ORDER BY random() LIMIT 15)
        UPDATE "Athlete" a SET "status" = 'LEFT', "leftOn" = CURRENT_DATE - (floor(random() * 80))::int,
                              "leaveReason" = 'demo' FROM gone WHERE gone."id" = a."id"
        """
    )
    await db.execute_raw(
        """UPDATE "Subscription" s SET "status" = 'ENDED', "endsOn" = a."leftOn"
           FROM "Athlete" a WHERE a."id" = s."athleteId" AND a."status" = 'LEFT'"""
    )
    # Kazanılan lead'leri son 6 ayda katılan sporculara bağla (atıf zinciri → ROI)
    await db.execute_raw(
        """
        WITH w AS (SELECT "id", row_number() OVER (ORDER BY "wonAt") AS rn FROM "Lead" WHERE "stage" = 'WON'),
             a AS (SELECT "id", row_number() OVER (ORDER BY "joinedOn" DESC) AS rn FROM "Athlete"
                   WHERE "status" = 'ACTIVE' AND "joinedOn" >= CURRENT_DATE - 190)
        UPDATE "Lead" l SET "convertedAthleteId" = a."id" FROM w JOIN a ON a.rn = w.rn WHERE l."id" = w."id"
        """
    )


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--athletes", type=int, default=120)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    from .core.db import db  # servislerle aynı istemci

    await db.connect()
    try:
        if await db.user.count() > 0:
            print("Veritabanı boş değil, seed atlandı.")
            return
        print(await seed(db, args.athletes, random.Random(args.seed)))
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
