import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.core.redis import redis_client
from app.core.kafka import kafka_consumer, kafka_producer

# from app.core.metrics import events_consumed_total, consume_errors_total
from app.core.db import engine
from sqlmodel import Session, select
from app.models import Order, OrderStatus

logger = logging.getLogger(__name__)


async def start_consumer():
    """
    Main consumer loop - runs as background task
    Consumes user events and handles them
    """
    logger.info("Starting user event consumer...")

    try:
        async for message in kafka_consumer.consume_messages():
            await handle_message(message)

    except asyncio.CancelledError:
        logger.info("Consumer task cancelled, shutting down gracefully")
        raise
    except Exception as e:
        logger.error(f"Consumer crashed: {e}", exc_info=True)
        raise


async def handle_message(message):
    """Process a single Kafka message with idempotency"""
    event = message.value
    event_id = event["event_id"]
    event_type = event["event_type"]

    # Idempotency check
    cache_key = f"processed_event:{event_id}"
    if await redis_client.exists(cache_key):
        logger.debug(f"Duplicate event {event_id}, skipping")
        await kafka_consumer.commit()
        return

    try:
        if event_type == "user.created":
            await handle_user_created(event)
        elif event_type == "user.updated":
            await handle_user_updated(event)
        elif event_type == "user.deleted":
            await handle_user_deleted(event)
        else:
            logger.warning(f"Unknown event type: {event_type}")

        # Mark as processed
        await redis_client.set(cache_key, "1", ttl=settings.PROCESSED_EVENT_TTL)

        # Commit offset
        await kafka_consumer.commit()

        # # Metrics
        # events_consumed_total.labels(
        #     topic=message.topic,
        #     event_type=event_type
        # ).inc()

    except Exception as e:
        logger.error(f"Failed to process event {event_id}: {e}", exc_info=True)
        # consume_errors_total.labels(
        #     topic=message.topic,
        #     error_type=type(e).__name__
        # ).inc()
        # Don't commit - will retry


async def handle_user_created(event):
    """Cache new user data"""
    user_data = event["data"]
    user_id = user_data["user_id"]

    await redis_client.set_json(
        f"user:{user_id}", user_data, ttl=settings.USER_CACHE_TTL
    )
    logger.info(f"Cached user {user_id}")


async def handle_user_updated(event):
    """Update cached user data"""
    user_data = event["data"]
    user_id = user_data["user_id"]

    await redis_client.set_json(
        f"user:{user_id}", user_data, ttl=settings.USER_CACHE_TTL
    )
    logger.info(f"✓ Updated cache for user {user_id}")


async def handle_user_deleted(event):
    """Cancel pending orders and clean up cache"""
    user_id = event["data"]["user_id"]

    # Cancel pending orders
    with Session(engine) as session:
        statement = select(Order).where(
            Order.user_id == user_id,
            Order.status.in_([OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value]),  # type: ignore[attr-defined]
        )
        orders = session.exec(statement).all()

        for order in orders:
            try:
                # Publish event FIRST (before DB commit)
                await kafka_producer.publish_event(
                    topic=settings.KAFKA_TOPIC_ORDER_CANCELLED,
                    event_type="order.cancelled",
                    data={
                        "order_id": str(order.id),
                        "user_id": user_id,
                        "reason": "user_deleted",
                        "cancelled_at": datetime.now(UTC).isoformat(),
                    },
                    key=user_id,
                )

                # Then update DB
                order.status = OrderStatus.CANCELLED.value
                order.updated_at = datetime.now(UTC)
                session.add(order)
                session.commit()

                logger.info(f"Cancelled order {order.id} for deleted user {user_id}")

            except Exception as e:
                session.rollback()
                logger.error(
                    f"Failed to cancel order {order.id} for user {user_id}: {e}",
                    exc_info=True,
                )
                # Order stays in current state, may retry later

    # Clean up cache
    await redis_client.delete(f"user:{user_id}")
    logger.info(f"✓ Cleaned up cache for deleted user {user_id}")
