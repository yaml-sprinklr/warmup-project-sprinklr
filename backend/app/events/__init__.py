"""
Event schemas for Kafka events
Centralized event definitions using Pydantic for type safety
"""

from app.events.base import EventEnvelope, BaseEventData
from app.events.user_events import (
    UserCreatedData,
    UserUpdatedData,
    UserDeletedData,
)
from app.events.order_events import (
    OrderCreatedData,
    OrderConfirmedData,
    OrderShippedData,
    OrderCompletedData,
    OrderCancelledData,
)

__all__ = [
    # Base
    "EventEnvelope",
    "BaseEventData",
    # User events
    "UserCreatedData",
    "UserUpdatedData",
    "UserDeletedData",
    # Order events
    "OrderCreatedData",
    "OrderConfirmedData",
    "OrderShippedData",
    "OrderCompletedData",
    "OrderCancelledData",
]
