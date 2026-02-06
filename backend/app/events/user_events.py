"""
User event schemas
"""

from datetime import datetime
from pydantic import EmailStr

from app.events.base import BaseEventData


class UserCreatedData(BaseEventData):
    """User creation event payload"""

    user_id: str
    email: EmailStr
    name: str
    status: str = "active"
    created_at: datetime


class UserUpdatedData(BaseEventData):
    """User update event payload"""

    user_id: str
    email: EmailStr | None = None
    name: str | None = None
    status: str | None = None
    updated_at: datetime


class UserDeletedData(BaseEventData):
    """User deletion event payload"""

    user_id: str
    deleted_at: datetime
    reason: str | None = None
