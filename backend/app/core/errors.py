"""Veritabanı kısıt ihlallerini anlamlı HTTP yanıtlarına çevirir.

İş kurallarının çoğu (çakışma, tekillik, tutar kontrolleri) PostgreSQL'de
zorlanır; API katmanı yalnızca hatayı kullanıcıya tercüme eder.
"""
import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_FRIENDLY = {
    "training_sessions_no_facility_overlap": "Bu saha bu saat aralığında dolu.",
    "training_sessions_no_coach_overlap": "Koçun bu saat aralığında başka bir seansı var.",
    "team_memberships_one_active": "Sporcunun zaten aktif bir takımı var.",
    "invoices_subscription_id_period_key": "Bu dönem için fatura zaten kesilmiş.",
    "guardians_phone_key": "Bu telefon numarası başka bir veliye kayıtlı.",
}


def _msg(exc: asyncpg.PostgresError, default: str) -> str:
    return _FRIENDLY.get(getattr(exc, "constraint_name", None) or "", default)


def install(app: FastAPI) -> None:
    @app.exception_handler(asyncpg.ExclusionViolationError)
    async def _excl(_: Request, exc: asyncpg.ExclusionViolationError):
        return JSONResponse({"detail": _msg(exc, "Zaman çakışması"), "constraint": exc.constraint_name},
                            status_code=409)

    @app.exception_handler(asyncpg.UniqueViolationError)
    async def _uniq(_: Request, exc: asyncpg.UniqueViolationError):
        return JSONResponse({"detail": _msg(exc, "Kayıt zaten mevcut"), "constraint": exc.constraint_name},
                            status_code=409)

    @app.exception_handler(asyncpg.CheckViolationError)
    async def _check(_: Request, exc: asyncpg.CheckViolationError):
        return JSONResponse({"detail": "Geçersiz değer", "constraint": exc.constraint_name}, status_code=422)

    @app.exception_handler(asyncpg.ForeignKeyViolationError)
    async def _fk(_: Request, exc: asyncpg.ForeignKeyViolationError):
        return JSONResponse({"detail": "İlişkili kayıt bulunamadı", "constraint": exc.constraint_name},
                            status_code=422)
