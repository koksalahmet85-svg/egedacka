"""Prisma istemcisi: süreç başına tek bağlantı havuzu."""

from prisma import Prisma

db = Prisma(auto_register=True)


async def connect() -> None:
    if not db.is_connected():
        await db.connect()


async def disconnect() -> None:
    if db.is_connected():
        await db.disconnect()
