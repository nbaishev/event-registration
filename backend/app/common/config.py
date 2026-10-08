from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    EmailStr,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)
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

    redis_url: str = "redis://redis:6379/0"
    smtp_host: str = "mailpit"
    smtp_port: int = Field(default=1025, gt=0, le=65535)
    smtp_from: EmailStr = "tickets@example.com"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    smtp_timeout_seconds: float = Field(default=10, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_smtp(self) -> "Settings":
        if (self.smtp_username is None) != (self.smtp_password is None):
            raise ValueError("SMTP credentials must be configured as a pair")
        if self.smtp_username is not None and self.smtp_password is not None:
            if not self.smtp_username or not self.smtp_password.get_secret_value():
                raise ValueError("SMTP credentials must be nonempty")
            if self.smtp_security == "none":
                raise ValueError("SMTP authentication requires TLS")
        return self

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
