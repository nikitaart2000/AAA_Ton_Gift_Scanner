"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ton_gifts"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ton_gifts"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Swift Gifts API
    SWIFT_GIFTS_API_KEY: str
    SWIFT_GIFTS_BASE_URL: str = "https://api-swiftgifts.vercel.app"

    # Tonnel API
    TONNEL_BASE_URL: str = "https://gifts2.tonnel.network"
    TONNEL_AUTH_DATA: str

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WHITELIST: str = ""

    @property
    def whitelist_ids(self) -> List[int]:
        """Parse whitelist as list of integers."""
        if not self.TELEGRAM_WHITELIST:
            return []
        return [int(uid.strip()) for uid in self.TELEGRAM_WHITELIST.split(",") if uid.strip()]

    # App Settings
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Scanner settings
    SWIFT_RECONNECT_DELAY: int = 5
    TONNEL_SYNC_INTERVAL: int = 60
    ANALYTICS_CACHE_TTL: int = 60
    FLOOR_CACHE_TTL: int = 30

    # Alert settings
    COOLDOWN_SECONDS: int = 120
    MAX_ALERTS_PER_HOUR: int = 50
    BATCH_WINDOW_SECONDS: int = 30


settings = Settings()
