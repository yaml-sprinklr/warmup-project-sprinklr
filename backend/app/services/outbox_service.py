"""
Outbox service - handles transactional event publishing with distributed tracing support
"""

from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.tracing import get_trace_context
from app.models import OutboxEvent
from app.events.base import BaseEventData

logger = get_logger(__name__)


class OutboxService:
    """Service for transactional outbox pattern"""

    @staticmethod
    def create_event(
        session: Session,
        event_type: str,
        topic: str,
        event_data: BaseEventData,
        partition_key: str | None = None,
    ) -> OutboxEvent:
        """
        Create an outbox event (writes to DB in same transaction) with trace context.

        Learning: This method captures the current trace context (trace_id, span_id)
        and persists it in the outbox table. This enables the outbox worker to:
        1. Reconstruct the trace context hours/days later when publishing to Kafka
        2. Inject traceparent header into Kafka messages
        3. Continue the distributed trace across async boundaries

        Args:
            session: Database session (must be same as business logic transaction)
            event_type: Type of event (e.g., "order.created")
            topic: Kafka topic name
            event_data: Pydantic model with event payload
            partition_key: Key for Kafka partitioning (usually user_id)

        Returns:
            OutboxEvent: Created outbox event with trace context

        Trace Context Flow:
        ------------------
        HTTP Request → TracingMiddleware sets trace_id in contextvars
        ↓
        API Route creates order
        ↓
        OutboxService.create_event() captures trace_id from contextvars
        ↓
        Trace context persisted in outbox_events table
        ↓
        [Hours/days later...]
        ↓
        Outbox worker reads event, extracts trace_id
        ↓
        Worker injects traceparent header into Kafka message
        ↓
        Consumer extracts traceparent and continues trace!
        """
        event_id = str(uuid4())

        # Capture current trace context from contextvars
        # Learning: get_trace_context() reads from ContextVar, which is automatically
        # isolated per async request. This is safe even with 1000s of concurrent requests.
        trace_context = get_trace_context()

        # Full event envelope as per schema
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0",
            "data": event_data.model_dump(mode="json"),
        }

        # Create outbox event WITH trace context
        # Learning: If trace_context is None (e.g., event created by background job
        # without HTTP request), these fields will be NULL. That's OK - the event
        # still gets published, just without trace correlation.
        outbox_event = OutboxEvent(
            event_id=event_id,
            event_type=event_type,
            topic=topic,
            partition_key=partition_key,
            payload=payload,
            # Trace context fields (NEW)
            trace_id=trace_context.trace_id if trace_context else None,
            span_id=trace_context.span_id if trace_context else None,
            parent_span_id=trace_context.parent_span_id if trace_context else None,
        )

        session.add(outbox_event)
        # Note: Do NOT commit here - let the caller commit atomically with business logic

        logger.info(
            "outbox_event_created",
            event_id=event_id,
            event_type=event_type,
            topic=topic,
            has_trace_context=trace_context is not None,
        )

        return outbox_event
