import os
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from app.api.main import api_router  # noqa: E402
from app.deps import get_db, get_redis  # noqa: E402


def create_test_client(redis_ok: bool = True, db_ok: bool = True) -> TestClient:
    class FakeSession:
        def exec(self, _statement):
            if not db_ok:
                raise RuntimeError("db down")
            return None

    def override_get_db():
        yield FakeSession()

    class FakeRedis:
        async def ping(self) -> bool:
            return redis_ok

    def override_get_redis():
        return FakeRedis()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    return TestClient(app)


class TestHealthEndpoints(unittest.TestCase):
    def test_liveness_returns_alive(self) -> None:
        client = create_test_client()
        response = client.get("/api/v1/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "alive"})

    def test_readiness_reports_ready(self) -> None:
        client = create_test_client()
        response = client.get("/api/v1/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ready", "checks": {"database": "connected", "redis": "connected"}},
        )

    def test_readiness_reports_not_ready_when_redis_down(self) -> None:
        client = create_test_client(redis_ok=False)
        response = client.get("/api/v1/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "not ready",
                "checks": {"database": "connected", "redis": "disconnected"},
            },
        )
