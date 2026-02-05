from typing import Any

from fastapi import APIRouter
from sqlmodel import func, select
from sqlalchemy.orm import selectinload

from app.deps import SessionDep
from app.models import Order, OrderCreate, OrderItem, OrderPublic, OrdersPublic
from app.services import OutboxService
from app.core.config import settings

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/")
async def read_orders(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """Get all orders with pagination"""
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

    return OrdersPublic(
        data=[OrderPublic.model_validate(order) for order in orders], count=count
    )


@router.post("/", response_model=OrderPublic)
async def create_order(*, session: SessionDep, order_in: OrderCreate):
    """Create a new order"""
    order_data = order_in.model_dump(exclude={"items"})
    order = Order(**order_data)
    order.items = [OrderItem(**item.model_dump()) for item in order_in.items]
    session.add(order)

    # Write event to outbox (same transaction as order creation)
    OutboxService.create_event(
        session=session,
        event_type="order.created",
        topic=settings.KAFKA_TOPIC_ORDER_CREATED,
        data={
            "order_id": str(order.id),
            "user_id": order.user_id,
            "status": order.status,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "shipping_address": order.shipping_address,
            "items": [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "price": item.price,
                }
                for item in order_in.items
            ],
            "created_at": order.created_at.isoformat(),
        },
        partition_key=order.user_id,
    )

    # Single atomic commit for both order and outbox event
    session.commit()
    session.refresh(order)

    return order
