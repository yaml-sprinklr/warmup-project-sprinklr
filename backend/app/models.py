import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


class OrderBase(SQLModel):
    amount: int


class OrderCreate(OrderBase):
    user_id: uuid.UUID


class Order(OrderBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class OrderPublic(OrderBase):
    id: uuid.UUID
    created_at: datetime


class OrdersPublic(SQLModel):
    data: list[OrderPublic]
    count: int
