from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    cache_dir: Path = Field(default=Path(".cache/geo_expression"))
    cache_max_entries: int = Field(default=256, ge=1)
    cache_max_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    http_timeout_s: float = Field(default=120.0, gt=0)
    http_retry_count: int = Field(default=3, ge=0)
    http_retry_backoff_s: float = Field(default=1.0, gt=0)
    concurrency_limit: int = Field(default=4, ge=1)
    stub_llm: bool = Field(default=False)
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "GEO_OPENAI_API_KEY"),
    )
    openai_model: str = Field(default="gpt-4o-mini")

    def should_use_stub_llm(self) -> bool:
        return self.stub_llm or not self.openai_api_key


def get_settings() -> Settings:
    return Settings()
