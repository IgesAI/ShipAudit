from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ShipAudit"
    environment: Literal["local", "test", "staging", "production"] = "local"
    secret_key: str = Field(default="dev-secret", min_length=8)
    access_token_minutes: int = 60 * 8

    database_url: str = "sqlite+pysqlite:///./shipaudit.db"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "shipaudit"
    s3_secret_access_key: str = "shipaudit-secret"
    s3_bucket: str = "shipaudit-evidence"
    s3_region: str = "us-east-1"

    address_validator: str = "mock"
    geocoder: str = "mock"
    usps_client_id: str | None = None
    usps_client_secret: str | None = None
    google_address_validation_api_key: str | None = None
    smarty_auth_id: str | None = None
    smarty_auth_token: str | None = None

    fedex_account_number: str | None = None
    fedex_client_id: str | None = None
    fedex_client_secret: str | None = None
    ups_client_id: str | None = None
    ups_client_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
