from fastapi import APIRouter, Response, status
from sqlmodel import literal, select
from app.api.routes import order
from app.deps import SessionDep

api_router = APIRouter()

api_router.include_router(order.router)


@api_router.get("/health/live")
def liveness():
    return {"status": "alive"}


@api_router.get("/health/ready")
def readiness(response: Response, session: SessionDep):
    try:
        session.exec(select(literal("SELECT 1")))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not ready", "database": "disconnected", "error": str(e)}
