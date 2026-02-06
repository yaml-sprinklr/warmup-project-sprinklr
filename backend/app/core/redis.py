import json
import logging
import time
from typing import Any

from redis.exceptions import RedisError, ConnectionError, TimeoutError
import redis.asyncio as redis
from app.core.config import settings
from app.core.metrics import (
    redis_commands_total,
    redis_command_duration_seconds,
    cache_hits_total,
    cache_misses_total,
    redis_errors_total,
)

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper with proper error handling"""

    def __init__(self):
        self.client: redis.Redis | None = None

    async def connect(self):
        """
        Connect to Redis

        Raises:
            ConnectionError: If unable to connect to Redis
        """
        try:
            self.client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            await self.client.ping()
            logger.info(
                f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.aclose()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> str | None:
        """
        Get value from Redis

        Args:
            key: Redis key

        Returns:
            Value if key exists, None if key doesn't exist

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        start_time = time.time()
        try:
            result = await self.client.get(key)
            duration = time.time() - start_time
            
            # Track command execution
            redis_commands_total.labels(command="get").inc()
            redis_command_duration_seconds.labels(command="get").observe(duration)
            
            # Track cache hits/misses
            if result is not None:
                cache_hits_total.inc()
            else:
                cache_misses_total.inc()
            
            return result
        except (ConnectionError, TimeoutError) as e:
            redis_errors_total.labels(error_type="connection").inc()
            logger.error(f"Redis connection/timeout error for GET {key}: {e}")
            raise
        except RedisError as e:
            redis_errors_total.labels(error_type="other").inc()
            logger.error(f"Redis error for GET {key}: {e}")
            raise

    async def ping(self) -> bool:
        """
        Check if Redis is alive

        Returns:
            True if Redis is responsive, False otherwise
        """
        if not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except RedisError:
            return False

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """
        Set value in Redis with optional TTL

        Args:
            key: Redis key
            value: Value to store
            ttl: Time-to-live in seconds (optional)

        Returns:
            True if successful

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        start_time = time.time()
        command = "setex" if ttl else "set"
        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
            
            duration = time.time() - start_time
            redis_commands_total.labels(command=command).inc()
            redis_command_duration_seconds.labels(command=command).observe(duration)
            
            return True
        except (ConnectionError, TimeoutError) as e:
            redis_errors_total.labels(error_type="connection").inc()
            logger.error(f"Redis connection/timeout error for SET {key}: {e}")
            raise
        except RedisError as e:
            redis_errors_total.labels(error_type="other").inc()
            logger.error(f"Redis error for SET {key}: {e}")
            raise

    async def delete(self, key: str) -> int:
        """
        Delete key from Redis

        Args:
            key: Redis key

        Returns:
            Number of keys deleted (0 or 1)

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        start_time = time.time()
        try:
            result = await self.client.delete(key)
            duration = time.time() - start_time
            
            redis_commands_total.labels(command="delete").inc()
            redis_command_duration_seconds.labels(command="delete").observe(duration)
            
            return result
        except (ConnectionError, TimeoutError) as e:
            redis_errors_total.labels(error_type="connection").inc()
            logger.error(f"Redis connection/timeout error for DELETE {key}: {e}")
            raise
        except RedisError as e:
            redis_errors_total.labels(error_type="other").inc()
            logger.error(f"Redis error for DELETE {key}: {e}")
            raise

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis

        Args:
            key: Redis key

        Returns:
            True if key exists

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        start_time = time.time()
        try:
            result = bool(await self.client.exists(key))
            duration = time.time() - start_time
            
            redis_commands_total.labels(command="exists").inc()
            redis_command_duration_seconds.labels(command="exists").observe(duration)
            
            return result
        except (ConnectionError, TimeoutError) as e:
            redis_errors_total.labels(error_type="connection").inc()
            logger.error(f"Redis connection/timeout error for EXISTS {key}: {e}")
            raise
        except RedisError as e:
            redis_errors_total.labels(error_type="other").inc()
            logger.error(f"Redis error for EXISTS {key}: {e}")
            raise

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """
        Get and deserialize JSON value

        Args:
            key: Redis key

        Returns:
            Deserialized dict if key exists, None otherwise

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
            json.JSONDecodeError: If value is not valid JSON
        """
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for key {key}: {e}")
                raise ValueError(f"Invalid JSON in Redis key {key}") from e
        return None

    async def set_json(
        self, key: str, value: dict[str, Any], ttl: int | None = None
    ) -> bool:
        """
        Serialize and set JSON value

        Args:
            key: Redis key
            value: Dict to serialize and store
            ttl: Time-to-live in seconds (optional)

        Returns:
            True if successful

        Raises:
            RuntimeError: If Redis client not connected
            RedisError: On Redis operation failures
            TypeError: If value is not JSON-serializable
        """
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for key {key}: {e}")
            raise TypeError(f"Value not JSON-serializable for key {key}") from e


# Global Redis client instance
redis_client = RedisClient()
