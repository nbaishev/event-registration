from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    app_origin: str = "http://localhost:8080"
    environment: Literal["development", "test", "production"] = "development"
    jwt_secret: SecretStr
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    postgres_user: str = "event_registration"
    postgres_password: str = "development"
    postgres_db: str = "event_registration"

    @field_validator("app_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        canonical = TypeAdapter(AnyHttpUrl).validate_python(value)
        parsed = urlsplit(value)
        if (
            parsed.path
            or "\\" in value
            or canonical.path not in (None, "/")
            or canonical.query is not None
            or canonical.fragment is not None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("APP_ORIGIN must contain only scheme, host and port")
        return str(canonical).removesuffix("/")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET requires at least 32 bytes")
        return value

    def validate_startup(self) -> None:
        if self.environment == "production" and not self.app_origin.startswith(
            "https://"
        ):
            raise ValueError("Production APP_ORIGIN requires HTTPS")

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None:
            return make_url(self.database_url)
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.db_host,
            port=self.db_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
