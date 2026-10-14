from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/egealfa"
    db_pool_min: int = 2
    db_pool_max: int = 10

    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_ttl_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    timezone: str = "Europe/Istanbul"
    invoice_due_days: int = 10
    # Kayıtlı sporcunun ortalama kulüpte kalma süresi (ay). Yeterli "LEFT"
    # verisi birikene kadar LTV hesabında bu varsayım kullanılır.
    default_lifetime_months: int = 18

    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_page_token: str = ""
    payment_webhook_secret: str = ""

    dashboard_cache_seconds: int = 60

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
