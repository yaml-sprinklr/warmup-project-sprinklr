"""
Outbox worker - separate process that publishes events from outbox to Kafka with trace propagation
Runs as independent K8s deployment for reliability

Learning: This worker reconstructs trace context from the outbox table and injects
it into Kafka message headers, enabling end-to-end distributed tracing.
"""

import asyncio
import signal
import sys
import time
from datetime import datetime, UTC

from prometheus_client import start_http_server
from sqlmodel import Session, select, func
import structlog

from app.core.config import settings
from app.core.db import engine
from app.core.kafka import kafka_producer
from app.core.logging import configure_logging, get_logger
from app.core.tracing import create_trace_context, TraceContext
from app.core.metrics.metrics import (
    registry,
    outbox_events_pending,
    outbox_events_processed_total,
    outbox_publish_duration_seconds,
    outbox_retry_attempts_total,
    kafka_events_published_total,
    kafka_publish_duration_seconds,
)
from app.models import OutboxEvent

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    logger.info("shutdown_signal_received", signal=sig)
    shutdown_flag = True


async def process_outbox_events():
    """
    Main worker loop - polls outbox table and publishes events
    """
    logger.info("outbox_worker_starting")

    await kafka_producer.start()

    try:
        while not shutdown_flag:
            try:
                published_count = await publish_pending_events(
                    settings.OUTBOX_BATCH_SIZE
                )

                if published_count > 0:
                    logger.info("outbox_events_published", count=published_count)

                # Update pending events gauge
                update_pending_count()

                await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(
                    "outbox_processing_error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(settings.OUTBOX_ERROR_BACKOFF_SECONDS)

    except asyncio.CancelledError:
        logger.info("outbox_worker_cancelled")
        raise
    finally:
        await kafka_producer.stop()
        logger.info("outbox_worker_stopped")


async def publish_pending_events(batch_size: int) -> int:
    """
    Fetch and publish unpublished events from outbox with trace context propagation

    Learning: For each outbox event, we:
    1. Extract trace_id/span_id from the database row
    2. Reconstruct W3C traceparent header
    3. Inject as Kafka message header
    4. Consumer can extract and continue the trace!

    This enables tracing from HTTP request → DB → Kafka → Consumer,
    even when the outbox worker processes events hours/days later.

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

            # Reconstruct trace context from outbox event
            # Learning: The trace_id was captured when the event was created
            # (minutes/hours ago). We reconstruct it to continue the trace.
            trace_context = None
            if event.trace_id:
                trace_context = create_trace_context(
                    trace_id=event.trace_id,
                    parent_span_id=event.span_id,  # The publishing span's parent is the creation span
                )

                # Bind to structlog so logs include trace_id
                structlog.contextvars.bind_contextvars(
                    **{"trace.id": trace_context.trace_id},
                    **{"span.id": trace_context.span_id},
                    parent_span_id=trace_context.parent_span_id,
                )

            try:
                if not kafka_producer.producer:
                    raise RuntimeError("Kafka producer not started")

                # Prepare Kafka headers with trace context
                # Learning: Kafka headers are list of (str, bytes) tuples
                headers = []
                if trace_context:
                    # Inject W3C traceparent header
                    traceparent = trace_context.to_traceparent_header()
                    headers.append(("traceparent", traceparent.encode("utf-8")))

                # Publish to Kafka with trace headers
                kafka_start_time = time.time()
                await kafka_producer.producer.send_and_wait(
                    topic=event.topic,
                    value=event.payload,
                    key=event.partition_key.encode("utf-8")
                    if event.partition_key
                    else None,
                    headers=headers,  # NEW: Include trace context
                )
                kafka_duration = time.time() - kafka_start_time

                # Track Kafka publish metrics
                kafka_events_published_total.labels(
                    topic=event.topic, event_type=event.event_type, status="success"
                ).inc()
                kafka_publish_duration_seconds.labels(
                    topic=event.topic, event_type=event.event_type
                ).observe(kafka_duration)

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

                logger.info(
                    "outbox_event_published",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    topic=event.topic,
                    has_trace_context=trace_context is not None,
                )

            except Exception as e:
                session.rollback()

                # Track failed Kafka publish
                kafka_events_published_total.labels(
                    topic=event.topic, event_type=event.event_type, status="failure"
                ).inc()

                # Update failure tracking
                event.attempts += 1
                event.last_error = str(e)[: settings.OUTBOX_ERROR_MESSAGE_MAX_LENGTH]
                event.updated_at = datetime.now(UTC)

                session.add(event)
                session.commit()

                # Track failed processing and retries
                outbox_events_processed_total.labels(status="failure").inc()
                outbox_retry_attempts_total.labels(event_type=event.event_type).inc()

                logger.error(
                    "outbox_event_publish_failed",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    attempts=event.attempts,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

                # TODO: Move to dead letter queue after max attempts
                if event.attempts >= settings.OUTBOX_MAX_RETRY_ATTEMPTS:
                    logger.critical(
                        "outbox_event_max_retries_exceeded",
                        event_id=event.event_id,
                        attempts=event.attempts,
                        needs_manual_intervention=True,
                    )
            finally:
                # Clear trace context for next event
                structlog.contextvars.clear_contextvars()

    return published_count


def update_pending_count():
    """
    Update the outbox_events_pending gauge with current count
    """
    try:
        with Session(engine) as session:
            count_statement = (
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.published == False  # noqa: E712
                )
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

    logger.info(
        "outbox_worker_main_starting",
        service=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
    )

    # Start metrics server
    metrics_port = 8000
    if hasattr(settings, "METRICS_PORT"):
        metrics_port = int(settings.METRICS_PORT)  # type: ignore
    start_http_server(metrics_port, registry=registry)
    logger.info("metrics_server_started", port=metrics_port)

    try:
        await process_outbox_events()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error(
            "outbox_worker_fatal_error",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        sys.exit(1)
    logger.info("outbox_worker_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
