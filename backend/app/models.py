import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, JSON
from sqlmodel import Field, SQLModel, Column, String, Relationship


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


class OrderStatus(str, Enum):
    """Order lifecycle states"""

    PENDING = "pending"  # Order created, awaiting payment
    CONFIRMED = "confirmed"  # Payment confirmed
    SHIPPED = "shipped"  # Order shipped
    DELIVERED = "delivered"  # Order delivered (future)
    CANCELLED = "cancelled"  # Order cancelled


# ORDER ITEM MODELS


class OrderItemBase(SQLModel):
    """Base model for order items"""

    product_id: str
    quantity: int
    price: float


class OrderItemCreate(OrderItemBase):
    """Schema for creating order items"""

    pass


# ORDER MODELS


class OrderBase(SQLModel):
    """Base order schema"""

    user_id: str = Field(index=True)
    total_amount: float
    currency: str = Field(default="USD", max_length=3)
    shipping_address: str | None = Field(default=None)


class OrderCreate(OrderBase):
    """Schema for creating orders"""

    items: list[OrderItemCreate]


class Order(OrderBase, table=True):
    """Order database model"""

    __tablename__ = "orders"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: str = Field(
        default=OrderStatus.PENDING.value,
        sa_column=Column(String, nullable=False, index=True),
    )

    # Tracking information
    tracking_number: str | None = Field(default=None)
    carrier: str | None = Field(default=None)

    # Payment information
    payment_id: str | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )
    confirmed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    shipped_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    items: list["OrderItem"] = Relationship(back_populates="order")


class OrderItem(OrderItemBase, table=True):
    """Order item database model"""

    __tablename__ = "order_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID = Field(foreign_key="orders.id", nullable=False)
    order: Order | None = Relationship(back_populates="items")


class OrderItemPublic(OrderItemBase):
    """Public schema for order items"""

    id: uuid.UUID
    order_id: uuid.UUID


class OrderPublic(OrderBase):
    """Public order schema"""

    id: uuid.UUID
    status: str
    tracking_number: str | None
    carrier: str | None
    payment_id: str | None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    shipped_at: datetime | None
    items: list["OrderItemPublic"] = []


class OrdersPublic(SQLModel):
    """List of orders with count"""

    data: list[OrderPublic]
    count: int


class OrderConfirm(SQLModel):
    """Schema for confirming an order"""

    payment_id: str


class OrderShip(SQLModel):
    """Schema for shipping an order"""

    tracking_number: str
    carrier: str
    estimated_delivery: datetime | None = None


# USER CACHE MODELS (for type hints)


class UserData(SQLModel):
    """Schema for cached user data from Kafka"""

    user_id: str
    email: str
    name: str | None = None
    status: str = "active"


# OUTBOX PATTERN


class OutboxEvent(SQLModel, table=True):
    """
    Outbox table for transactional event publishing
    Events are written here atomically with DB changes, then published by worker
    """

    __tablename__ = "outbox_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: str = Field(index=True, unique=True)  # For idempotency
    event_type: str = Field(index=True)
    topic: str = Field(index=True)
    partition_key: str | None = Field(default=None)  # For Kafka partitioning
    payload: dict[str, Any] = Field(sa_column=Column(JSON))

    # Status tracking
    published: bool = Field(default=False, index=True)
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
