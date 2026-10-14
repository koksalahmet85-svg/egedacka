from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Ege Alfa Kulüp Yönetimi"
    env: str = "development"
    database_url: str
    cors_origins: list[str] = ["http://localhost:3000"]

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 12

    # Hassas alanlar (TCKN, IBAN) için AES-GCM anahtarı, base64 32 bayt.
    field_encryption_key: str = ""

    # Entegrasyonlar
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_ad_account_id: str = ""  # "act_123..." olmadan sadece rakamlar
    whatsapp_phone_number_id: str = ""
    calcom_webhook_secret: str = ""
    iyzico_api_key: str = ""
    iyzico_secret_key: str = ""
    invoice_provider: str = "mock"  # "parasut" | "mock"
    parasut_company_id: str = ""
    parasut_client_id: str = ""
    parasut_client_secret: str = ""
    parasut_username: str = ""
    parasut_password: str = ""

    # İş kuralları
    default_expected_tenure_months: float = 14.0
    dashboard_cache_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
