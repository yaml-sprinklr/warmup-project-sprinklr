import asyncio
from datetime import UTC, datetime

import structlog
from sqlmodel import Session, select

from app.core.config import settings
from app.core.redis import redis_client
from app.core.kafka import kafka_consumer, kafka_producer
from app.core.db import engine
from app.core.logging import get_logger
from app.core.tracing import (
    extract_trace_context_from_kafka_headers,
    set_trace_context,
    clear_trace_context,
    get_trace_context,
)
from app.core.metrics import kafka_events_consumed_total, kafka_events_duplicate_total
from app.models import Order, OrderStatus
from app.events import (
    UserCreatedData,
    UserUpdatedData,
    UserDeletedData,
    OrderCancelledData,
)

logger = get_logger(__name__)


async def start_consumer():
    """
    Main consumer loop - runs as background task
    Consumes user events and handles them
    """
    logger.info("user_consumer_starting")

    try:
        async for message in kafka_consumer.consume_messages():
            await handle_message(message)

    except asyncio.CancelledError:
        logger.info("user_consumer_cancelled")
        raise
    except Exception as e:
        logger.error(
            "user_consumer_crashed",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise


async def handle_message(message):
    """
    Process a single Kafka message with idempotency and trace context extraction

    Learning: This is where distributed tracing crosses the Kafka boundary!
    We extract traceparent from Kafka headers to continue the trace that started
    in the producer service (possibly hours/days ago).
    """
    event = message.value
    event_id = event["event_id"]
    event_type = event["event_type"]

    # Step 1: Extract trace context from Kafka message headers
    # Learning: The producer (outbox worker) injected traceparent header.
    # We extract it to continue the distributed trace.
    trace_context = extract_trace_context_from_kafka_headers(message.headers)

    if trace_context:
        # Set trace context so all logs and subsequent operations include trace_id
        set_trace_context(trace_context)
        structlog.contextvars.bind_contextvars(
            **{"trace.id": trace_context.trace_id},
            **{"span.id": trace_context.span_id},
            parent_span_id=trace_context.parent_span_id,
        )

    try:
        # Idempotency check
        cache_key = f"processed_event:{event_id}"
        if await redis_client.exists(cache_key):
            logger.debug(
                "kafka_event_duplicate",
                event_id=event_id,
                event_type=event_type,
            )

            # Track duplicate
            kafka_events_duplicate_total.labels(
                topic=message.topic, event_type=event_type
            ).inc()

            await kafka_consumer.commit()
            return

        # Process event based on type
        if event_type == "user.created":
            await handle_user_created(event)
        elif event_type == "user.updated":
            await handle_user_updated(event)
        elif event_type == "user.deleted":
            await handle_user_deleted(event)
        else:
            logger.warning("kafka_event_unknown_type", event_type=event_type)

        # Mark as processed
        await redis_client.set(cache_key, "1", ttl=settings.PROCESSED_EVENT_TTL)

        # Commit offset
        await kafka_consumer.commit()

        # Track successful consumption
        kafka_events_consumed_total.labels(
            topic=message.topic, event_type=event_type, status="success"
        ).inc()

        logger.info(
            "kafka_event_processed",
            event_id=event_id,
            event_type=event_type,
            has_trace_context=trace_context is not None,
        )

    except Exception as e:
        logger.error(
            "kafka_event_processing_failed",
            event_id=event_id,
            event_type=event_type,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )

        # Track failed consumption
        kafka_events_consumed_total.labels(
            topic=message.topic, event_type=event_type, status="failure"
        ).inc()

        # Don't commit - will retry
    finally:
        # Clean up trace context
        clear_trace_context()
        structlog.contextvars.clear_contextvars()


async def handle_user_created(event):
    """Cache new user data"""
    # Validate and parse event data
    event_data = UserCreatedData(**event["data"])

    # Cache the data
    await redis_client.set_json(
        f"user:{event_data.user_id}",
        event_data.model_dump(mode="json"),
        ttl=settings.USER_CACHE_TTL,
    )
    logger.info("user_cached", user_id=event_data.user_id, email=event_data.email)


async def handle_user_updated(event):
    """Update cached user data"""
    # Validate and parse event data
    event_data = UserUpdatedData(**event["data"])

    # Cache the updated data
    await redis_client.set_json(
        f"user:{event_data.user_id}",
        event_data.model_dump(mode="json"),
        ttl=settings.USER_CACHE_TTL,
    )
    logger.info("user_cache_updated", user_id=event_data.user_id)


async def handle_user_deleted(event):
    """Cancel pending orders and clean up cache"""
    # Validate and parse event data
    event_data = UserDeletedData(**event["data"])

    # Cancel pending orders
    with Session(engine) as session:
        statement = select(Order).where(
            Order.user_id == event_data.user_id,
            Order.status.in_([OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value]),  # type: ignore[attr-defined]
        )
        orders = session.exec(statement).all()

        logger.info(
            "user_deleted_cancelling_orders",
            user_id=event_data.user_id,
            orders_to_cancel=len(orders),
        )

        for order in orders:
            try:
                # Create typed event data
                cancel_data = OrderCancelledData(
                    order_id=str(order.id),
                    user_id=event_data.user_id,
                    reason="user_deleted",
                    cancelled_at=datetime.now(UTC),
                )

                # Publish event FIRST (before DB commit)
                # Get current trace context to propagate through the event chain
                trace_context = get_trace_context()

                await kafka_producer.publish_event(
                    topic=settings.KAFKA_TOPIC_ORDER_CANCELLED,
                    event_type="order.cancelled",
                    data=cancel_data.model_dump(mode="json"),
                    key=event_data.user_id,
                    trace_context=trace_context,
                )

                # Then update DB
                order.status = OrderStatus.CANCELLED.value
                order.updated_at = datetime.now(UTC)
                session.add(order)
                session.commit()

                logger.info(
                    "order_cancelled_user_deleted",
                    order_id=str(order.id),
                    user_id=event_data.user_id,
                )

            except Exception as e:
                session.rollback()
                logger.error(
                    "order_cancellation_failed",
                    order_id=str(order.id),
                    user_id=event_data.user_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True,
                )
                # Order stays in current state, may retry later

    # Clean up cache
    await redis_client.delete(f"user:{event_data.user_id}")
    logger.info("user_cache_deleted", user_id=event_data.user_id)
