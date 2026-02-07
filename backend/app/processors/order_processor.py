"""
Order lifecycle processor - handles automatic state transitions with trace propagation
Simulates payment and fulfillment workflows

Learning: Background tasks don't have HTTP request context, so trace_id
from the original order creation needs to be propagated through the database.
We read trace_id from the outbox event to continue the trace.
"""

import asyncio
from datetime import datetime, UTC, timedelta
from uuid import uuid4

from sqlmodel import Session, select
import structlog

from app.core.config import settings
from app.core.db import engine
from app.core.logging import get_logger
from app.core.tracing import (
    create_trace_context,
    set_trace_context,
    clear_trace_context,
)
from app.models import Order, OrderStatus, OutboxEvent
from app.services import OutboxService
from app.events import OrderConfirmedData, OrderShippedData

logger = get_logger(__name__)


async def start_order_processor():
    """
    Main processor loop - runs as background task
    Processes orders through their lifecycle
    """
    logger.info("order_processor_starting")

    try:
        while True:
            try:
                await process_pending_orders()
                await process_confirmed_orders()
                await asyncio.sleep(settings.ORDER_PROCESSOR_INTERVAL)
            except Exception as e:
                logger.error(
                    "order_processor_error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(5)  # Backoff on errors

    except asyncio.CancelledError:
        logger.info("order_processor_cancelled")
        raise


async def process_pending_orders():
    """
    Auto-confirm orders after configured delay (simulates payment processing)
    PENDING → CONFIRMED

    Learning: This function processes orders created by HTTP requests minutes/hours ago.
    To continue the trace, we:
    1. Find the original order.created outbox event (has the trace_id)
    2. Reconstruct trace context from that event
    3. Set it in contextvars so new outbox events inherit the same trace_id
    4. Result: All logs and events for this order share the same trace_id!
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
                # Step 1: Find the original outbox event to extract trace context
                # Learning: We query for order.created event because it has the
                # trace_id from the original HTTP request that created this order
                original_event_stmt = (
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.event_type == "order.created",
                        OutboxEvent.partition_key == order.user_id,
                        OutboxEvent.payload["data"]["order_id"].as_string()
                        == str(order.id),
                    )
                    .limit(1)
                )

                original_event = session.exec(original_event_stmt).first()

                # Step 2: Reconstruct and set trace context
                if original_event and original_event.trace_id:
                    # Continue the existing trace
                    trace_context = create_trace_context(
                        trace_id=original_event.trace_id,
                        parent_span_id=original_event.span_id,  # Our parent is the creation span
                    )
                    set_trace_context(trace_context)
                    structlog.contextvars.bind_contextvars(
                        **{"trace.id": trace_context.trace_id},
                        **{"span.id": trace_context.span_id},
                        parent_span_id=trace_context.parent_span_id,
                    )
                else:
                    # No trace context found, start new trace
                    trace_context = create_trace_context()
                    set_trace_context(trace_context)
                    structlog.contextvars.bind_contextvars(
                        **{"trace.id": trace_context.trace_id},
                        **{"span.id": trace_context.span_id},
                    )

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
                # Learning: OutboxService.create_event() will automatically capture
                # the trace_id we just set in contextvars above!
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
                    "order_confirmed",
                    order_id=str(order.id),
                    user_id=order.user_id,
                    payment_id=payment_id,
                )

            except Exception as e:
                session.rollback()
                logger.error(
                    "order_confirmation_failed",
                    order_id=str(order.id),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True,
                )
            finally:
                # Clean up trace context for next iteration
                clear_trace_context()
                structlog.contextvars.clear_contextvars()


async def process_confirmed_orders():
    """
    Auto-ship orders after configured delay (simulates fulfillment)
    CONFIRMED → SHIPPED

    Learning: Same pattern as process_pending_orders - we continue the trace
    by finding the original order.created event and reconstructing trace context.
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
                # Reconstruct trace context from original event
                original_event_stmt = (
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.event_type == "order.created",
                        OutboxEvent.partition_key == order.user_id,
                        OutboxEvent.payload["data"]["order_id"].as_string()
                        == str(order.id),
                    )
                    .limit(1)
                )

                original_event = session.exec(original_event_stmt).first()

                if original_event and original_event.trace_id:
                    trace_context = create_trace_context(
                        trace_id=original_event.trace_id,
                        parent_span_id=original_event.span_id,
                    )
                    set_trace_context(trace_context)
                    structlog.contextvars.bind_contextvars(
                        **{"trace.id": trace_context.trace_id},
                        **{"span.id": trace_context.span_id},
                        parent_span_id=trace_context.parent_span_id,
                    )
                else:
                    trace_context = create_trace_context()
                    set_trace_context(trace_context)
                    structlog.contextvars.bind_contextvars(
                        **{"trace.id": trace_context.trace_id},
                        **{"span.id": trace_context.span_id},
                    )

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
                    "order_shipped",
                    order_id=str(order.id),
                    user_id=order.user_id,
                    tracking_number=tracking_number,
                    carrier=carrier,
                )

            except Exception as e:
                session.rollback()
                logger.error(
                    "order_shipping_failed",
                    order_id=str(order.id),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    exc_info=True,
                )
            finally:
                clear_trace_context()
                structlog.contextvars.clear_contextvars()
