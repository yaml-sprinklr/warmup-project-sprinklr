"""
Base event schemas for Kafka event envelope
"""

from datetime import datetime, UTC
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

# Generic type for event data
TData = TypeVar("TData", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[TData]):
    """
    Standard Kafka event envelope
    Wraps all events with metadata
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = "1.0"
    data: TData

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class BaseEventData(BaseModel):
    """Base class for all event data payloads"""

    class Config:
        # Allow datetime serialization
        json_encoders = {datetime: lambda v: v.isoformat()}
        # Use enum values in JSON
        use_enum_values = True
