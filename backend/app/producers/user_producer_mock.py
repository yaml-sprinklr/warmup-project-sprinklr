"""
Mock User Service Producer
Simulates a real user service by producing user lifecycle events to Kafka
For testing order service consumer, metrics, logging, and tracing
"""

import asyncio
import random
import signal
import sys
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

import structlog

from app.core.config import settings
from app.core.kafka import kafka_producer
from app.core.logging import configure_logging
from app.core.tracing import create_trace_context, set_trace_context
from app.events import UserCreatedData, UserUpdatedData, UserDeletedData

# Configure structured logging
configure_logging()
logger = structlog.get_logger(__name__)

# User database simulation
active_users: dict[str, dict[str, Any]] = {}

# Shutdown flag
shutdown_flag = False


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    logger.info("shutdown_signal_received", signal=sig)
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
    """Simulate user creation with distributed tracing"""
    if len(active_users) >= settings.MOCK_USER_MAX_USERS:
        logger.debug(
            "max_users_reached",
            max_users=settings.MOCK_USER_MAX_USERS,
            current_users=len(active_users),
        )
        return

    user_data = generate_user_data()
    user_id = user_data["user_id"]

    # Create trace context for this user creation event
    trace_context = create_trace_context()
    set_trace_context(trace_context)

    # Bind trace context to logs
    structlog.contextvars.bind_contextvars(
        **{"trace.id": trace_context.trace_id},
        **{"span.id": trace_context.span_id},
    )

    active_users[user_id] = user_data

    try:
        # Create typed event data
        event_data = UserCreatedData(**user_data)

        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_CREATED,
            event_type="user.created",
            data=event_data.model_dump(mode="json"),
            key=user_id,
            trace_context=trace_context,
        )
        logger.info(
            "user_created_event_published",
            user_id=user_id,
            email=user_data["email"],
        )
    except Exception as e:
        logger.error(
            "user_create_failed",
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        # Remove from local cache if publish failed
        active_users.pop(user_id, None)
    finally:
        structlog.contextvars.clear_contextvars()


async def update_user_event():
    """Simulate user update with distributed tracing"""
    if not active_users:
        logger.debug("no_active_users_to_update")
        return

    user_id = random.choice(list(active_users.keys()))
    user = active_users[user_id]

    # Create trace context for this user update event
    trace_context = create_trace_context()
    set_trace_context(trace_context)

    # Bind trace context to logs
    structlog.contextvars.bind_contextvars(
        **{"trace.id": trace_context.trace_id},
        **{"span.id": trace_context.span_id},
    )

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

    updated_at = datetime.now(UTC)
    user["updated_at"] = updated_at.isoformat()

    try:
        # Create typed event data
        event_data = UserUpdatedData(
            user_id=user_id,
            email=user["email"],
            name=user.get("name"),
            status=user["status"],
            updated_at=updated_at,
        )

        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_UPDATED,
            event_type="user.updated",
            data=event_data.model_dump(mode="json"),
            key=user_id,
            trace_context=trace_context,
        )
        logger.info(
            "user_updated_event_published",
            user_id=user_id,
            email=user["email"],
            updates=updates,
        )
    except Exception as e:
        logger.error(
            "user_update_failed",
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )
    finally:
        structlog.contextvars.clear_contextvars()


async def delete_user_event():
    """Simulate user deletion with distributed tracing"""
    if not active_users:
        logger.debug("no_active_users_to_delete")
        return

    user_id = random.choice(list(active_users.keys()))
    user = active_users.pop(user_id)

    # Create trace context for this user deletion event
    trace_context = create_trace_context()
    set_trace_context(trace_context)

    # Bind trace context to logs
    structlog.contextvars.bind_contextvars(
        **{"trace.id": trace_context.trace_id},
        **{"span.id": trace_context.span_id},
    )

    try:
        # Create typed event data
        event_data = UserDeletedData(
            user_id=user_id, deleted_at=datetime.now(UTC), reason="simulated_deletion"
        )

        await kafka_producer.publish_event(
            topic=settings.KAFKA_TOPIC_USER_DELETED,
            event_type="user.deleted",
            data=event_data.model_dump(mode="json"),
            key=user_id,
            trace_context=trace_context,
        )
        logger.info(
            "user_deleted_event_published",
            user_id=user_id,
            email=user["email"],
        )
    except Exception as e:
        logger.error(
            "user_delete_failed",
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        # Add back to cache if publish failed
        active_users[user_id] = user
    finally:
        structlog.contextvars.clear_contextvars()


async def create_user_loop():
    """Background task: continuously create users"""
    while not shutdown_flag:
        try:
            await create_user_event()
            await asyncio.sleep(settings.MOCK_USER_CREATE_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(
                "create_loop_error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
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
            logger.error(
                "update_loop_error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
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
            logger.error(
                "delete_loop_error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            await asyncio.sleep(5)


async def main():
    """Entry point for mock user producer"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(
        "mock_user_producer_starting",
        create_interval=settings.MOCK_USER_CREATE_INTERVAL,
        update_interval=settings.MOCK_USER_UPDATE_INTERVAL,
        delete_interval=settings.MOCK_USER_DELETE_INTERVAL,
        max_users=settings.MOCK_USER_MAX_USERS,
    )

    try:
        await kafka_producer.start()
        logger.info("kafka_producer_connected")

        # Start background tasks
        create_task = asyncio.create_task(create_user_loop(), name="create-users")
        update_task = asyncio.create_task(update_user_loop(), name="update-users")
        delete_task = asyncio.create_task(delete_user_loop(), name="delete-users")

        # Wait for shutdown signal
        while not shutdown_flag:
            await asyncio.sleep(1)

        # Cancel tasks
        logger.info("cancelling_background_tasks")
        create_task.cancel()
        update_task.cancel()
        delete_task.cancel()

        await asyncio.gather(
            create_task, update_task, delete_task, return_exceptions=True
        )

    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error(
            "mock_producer_fatal_error",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        sys.exit(1)
    finally:
        await kafka_producer.stop()
        logger.info(
            "mock_user_producer_shutdown",
            total_active_users=len(active_users),
        )


if __name__ == "__main__":
    asyncio.run(main())
