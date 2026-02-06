"""  
Outbox worker - separate process that publishes events from outbox to Kafka
Runs as independent K8s deployment for reliability
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, UTC

from prometheus_client import start_http_server
from sqlmodel import Session, select, func

from app.core.config import settings
from app.core.db import engine
from app.core.kafka import kafka_producer
from app.core.metrics import (
    registry,
    outbox_events_pending,
    outbox_events_processed_total,
    outbox_publish_duration_seconds,
    outbox_retry_attempts_total,
)
from app.models import OutboxEvent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_flag = True


async def process_outbox_events():
    """
    Main worker loop - polls outbox table and publishes events
    """
    logger.info("Starting outbox worker...")

    await kafka_producer.start()

    try:
        while not shutdown_flag:
            try:
                published_count = await publish_pending_events(settings.OUTBOX_BATCH_SIZE)

                if published_count > 0:
                    logger.info(f"Published {published_count} events")
                
                # Update pending events gauge
                update_pending_count()

                await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Error in outbox processing: {e}", exc_info=True)
                await asyncio.sleep(settings.OUTBOX_ERROR_BACKOFF_SECONDS)

    except asyncio.CancelledError:
        logger.info("Outbox worker cancelled")
        raise
    finally:
        await kafka_producer.stop()
        logger.info("Outbox worker stopped")


async def publish_pending_events(batch_size: int) -> int:
    """
    Fetch and publish unpublished events from outbox

    Args:
        batch_size: Maximum number of events to process

    Returns:
        Number of events published
    """
    published_count = 0

    with Session(engine) as session:
        # Fetch unpublished events with row locking (for multi-worker safety)
        statement = (
            select(OutboxEvent)
            .where(OutboxEvent.published == False)  # noqa: E712
            .order_by(OutboxEvent.created_at.asc())  # type: ignore
            .limit(batch_size)
            .with_for_update(skip_locked=True)  # Skip locked rows
        )

        events = session.exec(statement).all()

        for event in events:
            start_time = time.time()
            try:
                if not kafka_producer.producer:
                    raise RuntimeError("Kafka producer not started")
                # Publish to Kafka
                await kafka_producer.producer.send_and_wait(
                    topic=event.topic,
                    value=event.payload,
                    key=event.partition_key.encode("utf-8")
                    if event.partition_key
                    else None,
                )

                # Mark as published
                event.published = True
                event.published_at = datetime.now(UTC)
                event.updated_at = datetime.now(UTC)

                session.add(event)
                session.commit()

                published_count += 1
                
                # Track successful processing
                duration = time.time() - start_time
                outbox_events_processed_total.labels(status="success").inc()
                outbox_publish_duration_seconds.observe(duration)

                logger.debug(
                    f"Published event {event.event_id} to {event.topic} "
                    f"(type: {event.event_type})"
                )

            except Exception as e:
                session.rollback()

                # Update failure tracking
                event.attempts += 1
                event.last_error = str(e)[:settings.OUTBOX_ERROR_MESSAGE_MAX_LENGTH]
                event.updated_at = datetime.now(UTC)

                session.add(event)
                session.commit()
                
                # Track failed processing and retries
                outbox_events_processed_total.labels(status="failure").inc()
                outbox_retry_attempts_total.labels(event_type=event.event_type).inc()

                logger.error(
                    f"Failed to publish event {event.event_id} "
                    f"(attempt {event.attempts}): {e}"
                )

                # TODO: Move to dead letter queue after max attempts
                if event.attempts >= settings.OUTBOX_MAX_RETRY_ATTEMPTS:
                    logger.critical(
                        f"Event {event.event_id} failed {event.attempts} times, "
                        "needs manual intervention"
                    )

    return published_count


def update_pending_count():
    """
    Update the outbox_events_pending gauge with current count
    """
    try:
        with Session(engine) as session:
            count_statement = select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.published == False  # noqa: E712
            )
            pending_count = session.exec(count_statement).one()
            outbox_events_pending.set(pending_count)
    except Exception as e:
        logger.error(f"Failed to update pending count metric: {e}")


async def main():
    """Entry point for outbox worker"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Outbox worker starting up...")

    # Start metrics server
    metrics_port = 8000
    if hasattr(settings, "METRICS_PORT"):
        metrics_port = int(settings.METRICS_PORT)  # type: ignore
    start_http_server(metrics_port, registry=registry)
    logger.info(f"Metrics server started on port {metrics_port}")

    try:
        await process_outbox_events()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error in outbox worker: {e}", exc_info=True)
        sys.exit(1)
    logger.info("Outbox worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
