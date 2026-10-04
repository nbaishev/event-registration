from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    environment: Literal["development", "test", "production"] = "development"
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    postgres_user: str = "event_registration"
    postgres_password: str = "development"
    postgres_db: str = "event_registration"

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
