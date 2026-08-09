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
    cache_backend: Literal["memory", "redis"] = "memory"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    module_roots: tuple[Path, ...] = Field(
        default_factory=lambda: (Path(__file__).parents[1] / "modules",)
    )
    request_rate_limit: int = Field(default=120, ge=1)
    command_rate_limit: int = Field(default=30, ge=1)
    chat_message_max_length: int = Field(default=20_000, ge=1, le=100_000)
    chat_context_message_limit: int = Field(default=20, ge=1, le=200)
    chat_event_retention_seconds: int = Field(default=86_400, ge=60)
    anonymous_cookie_name: str = "tradesentinel_client_id"
    cookie_secure: bool = False
    market_data_providers: tuple[str, ...] = ()
    news_providers: tuple[str, ...] = ()
    sentiment_providers: tuple[str, ...] = ()
    economic_data_providers: tuple[str, ...] = ()
    fundamentals_providers: tuple[str, ...] = ()
    stock_quote_cache_ttl_seconds: int = Field(default=15, ge=1, le=3_600)
    stock_history_cache_ttl_seconds: int = Field(default=21_600, ge=1, le=604_800)
    stock_actions_cache_ttl_seconds: int = Field(default=86_400, ge=1, le=2_592_000)
    research_document_fetch_limit: int = Field(default=10, ge=0, le=100)
    research_evidence_excerpt_length: int = Field(default=280, ge=40, le=2_000)
    research_extraction_version: str = Field(default="rules-v1", min_length=1, max_length=64)
    research_default_search_limit: int = Field(default=20, ge=1, le=100)
    sentiment_lexicon_version: str = Field(default="lexicon-v1", min_length=1, max_length=64)
    sentiment_excerpt_length: int = Field(default=280, ge=40, le=2_000)
    sentiment_minimum_mentions: int = Field(default=3, ge=1, le=1_000)
    sentiment_spam_minimum_tokens: int = Field(default=3, ge=1, le=20)
    sentiment_spam_max_urls: int = Field(default=3, ge=0, le=20)
    sentiment_spam_max_tags: int = Field(default=8, ge=0, le=100)
    sentiment_spam_repeated_ratio: float = Field(default=0.60, ge=0, le=1)
    sentiment_spam_author_burst: int = Field(default=5, ge=1, le=100)
    sentiment_narrative_limit: int = Field(default=10, ge=1, le=50)
    sentiment_provider_weights: dict[str, float] = Field(default_factory=dict)
    sentiment_source_type_weights: dict[str, float] = Field(default_factory=dict)
    sentiment_trend_stability_threshold: float = Field(default=0.02, ge=0, le=1)

    @model_validator(mode="after")
    def validate_sentiment_weights(self) -> Settings:
        for group in (self.sentiment_provider_weights, self.sentiment_source_type_weights):
            if any(weight < 0 or weight > 10 for weight in group.values()):
                raise ValueError("sentiment weights must be between 0 and 10")
        return self

    @model_validator(mode="after")
    def production_requires_external_infrastructure(self) -> Settings:
        if self.environment == "production":
            if (
                self.persistence_backend != "postgres"
                or self.event_backend != "redis"
                or self.cache_backend != "redis"
            ):
                raise ValueError(
                    "production requires PostgreSQL persistence, Redis events, and Redis cache"
                )
            if "localhost" in self.database_url.get_secret_value():
                raise ValueError("production database URL must not use localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
