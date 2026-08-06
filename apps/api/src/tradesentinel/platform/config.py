from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADESENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://tradesentinel:tradesentinel@localhost:5432/tradesentinel"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    persistence_backend: Literal["memory", "postgres"] = "memory"
    event_backend: Literal["memory", "redis"] = "memory"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    module_roots: tuple[Path, ...] = Field(
        default_factory=lambda: (Path(__file__).parents[1] / "modules",)
    )
    request_rate_limit: int = Field(default=120, ge=1)
    command_rate_limit: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def production_requires_external_infrastructure(self) -> Settings:
        if self.environment == "production":
            if self.persistence_backend != "postgres" or self.event_backend != "redis":
                raise ValueError("production requires PostgreSQL persistence and Redis events")
            if "localhost" in self.database_url.get_secret_value():
                raise ValueError("production database URL must not use localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
