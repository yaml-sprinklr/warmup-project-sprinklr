from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select
from sqlalchemy.orm import selectinload

from app.deps import SessionDep, RedisDep
from app.models import Order, OrderCreate, OrderItem, OrderPublic, OrdersPublic
from app.services import OutboxService, UserService
from app.core.config import settings
from app.core.logging import get_logger
from app.events import OrderCreatedData

router = APIRouter(prefix="/orders", tags=["orders"])
logger = get_logger(__name__)


@router.get("/")
async def read_orders(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """Get all orders with pagination"""
    logger.debug("orders_list_requested", skip=skip, limit=limit)

    count_statement = select(func.count()).select_from(Order)
    count = session.exec(count_statement).one()
    statement = (
        select(Order)
        .options(selectinload(Order.items))  # type: ignore[arg-type]
        .order_by(Order.created_at.desc())  # type: ignore[arg-type]
        .offset(skip)
        .limit(limit)
    )
    orders = session.exec(statement).all()

    logger.info(
        "orders_list_retrieved",
        count=count,
        returned=len(orders),
        skip=skip,
        limit=limit,
    )

    return OrdersPublic(
        data=[OrderPublic.model_validate(order) for order in orders], count=count
    )


@router.post("/", response_model=OrderPublic)
async def create_order(*, session: SessionDep, redis: RedisDep, order_in: OrderCreate):
    """Create a new order"""
    logger.info(
        "order_creation_started",
        user_id=order_in.user_id,
        total_amount=float(order_in.total_amount),
        currency=order_in.currency,
        items_count=len(order_in.items),
    )

    # Step 1: Validate user exists and is active
    user = await UserService.validate_user(order_in.user_id, redis)
    if not user:
        logger.warning(
            "order_creation_failed",
            user_id=order_in.user_id,
            reason="user_not_found_or_inactive",
        )
        raise HTTPException(
            status_code=404,
            detail="User not found or inactive. Please ensure the user exists and is active before creating an order.",
        )

    logger.debug(
        "order_user_validated",
        user_id=order_in.user_id,
        user_email=user.email,
        user_name=user.name,
    )

    # Step 2: Create order
    order_data = order_in.model_dump(exclude={"items"})
    order = Order(**order_data)
    order.items = [OrderItem(**item.model_dump()) for item in order_in.items]
    session.add(order)

    # Create typed event data
    event_data = OrderCreatedData(
        order_id=str(order.id),
        user_id=order.user_id,
        status=order.status,
        total_amount=order.total_amount,
        currency=order.currency,
        shipping_address=order.shipping_address,
        items=[
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": item.price,
            }
            for item in order_in.items
        ],
        created_at=order.created_at,
    )

    # Write event to outbox (same transaction as order creation)
    OutboxService.create_event(
        session=session,
        event_type="order.created",
        topic=settings.KAFKA_TOPIC_ORDER_CREATED,
        event_data=event_data,
        partition_key=order.user_id,
    )

    # Single atomic commit for both order and outbox event
    session.commit()
    session.refresh(order)

    logger.info(
        "order_created",
        order_id=str(order.id),
        user_id=order.user_id,
        status=order.status,
        total_amount=float(order.total_amount),
        currency=order.currency,
    )

    return order
