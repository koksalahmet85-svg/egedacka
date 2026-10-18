"""Kurulum komutları (Docker ile: docker compose run --rm api python -m app.cli <komut> ...).

  create-admin  E-POSTA                      İlk yönetici hesabı (şifre sorulur)
  set-season    AD BAŞLANGIÇ BİTİŞ [--active] Sezon tanımı, ör. 2026-2027 2026-07-01 2027-06-30
  set-plan-price SEZON GRUP KADEME FİYAT [SON_GÜN] [ETİKET]
                                              ör. 2026-2027 ALTYAPI EARLY 107000 2026-07-31 "Erken kayıt"
  import-ledger DOSYA.xlsx                   Excel tahsilat defterini içe aktar
  diff-ledger   ESKI.xlsx YENI.xlsx          İki defter sürümünü kayıt bazında karşılaştır (veritabanı gerekmez)
"""
import argparse
import asyncio
import getpass
import sys
from datetime import date
from pathlib import Path

from .core import db
from .core.security import hash_password
from .services import ledger_store
from .services.ledger_diff import diff
from .services.ledger_import import parse_workbook


async def create_admin(email: str) -> None:
    pw = getpass.getpass("Şifre (en az 10 karakter): ")
    if len(pw) < 10 or pw != getpass.getpass("Şifre (tekrar): "):
        sys.exit("Şifre en az 10 karakter olmalı ve iki giriş aynı olmalı.")
    async with db.pool().acquire() as c:
        await c.execute(
            """INSERT INTO users (email, password_hash, role) VALUES (lower($1), $2, 'ADMIN')
               ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = 'ADMIN',
                 is_active = true""", email, hash_password(pw))
    print(f"Yönetici hazır: {email.lower()}")


async def set_season(name: str, start: str, end: str, active: bool) -> None:
    async with db.pool().acquire() as c, c.transaction():
        if active:
            await c.execute("UPDATE seasons SET is_active=false WHERE name <> $1", name)
        await c.execute(
            """INSERT INTO seasons (name, start_date, end_date, is_active) VALUES ($1,$2,$3,$4)
               ON CONFLICT (name) DO UPDATE SET start_date=EXCLUDED.start_date, end_date=EXCLUDED.end_date,
                 is_active=EXCLUDED.is_active""",
            name, date.fromisoformat(start), date.fromisoformat(end), active)
    print(f"Sezon kaydedildi: {name} ({start} → {end})")


async def set_plan_price(season: str, group: str, tier: str, price: str, until: str | None, label: str | None) -> None:
    async with db.pool().acquire() as c:
        sid = await c.fetchval("SELECT id FROM seasons WHERE name=$1", season)
        if sid is None:
            sys.exit(f"Önce sezonu tanımlayın: {season}")
        await c.execute(
            """INSERT INTO season_plan_prices (season_id, "group", tier, label, price, valid_until)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (season_id, "group", tier) DO UPDATE SET label=EXCLUDED.label, price=EXCLUDED.price,
                 valid_until=EXCLUDED.valid_until""",
            sid, group.upper(), tier.upper(), label, float(price), date.fromisoformat(until) if until else None)
    print(f"Kademe kaydedildi: {season} {group} {tier} {price}")


async def import_ledger(path: str) -> None:
    content = Path(path).read_bytes()
    parsed = parse_workbook(content)
    async with db.pool().acquire() as c:
        r = await ledger_store.store(c, parsed, Path(path).name, content, None)
    print(f"{len(r['sheets'])} sayfa, {r['rows']} satır içe aktarıldı; {r['anomalies']} veri uyarısı.")


def diff_ledger(old_path: str, new_path: str) -> None:
    res = diff(parse_workbook(Path(old_path).read_bytes()), parse_workbook(Path(new_path).read_bytes()))
    if not res.changes and not res.sheets_added and not res.sheets_removed:
        print("Değişiklik yok.")
        return
    for s in res.sheets_added:
        print(f"+ sayfa eklendi: {s}")
    for s in res.sheets_removed:
        print(f"- sayfa silindi: {s}")
    for c in res.changes:
        if c.kind != "MOVED":
            print(f"{c.kind:8} {c.sheet:12} satır {c.old_row or '-'}→{c.new_row or '-'}  {c.amount_delta:+,.2f}")
    print(f"Özet: {res.counts()}  net {res.net_delta():+,.2f} TL")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin"); a.add_argument("email")
    s = sub.add_parser("set-season"); s.add_argument("name"); s.add_argument("start"); s.add_argument("end")
    s.add_argument("--active", action="store_true")
    t = sub.add_parser("set-plan-price")
    for arg in ("season", "group", "tier", "price"):
        t.add_argument(arg)
    t.add_argument("until", nargs="?"); t.add_argument("label", nargs="?")
    i = sub.add_parser("import-ledger"); i.add_argument("path")
    d = sub.add_parser("diff-ledger"); d.add_argument("old"); d.add_argument("new")
    args = p.parse_args()
    if args.cmd == "diff-ledger":
        diff_ledger(args.old, args.new)
        return

    async def run():
        await db.connect()
        try:
            if args.cmd == "create-admin":
                await create_admin(args.email)
            elif args.cmd == "set-season":
                await set_season(args.name, args.start, args.end, args.active)
            elif args.cmd == "set-plan-price":
                await set_plan_price(args.season, args.group, args.tier, args.price, args.until, args.label)
            else:
                await import_ledger(args.path)
        finally:
            await db.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    main()
