from fastapi import APIRouter, Response, status
from sqlmodel import literal, select
from app.api.routes import order
from app.deps import RedisDep, SessionDep

api_router = APIRouter()

api_router.include_router(order.router)


@api_router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@api_router.get("/health/ready")
async def readiness(response: Response, session: SessionDep, redis: RedisDep):
    health_status = {"status": "ready", "checks": {}}
    all_healthy = True

    # Check PostgreSQL
    try:
        session.exec(select(literal("SELECT 1")))
        health_status["checks"]["database"] = "connected"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        all_healthy = False

    # Check Redis
    try:
        is_alive = await redis.ping()
        if is_alive:
            health_status["checks"]["redis"] = "connected"
        else:
            health_status["checks"]["redis"] = "disconnected"
            all_healthy = False
    except Exception as e:
        health_status["checks"]["redis"] = f"error: {str(e)}"
        all_healthy = False

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        health_status["status"] = "not ready"

    return health_status
