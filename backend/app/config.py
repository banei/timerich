from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://dca_app:password@mysql:3306/dca_dashboard?charset=utf8mb4"
    log_level: str = "INFO"
    sql_echo: bool = False

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:8050"

    tz: str = "Asia/Shanghai"

    scheduler_enabled: bool = True
    scheduler_run_on_start: bool = False

    data_fetch_timeout: int = 30
    data_fetch_retry: int = 3
    cache_ttl_realtime: int = 15
    cache_ttl_daily: int = 240

    backfill_years: int = 10
    daily_refresh_hour: int = 22
    daily_refresh_minute: int = 30

    notify_webhook_url: str = ""
    notify_webhook_feishu: str = ""

    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    backup_dir: str = "/app/backups"
    backup_retain_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
