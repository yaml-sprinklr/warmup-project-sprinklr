"""
Order lifecycle processor - handles automatic state transitions
Simulates payment and fulfillment workflows
"""

import asyncio
import logging
from datetime import datetime, UTC, timedelta
from uuid import uuid4

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models import Order, OrderStatus
from app.services import OutboxService
from app.events import OrderConfirmedData, OrderShippedData

logger = logging.getLogger(__name__)


async def start_order_processor():
    """
    Main processor loop - runs as background task
    Processes orders through their lifecycle
    """
    logger.info("Starting order lifecycle processor...")

    try:
        while True:
            try:
                await process_pending_orders()
                await process_confirmed_orders()
                await asyncio.sleep(settings.ORDER_PROCESSOR_INTERVAL)
            except Exception as e:
                logger.error(f"Order processor error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Backoff on errors

    except asyncio.CancelledError:
        logger.info("Order processor task cancelled, shutting down gracefully")
        raise


async def process_pending_orders():
    """
    Auto-confirm orders after configured delay (simulates payment processing)
    PENDING → CONFIRMED
    """
    with Session(engine) as session:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.ORDER_CONFIRM_DELAY)

        # Use row-level locking to prevent race conditions
        statement = (
            select(Order)
            .where(Order.status == OrderStatus.PENDING.value, Order.created_at < cutoff)
            .with_for_update(skip_locked=True)  # Skip rows locked by other instances
        )

        orders = session.exec(statement).all()

        for order in orders:
            try:
                # Generate payment details
                payment_id = f"pay_{uuid4().hex[:12]}"
                confirmed_at = datetime.now(UTC)

                # Update order
                order.status = OrderStatus.CONFIRMED.value
                order.confirmed_at = confirmed_at
                order.payment_id = payment_id
                order.updated_at = confirmed_at

                # Create typed event data
                event_data = OrderConfirmedData(
                    order_id=str(order.id),
                    user_id=order.user_id,
                    payment_id=payment_id,
                    total_amount=order.total_amount,
                    currency=order.currency,
                    confirmed_at=confirmed_at,
                )

                # Write event to outbox (same transaction)
                OutboxService.create_event(
                    session=session,
                    event_type="order.confirmed",
                    topic=settings.KAFKA_TOPIC_ORDER_CONFIRMED,
                    event_data=event_data,
                    partition_key=order.user_id,
                )

                session.add(order)
                session.commit()  # Atomic: order + outbox event

                logger.info(
                    f"✓ Confirmed order {order.id} with payment {payment_id}"
                )

            except Exception as e:
                session.rollback()
                logger.error(f"Error processing order {order.id}: {e}", exc_info=True)


async def process_confirmed_orders():
    """
    Auto-ship orders after configured delay (simulates fulfillment)
    CONFIRMED → SHIPPED
    """
    with Session(engine) as session:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.ORDER_SHIP_DELAY)

        # Use row-level locking to prevent race conditions
        statement = (
            select(Order)
            .where(
                Order.status == OrderStatus.CONFIRMED.value, Order.confirmed_at < cutoff
            )
            .with_for_update(skip_locked=True)
        )

        orders = session.exec(statement).all()

        for order in orders:
            try:
                # Generate shipping details
                tracking_number = f"TRK{uuid4().hex[:10].upper()}"
                carrier = "FedEx"
                estimated_delivery = datetime.now(UTC) + timedelta(days=3)
                shipped_at = datetime.now(UTC)

                # Update order
                order.status = OrderStatus.SHIPPED.value
                order.shipped_at = shipped_at
                order.tracking_number = tracking_number
                order.carrier = carrier
                order.updated_at = shipped_at

                # Create typed event data
                event_data = OrderShippedData(
                    order_id=str(order.id),
                    user_id=order.user_id,
                    tracking_number=tracking_number,
                    carrier=carrier,
                    estimated_delivery=estimated_delivery,
                    shipped_at=shipped_at,
                )

                # Write event to outbox (same transaction)
                OutboxService.create_event(
                    session=session,
                    event_type="order.shipped",
                    topic=settings.KAFKA_TOPIC_ORDER_SHIPPED,
                    event_data=event_data,
                    partition_key=order.user_id,
                )

                session.add(order)
                session.commit()  # Atomic: order + outbox event

                logger.info(
                    f"✓ Shipped order {order.id} with tracking {tracking_number}"
                )

            except Exception as e:
                session.rollback()
                logger.error(f"Error processing order {order.id}: {e}", exc_info=True)
