from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_prefix="VERQAC_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev | staging | prod
    reminders: bool = True  # background deadline reminders (VERQAC_REMINDERS=0 to switch off)
    # The application connects as a non-owner role so that Row-Level Security applies.
    database_url: str = "postgresql+psycopg://verqac_app:verqac_app@localhost:5432/verqac"
    # Migrations run as the owner role (creates tables, policies, grants).
    migration_database_url: str = "postgresql+psycopg://verqac_owner:verqac_owner@localhost:5432/verqac"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    refresh_cookie_name: str = "verqac_refresh"
    cookie_secure: bool = False

    cors_origins: list[str] = ["http://localhost:5173"]
    app_url: str = "http://localhost:5173"

    invitation_days: int = 14

    files_dir: str = "/data/files"
    max_upload_mb: int = 50

    # E-mail is optional: without SMTP the invitation link is shown to the inviter to send by hand.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Verqac <no-reply@verqac.com>"
    smtp_starttls: bool = True

    # Mahami push: the same endpoint the Odoo dr module uses (POST {url}/integrations/odoo/notify)
    mahami_url: str = ""
    mahami_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
