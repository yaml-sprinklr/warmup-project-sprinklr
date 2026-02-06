"""
Outbox service - handles transactional event publishing
"""

import logging
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.models import OutboxEvent
from app.events.base import BaseEventData

logger = logging.getLogger(__name__)


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
        Create an outbox event (writes to DB in same transaction)

        Args:
            session: Database session (must be same as business logic transaction)
            event_type: Type of event (e.g., "order.created")
            topic: Kafka topic name
            event_data: Pydantic model with event payload
            partition_key: Key for Kafka partitioning (usually user_id)

        Returns:
            OutboxEvent: Created outbox event
        """
        event_id = str(uuid4())

        # Full event envelope as per schema
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0",
            "data": event_data.model_dump(mode="json"),
        }

        outbox_event = OutboxEvent(
            event_id=event_id,
            event_type=event_type,
            topic=topic,
            partition_key=partition_key,
            payload=payload,
        )

        session.add(outbox_event)
        # Note: Do NOT commit here - let the caller commit atomically with business logic

        logger.debug(f"Created outbox event {event_id} for topic {topic}")

        return outbox_event
