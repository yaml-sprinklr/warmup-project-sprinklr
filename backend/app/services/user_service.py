"""
User Service - User validation and data fetching

Implements cache-aside pattern:
1. Check Redis cache first (fast path)
2. On cache miss, fetch from User Service API
3. Update cache with fetched data
"""

from typing import Any

from app.core.redis import RedisClient
from app.core.logging import get_logger
from app.clients.user_client import user_client
from app.models import UserData
from app.core.config import settings
from app.core.metrics.metrics import (
    user_validation_total,
    user_validation_duration_seconds,
    user_service_api_calls_total,
)
import time

logger = get_logger(__name__)


class UserService:
    """User validation and data management service"""

    @staticmethod
    async def validate_user(user_id: str, redis: RedisClient) -> UserData | None:
        """
        Validate that a user exists and is active

        Implements cache-aside pattern:
        1. Check Redis cache (populated by user.created/updated events)
        2. On miss, call User Service API (mocked)
        3. Cache the result for future requests

        Args:
            user_id: The user ID to validate
            redis: Redis client instance

        Returns:
            UserData if user exists and is active, None otherwise
        """
        start_time = time.time()
        logger.debug("user_validation_started", user_id=user_id)

        try:
            # Step 1: Check cache first (fast path)
            cache_key = f"user:{user_id}"
            cached_data = await redis.get_json(cache_key)

            if cached_data:
                # Cache hit!
                user_data = UserData(**cached_data)
                duration = time.time() - start_time

                user_validation_total.labels(result="cache_hit").inc()
                user_validation_duration_seconds.observe(duration)

                logger.info(
                    "user_validation_cache_hit",
                    user_id=user_id,
                    status=user_data.status,
                    duration_ms=round(duration * 1000, 2),
                )

                # Check if user is active
                if user_data.status != "active":
                    user_validation_total.labels(result="inactive").inc()
                    logger.warning(
                        "user_validation_failed",
                        user_id=user_id,
                        reason="user_inactive",
                        status=user_data.status,
                    )
                    return None

                logger.info(
                    "user_validation_succeeded",
                    user_id=user_id,
                    source="cache",
                    duration_ms=round(duration * 1000, 2),
                )
                return user_data

            # Step 2: Cache miss - fetch from User Service API
            logger.info("user_validation_cache_miss", user_id=user_id)
            user_validation_total.labels(result="cache_miss").inc()

            api_data = await UserService._fetch_from_user_service(user_id)

            if not api_data:
                # User not found in API
                duration = time.time() - start_time
                user_validation_total.labels(result="not_found").inc()
                user_validation_duration_seconds.observe(duration)

                logger.warning(
                    "user_validation_failed",
                    user_id=user_id,
                    reason="user_not_found",
                    duration_ms=round(duration * 1000, 2),
                )
                return None

            # Step 3: Parse and validate user data
            user_data = UserData(**api_data)

            # Check if user is active
            if user_data.status != "active":
                duration = time.time() - start_time
                user_validation_total.labels(result="inactive").inc()
                user_validation_duration_seconds.observe(duration)

                logger.warning(
                    "user_validation_failed",
                    user_id=user_id,
                    reason="user_inactive",
                    status=user_data.status,
                    duration_ms=round(duration * 1000, 2),
                )
                return None

            # Step 4: Update cache for future requests
            try:
                await redis.set_json(
                    cache_key,
                    user_data.model_dump(mode="json"),
                    ttl=settings.USER_CACHE_TTL,
                )
                logger.debug("user_cached_from_api", user_id=user_id)
            except Exception as cache_error:
                # Non-critical: Cache update failed, but we have the data
                logger.warning(
                    "user_cache_update_failed",
                    user_id=user_id,
                    error_type=type(cache_error).__name__,
                    error_message=str(cache_error),
                )

            duration = time.time() - start_time
            user_validation_duration_seconds.observe(duration)

            logger.info(
                "user_validation_succeeded",
                user_id=user_id,
                source="api",
                email=user_data.email,
                duration_ms=round(duration * 1000, 2),
            )

            return user_data

        except Exception as e:
            duration = time.time() - start_time
            user_validation_total.labels(result="error").inc()
            user_validation_duration_seconds.observe(duration)

            logger.error(
                "user_validation_error",
                user_id=user_id,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=round(duration * 1000, 2),
                exc_info=True,
            )
            return None

    @staticmethod
    async def _fetch_from_user_service(user_id: str) -> dict[str, Any] | None:
        """
        Fetch user data from User Service API (mocked)

        Args:
            user_id: The user ID to fetch

        Returns:
            User data dict or None if not found
        """
        logger.info("user_service_api_called", user_id=user_id)

        try:
            user_data = await user_client.get_user(user_id)

            if user_data:
                user_service_api_calls_total.labels(status="success").inc()
            else:
                user_service_api_calls_total.labels(status="not_found").inc()

            return user_data

        except Exception as e:
            user_service_api_calls_total.labels(status="failure").inc()
            logger.error(
                "user_service_api_error",
                user_id=user_id,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            return None
