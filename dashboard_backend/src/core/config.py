from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Uses Pydantic Settings with .env support (python-dotenv is already included).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Dashboard Backend", description="Application name")
    app_env: str = Field(default="development", description="Environment name (development/staging/production)")
    log_level: str = Field(default="INFO", description="Log level")

    cors_allow_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins, or '*' for all (development only).",
    )

    jwt_secret: str = Field(..., description="JWT signing secret (HS256) - must be set")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(default=60, description="Access token expiry in minutes")

    postgres_url: str = Field(
        ...,
        description="SQLAlchemy database URL (async preferred), e.g. postgresql+asyncpg://user:pass@host:port/db",
        validation_alias="POSTGRES_URL",
    )

    tenancy_mode: str = Field(
        default="header",
        description="Tenancy mode: 'header' uses X-Organization-Id/X-Workspace-Id headers; 'token' uses JWT claims.",
    )

    @field_validator("tenancy_mode")
    @classmethod
    def _validate_tenancy_mode(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"header", "token"}:
            raise ValueError("TENANCY_MODE must be one of: header, token")
        return v

    # PUBLIC_INTERFACE
    def cors_origins_list(self) -> List[str]:
        """Return parsed CORS origins list."""
        raw = (self.cors_allow_origins or "").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Get cached Settings instance."""
    return Settings()
