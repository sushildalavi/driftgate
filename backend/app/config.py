from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://driftgate:dev@localhost:5432/driftgate"
    )
    database_url_sync: str = Field(
        default="postgresql://driftgate:dev@localhost:5432/driftgate"
    )

    admin_secret: str = Field(default="dev-secret")

    anthropic_api_key: str | None = None
    llm_model: str = "claude-haiku-4-5-20251001"

    frontend_origins: str = "http://localhost:5173"
    registry_path: str = "/app/config/apis.yaml"

    fetch_timeout_sec: int = 10
    raw_body_max_bytes: int = 262144
    raw_retention_per_endpoint: int = 10

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
