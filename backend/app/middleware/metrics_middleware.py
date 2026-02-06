"""
HTTP Metrics Middleware for FastAPI

Automatically tracks HTTP request metrics including:
- Request counts by method, endpoint, and status code group
- Request duration histograms
- In-progress request gauge
"""

import time
import re
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track HTTP request metrics"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Compile regex patterns for endpoint templating
        self.uuid_pattern = re.compile(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(/|$)"
        )
        self.numeric_pattern = re.compile(r"/\d+(/|$)")

    def _template_path(self, path: str) -> str:
        """
        Convert raw path to templated path to avoid high cardinality

        Examples:
            /orders/123e4567-e89b-12d3-a456-426614174000 -> /orders/{id}
            /orders/123 -> /orders/{id}
            /health/ready -> /health/ready
        """
        # Replace UUIDs with {id}
        templated = self.uuid_pattern.sub(r"/{id}\1", path)
        # Replace numeric IDs with {id}
        templated = self.numeric_pattern.sub(r"/{id}\1", templated)
        return templated

    def _get_status_group(self, status_code: int) -> str:
        """
        Group status codes into classes (2xx, 3xx, 4xx, 5xx)

        Args:
            status_code: HTTP status code

        Returns:
            Status code group as string (e.g., "2xx", "4xx")
        """
        return f"{status_code // 100}xx"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track metrics"""
        method = request.method
        raw_path = request.url.path
        endpoint = self._template_path(raw_path)

        # Track in-progress requests
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Track 5xx for unhandled exceptions
            status_code = 500
            raise
        finally:
            # Calculate duration
            duration = time.time() - start_time
            status_group = self._get_status_group(status_code)

            # Record metrics
            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_group
            ).inc()

            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

        return response
