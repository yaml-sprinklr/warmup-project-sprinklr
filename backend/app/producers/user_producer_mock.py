"""
Mock User Service Producer
Simulates a real user service by producing user lifecycle events to Kafka
For testing order service consumer, metrics, logging, and tracing
"""

import asyncio
import logging
import random
import signal
import sys
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from app.core.config import settings
from app.core.kafka import kafka_producer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# User database simulation
active_users: dict[str, dict[str, Any]] = {}

# Shutdown flag
shutdown_flag = False


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_flag = True


def generate_user_data() -> dict[str, Any]:
    """Generate realistic user data"""
    first_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    
    first_name = random.choice(first_names)
    last_name = random.choice(last_names)
    
    return {
        "user_id": f"user_{uuid4().hex[:8]}",
        "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
        "name": f"{first_name} {last_name}",
        "status": "active",
        "created_at": datetime.now(UTC).isoformat(),
    }


async def create_user_event():
    """Simulate user creation"""
    if len(active_users) >= settings.MOCK_USER_MAX_USERS:
        logger.debug(f"Max users ({settings.MOCK_USER_MAX_USERS}) reached, skipping creation")
        return

    user_data = generate_user_data()
    user_id = user_data["user_id"]
    
    active_users[user_id] = user_data
    
    try:
        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_CREATED,
            event_type="user.created",
            data=user_data,
            key=user_id,
        )
        logger.info(f"✓ Created user {user_id} ({user_data['email']})")
    except Exception as e:
        logger.error(f"Failed to publish user.created event: {e}")
        # Remove from local cache if publish failed
        active_users.pop(user_id, None)


async def update_user_event():
    """Simulate user update"""
    if not active_users:
        logger.debug("No active users to update")
        return

    user_id = random.choice(list(active_users.keys()))
    user = active_users[user_id]
    
    # Simulate updates: change name or status
    updates = {}
    if random.random() < 0.7:
        # 70% chance: update name
        user["name"] = f"{user['name']} (Updated)"
        updates["name"] = user["name"]
    else:
        # 30% chance: change status
        new_status = random.choice(["active", "inactive", "suspended"])
        user["status"] = new_status
        updates["status"] = new_status
    
    user["updated_at"] = datetime.now(UTC).isoformat()
    
    try:
        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_UPDATED,
            event_type="user.updated",
            data={
                "user_id": user_id,
                "email": user["email"],
                "name": user.get("name"),
                "status": user["status"],
                "updated_at": user["updated_at"],
            },
            key=user_id,
        )
        logger.info(f"✓ Updated user {user_id} ({user['email']}) - changes: {updates}")
    except Exception as e:
        logger.error(f"Failed to publish user.updated event: {e}")


async def delete_user_event():
    """Simulate user deletion"""
    if not active_users:
        logger.debug("No active users to delete")
        return

    user_id = random.choice(list(active_users.keys()))
    user = active_users.pop(user_id)
    
    try:
        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_DELETED,
            event_type="user.deleted",
            data={
                "user_id": user_id,
                "email": user["email"],
                "deleted_at": datetime.now(UTC).isoformat(),
            },
            key=user_id,
        )
        logger.info(f"✓ Deleted user {user_id} ({user['email']})")
    except Exception as e:
        logger.error(f"Failed to publish user.deleted event: {e}")
        # Add back to cache if publish failed
        active_users[user_id] = user


async def create_user_loop():
    """Background task: continuously create users"""
    while not shutdown_flag:
        try:
            await create_user_event()
            await asyncio.sleep(settings.MOCK_USER_CREATE_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in create loop: {e}", exc_info=True)
            await asyncio.sleep(5)


async def update_user_loop():
    """Background task: continuously update users"""
    # Wait a bit before starting updates
    await asyncio.sleep(settings.MOCK_USER_CREATE_INTERVAL * 2)
    
    while not shutdown_flag:
        try:
            await update_user_event()
            await asyncio.sleep(settings.MOCK_USER_UPDATE_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in update loop: {e}", exc_info=True)
            await asyncio.sleep(5)


async def delete_user_loop():
    """Background task: continuously delete users"""
    # Wait longer before starting deletions
    await asyncio.sleep(settings.MOCK_USER_CREATE_INTERVAL * 5)
    
    while not shutdown_flag:
        try:
            await delete_user_event()
            await asyncio.sleep(settings.MOCK_USER_DELETE_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in delete loop: {e}", exc_info=True)
            await asyncio.sleep(5)


async def main():
    """Entry point for mock user producer"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Starting Mock User Service Producer...")
    logger.info(f"Configuration:")
    logger.info(f"  - Create user every {settings.MOCK_USER_CREATE_INTERVAL}s")
    logger.info(f"  - Update user every {settings.MOCK_USER_UPDATE_INTERVAL}s")
    logger.info(f"  - Delete user every {settings.MOCK_USER_DELETE_INTERVAL}s")
    logger.info(f"  - Max users: {settings.MOCK_USER_MAX_USERS}")

    try:
        await kafka_producer.start()
        logger.info("Kafka producer connected")

        # Start background tasks
        create_task = asyncio.create_task(create_user_loop(), name="create-users")
        update_task = asyncio.create_task(update_user_loop(), name="update-users")
        delete_task = asyncio.create_task(delete_user_loop(), name="delete-users")

        # Wait for shutdown signal
        while not shutdown_flag:
            await asyncio.sleep(1)

        # Cancel tasks
        logger.info("Cancelling background tasks...")
        create_task.cancel()
        update_task.cancel()
        delete_task.cancel()

        await asyncio.gather(create_task, update_task, delete_task, return_exceptions=True)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error in mock producer: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await kafka_producer.stop()
        logger.info(f"✓ Mock User Service Producer shutdown complete (created {len(active_users)} users)")


if __name__ == "__main__":
    asyncio.run(main())
