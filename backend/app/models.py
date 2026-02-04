import uuid
from enum import Enum
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel, Column, String


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


class OrderItem(OrderItemBase, table=True):
    """Order item database model"""

    __tablename__ = "order_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID = Field(foreign_key="orders.id", nullable=False)


class OrderItemPublic(OrderItemBase):
    """Public schema for order items"""

    id: uuid.UUID
    order_id: uuid.UUID


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
    items: list[OrderItemPublic] = []


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
