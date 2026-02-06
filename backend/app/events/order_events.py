"""
Order event schemas
"""

from datetime import datetime
from decimal import Decimal
from pydantic import Field

from app.events.base import BaseEventData


class OrderCreatedData(BaseEventData):
    """Order creation event payload"""

    order_id: str
    user_id: str
    status: str = "pending"
    product_id: str | None = None  # For simple orders
    quantity: int | None = Field(default=None, gt=0)
    total_amount: Decimal
    currency: str = "USD"
    shipping_address: dict | None = None
    items: list[dict] | None = None  # For multi-item orders
    created_at: datetime


class OrderConfirmedData(BaseEventData):
    """Order confirmation event payload (payment processed)"""

    order_id: str
    user_id: str
    status: str = "confirmed"
    payment_id: str
    total_amount: Decimal
    currency: str = "USD"
    confirmed_at: datetime


class OrderShippedData(BaseEventData):
    """Order shipment event payload"""

    order_id: str
    user_id: str
    status: str = "shipped"
    tracking_number: str
    carrier: str
    estimated_delivery: datetime
    shipped_at: datetime


class OrderCompletedData(BaseEventData):
    """Order completion event payload (fulfilled)"""

    order_id: str
    user_id: str
    status: str = "completed"
    payment_id: str
    tracking_number: str | None = None
    total_amount: Decimal
    currency: str = "USD"
    completed_at: datetime


class OrderCancelledData(BaseEventData):
    """Order cancellation event payload"""

    order_id: str
    user_id: str
    status: str = "cancelled"
    reason: str
    cancelled_at: datetime
