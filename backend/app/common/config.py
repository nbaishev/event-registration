from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_origin: str = "http://localhost:8080"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    postgres_user: str = "event_registration"
    postgres_password: str = "development"
    postgres_db: str = "event_registration"

    @field_validator("app_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        TypeAdapter(AnyHttpUrl).validate_python(value)
        parsed = urlsplit(value)
        if (
            parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("APP_ORIGIN must contain only scheme, host and port")
        return value

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
