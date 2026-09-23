from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Cricket Intelligence Platform"
    app_version: str = "0.1.0"

    environment: Literal[
        "development",
        "test",
        "staging",
        "production",
    ] = "development"

    debug: bool = False
    log_level: str = "INFO"

    database_url: SecretStr
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_recycle: int = Field(default=1800, ge=30)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        if value.startswith("postgres://"):
            return value.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )

        if value.startswith("postgresql://"):
            return value.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )

        if value.startswith("postgresql+psycopg://"):
            return value

        raise ValueError(
            "DATABASE_URL must use postgres://, "
            "postgresql://, or "
            "postgresql+psycopg://"
        )

    @property
    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]