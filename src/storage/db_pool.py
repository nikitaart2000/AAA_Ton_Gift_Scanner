"""Database connection pool for API."""

import logging
import asyncpg
from src.config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """Simple asyncpg connection pool."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Create connection pool."""
        if self.pool:
            return

        # Parse DATABASE_URL to asyncpg format
        # postgresql+asyncpg://user:pass@host:port/db -> postgresql://user:pass@host:port/db
        db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

        logger.info("Creating database connection pool")
        self.pool = await asyncpg.create_pool(
            db_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()


# Global pool instance
_db_pool = DatabasePool()


async def get_db_pool() -> DatabasePool:
    """Get database pool dependency."""
    if not _db_pool.pool:
        await _db_pool.connect()
    return _db_pool
