from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Workplace Discipline API")
    environment: str = Field(default="development")
    api_v1_prefix: str = Field(default="/api/v1")
    uploads_dir: Path = Field(default=Path("uploads"))
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    database_url: str = Field(default="sqlite+aiosqlite:///./app.db")

    jwt_secret: str = Field(..., min_length=16)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7, gt=0)

    admin_username: str = Field(..., min_length=1)
    admin_password: str = Field(..., min_length=8)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
