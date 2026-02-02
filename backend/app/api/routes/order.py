from typing import Any
from fastapi import APIRouter
from sqlmodel import func, select
from app.deps import SessionDep
from app.models import Order, OrderCreate, OrderPublic, OrdersPublic

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/")
async def read_orders(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    count_statement = select(func.count()).select_from(Order)
    count = session.exec(count_statement).one()
    statement = (
        select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit)
    )
    orders = session.exec(statement).all()

    return OrdersPublic(
        data=[OrderPublic.model_validate(order) for order in orders], count=count
    )


@router.post("/", response_model=OrderPublic)
async def create_order(*, session: SessionDep, order_in: OrderCreate):
    order = Order.model_validate(order_in)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order
