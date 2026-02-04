from collections.abc import Generator
from sqlmodel import Session
from app.core.db import engine
from app.core.redis import RedisClient, redis_client
from typing import Annotated
from fastapi import Depends


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_redis() -> RedisClient:
    return redis_client


RedisDep = Annotated[RedisClient, Depends(get_redis)]
SessionDep = Annotated[Session, Depends(get_db)]
