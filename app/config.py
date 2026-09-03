from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Etiquetado colaborativo", validation_alias="APP_TITLE")
    app_env: str = "development"
    secret_key: str = "local-only-change-me"
    database_url: str = "sqlite:///./data/app.db"
    session_cookie_name: str = "labeling_session"
    session_cookie_secure: bool = False
    admin_username: str = "admin"
    admin_password: str = "admin123"
    seed_demo_data: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _reject_development_secret_in_production(self) -> "Settings":
        if self.app_env.lower() == "production" and self.secret_key == "local-only-change-me":
            raise ValueError("secret_key must be changed before using production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
