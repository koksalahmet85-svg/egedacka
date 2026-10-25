"""Yönetim komutları.

python -m app.cli create-user <e-posta> <rol>    # şifre sorulur ya da EGEALFA_PASSWORD'dan okunur
python -m app.cli sync                           # Drive'dan geliri hemen oku
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from .core.db import connect, db, disconnect
from .core.security import hash_password

ROLES = ("ADMIN", "MANAGER", "COACH", "FINANCE", "MARKETING")


async def create_user(email: str, role: str) -> None:
    role = role.upper()
    if role not in ROLES:
        sys.exit(f"Rol şunlardan biri olmalı: {', '.join(ROLES)}")
    password = os.environ.get("EGEALFA_PASSWORD") or getpass.getpass("Şifre (en az 10 karakter): ")
    if len(password) < 10:
        sys.exit("Şifre en az 10 karakter olmalı")
    await connect()
    try:
        user = await db.user.upsert(
            where={"email": email.lower()},
            data={
                "create": {"email": email.lower(), "passwordHash": hash_password(password), "role": role},
                "update": {"passwordHash": hash_password(password), "role": role, "isActive": True},
            },
        )
        print(f"Kullanıcı hazır: {user.email} ({user.role})")
    finally:
        await disconnect()


async def sync() -> None:
    from .services import drive_income
    from .services.google_sheets import SheetsError

    await connect()
    try:
        try:
            r = await drive_income.sync(trigger="manual")
        except SheetsError as e:
            sys.exit(f"Drive okunamadı: {e}")
        if r.get("status") == "skipped":
            print(f"Atlandı: {r.get('reason')}")
            return
        print(f"Okunan sayfalar: {', '.join(r.get('sheets', []))}")
        print(f"Atlanan sayfalar: {', '.join(r.get('skippedSheets', []))}")
        print(f"Satır: {r.get('rows')} · değişiklik: {r.get('changes')}")
    finally:
        await disconnect()


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "create-user":
        asyncio.run(create_user(args[1], args[2]))
    elif args == ["sync"]:
        asyncio.run(sync())
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
