"""
Mock User Service API Client

Simulates external user service API calls.
In production, this would be replaced with real HTTP client using httpx.
"""

import asyncio
import random
from datetime import datetime, UTC
from typing import Any

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class UserClient:
    """Mock client for User Service API"""

    def __init__(self):
        self.base_url = settings.USER_SERVICE_URL

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        """
        Fetch user data from User Service API (mocked)

        In production, this would make actual HTTP call:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/users/{user_id}")
            if response.status_code == 200:
                return response.json()
            return None

        Args:
            user_id: The user ID to fetch

        Returns:
            User data dict or None if user not found
        """
        logger.debug("user_service_api_call", user_id=user_id, url=self.base_url)

        # Simulate network latency (50-200ms)
        await asyncio.sleep(random.uniform(0.05, 0.2))

        # Mock logic: Generate realistic user data based on user_id pattern
        # Pattern: user_* = valid, anything else = invalid
        if not user_id.startswith("user_"):
            logger.info(
                "user_service_api_not_found",
                user_id=user_id,
                reason="invalid_user_id_format",
            )
            return None

        # Some users are inactive (30% chance based on ID)
        # Use hash for deterministic inactive status
        status = "active" if hash(user_id) % 10 < 7 else "inactive"

        # Generate mock user data
        first_names = [
            "Alice",
            "Bob",
            "Charlie",
            "Diana",
            "Eve",
            "Frank",
            "Grace",
            "Henry",
        ]
        last_names = [
            "Smith",
            "Johnson",
            "Williams",
            "Brown",
            "Jones",
            "Garcia",
            "Miller",
        ]

        # Use deterministic selection based on user_id
        first_name = first_names[hash(user_id) % len(first_names)]
        last_name = last_names[hash(user_id + "last") % len(last_names)]

        user_data = {
            "user_id": user_id,
            "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
            "name": f"{first_name} {last_name}",
            "status": status,
            "created_at": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "user_service_api_success",
            user_id=user_id,
            status=status,
            email=user_data["email"],
        )

        return user_data


# Global instance
user_client = UserClient()
