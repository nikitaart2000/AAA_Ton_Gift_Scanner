"""Redis cache client."""

import json
import logging
from typing import Any, Optional
from redis.asyncio import Redis, ConnectionPool
from src.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis cache client."""

    def __init__(self):
        self.redis: Redis | None = None
        self.pool: ConnectionPool | None = None

    async def connect(self):
        """Connect to Redis."""
        logger.info(f"Connecting to Redis: {settings.REDIS_URL}")

        self.pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )

        self.redis = Redis(connection_pool=self.pool)

        # Test connection
        await self.redis.ping()
        logger.info("Redis connected successfully")

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
        if self.pool:
            await self.pool.disconnect()
        logger.info("Redis disconnected")

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.get(key)

    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value by key."""
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        if ttl:
            return await self.redis.setex(key, ttl, value)
        return await self.redis.set(key, value)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set JSON value with optional TTL."""
        return await self.set(key, json.dumps(value, default=str), ttl)

    async def delete(self, key: str) -> int:
        """Delete key."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.exists(key) > 0

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.incrby(key, amount)

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on key."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        """Get TTL of key."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.ttl(key)

    async def keys(self, pattern: str) -> list[str]:
        """Get keys matching pattern."""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.keys(pattern)


# Global Redis client
redis_client = RedisClient()
