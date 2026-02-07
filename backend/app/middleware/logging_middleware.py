"""
Logging Middleware for HTTP Request/Response Logging

This middleware logs every HTTP request and response with structured data,
enabling API monitoring and debugging through logs.

Why Separate from TracingMiddleware?
------------------------------------
Separation of concerns:
- TracingMiddleware: Sets up trace context (low-level infrastructure)
- LoggingMiddleware: Records HTTP events (application observability)

This separation makes it easier to:
- Enable/disable request logging without affecting tracing
- Configure different log levels for different aspects
- Test each middleware independently

Learning: In production microservices, you want structured HTTP access logs
that go to Elasticsearch, not just stdout. This middleware provides that.
"""

import time
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured HTTP access logging.

    Logs Each Request With:
    ----------------------
    - HTTP method, path, query parameters
    - Request duration (milliseconds)
    - Response status code
    - Client IP address
    - User agent
    - Error details (if 5xx status)

    Learning: This is similar to nginx access logs or Apache logs, but:
    1. Structured (JSON) instead of plain text
    2. Includes trace_id automatically (from TracingMiddleware)
    3. Searchable in Elasticsearch
    4. Correlates with application logs via trace_id

    Middleware Order:
    ----------------
    CORRECT:
        app.add_middleware(LoggingMiddleware)  # Logs after tracing is set up
        app.add_middleware(TracingMiddleware)  # Sets trace context

    Why? Middleware executes in reverse order of registration:
        TracingMiddleware → LoggingMiddleware → Route Handler

    INCORRECT:
        app.add_middleware(TracingMiddleware)
        app.add_middleware(LoggingMiddleware)

    Would result in:
        LoggingMiddleware → TracingMiddleware → Route Handler
        (logs wouldn't have trace_id because TracingMiddleware hasn't run yet!)
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """
        Log HTTP request and response details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response

        Learning: We measure duration by recording start time, calling next handler,
        then calculating elapsed time. This captures total request processing time
        including all downstream middleware and route handlers.
        """

        # Capture request start time
        start_time = time.time()

        # Extract request metadata
        # ========================
        # Using ECS (Elastic Common Schema) field names for better compatibility
        # with Elasticsearch, Kibana, and other observability tools.
        # These are the fields you'll query in Kibana when debugging:
        # - "Show me all POST /orders requests"
        # - "Find slow requests (duration > 1000ms)"
        # - "Which client IP is getting 500 errors?"

        method = request.method
        path = request.url.path
        query_params = str(request.url.query) if request.url.query else None

        # Client information (useful for debugging client-specific issues)
        client_ip = None
        if request.client:
            client_ip = request.client.host

        user_agent = request.headers.get("user-agent")

        # Log incoming request
        # ====================
        # Learning: We log request START at DEBUG level because it's verbose.
        # The request COMPLETION is logged at INFO with duration_ms, status code, etc.
        #
        # This way, at LOG_LEVEL=INFO you see all completed requests with metrics,
        # but skip the less useful "request received" logs.

        logger.debug(
            "http_request_received",
            **{"http.request.method": method},
            **{"url.path": path},
            **{"url.query": query_params},
            **{"client.ip": client_ip},
            **{"user_agent.original": user_agent},
        )

        # Process request
        # ===============
        response = None
        exception_raised = None

        try:
            response = await call_next(request)
        except Exception as e:
            # Catch any unhandled exception
            # Learning: Middleware can catch exceptions that escaped route handlers.
            # This is a safety net for logging unexpected errors.
            exception_raised = e

            # Create 500 response
            # In production, you'd want a proper error handler that returns JSON
            response = Response(
                content="Internal Server Error",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Calculate duration
        # ==================
        duration_ms = (time.time() - start_time) * 1000

        # Determine log level based on response
        # ======================================
        # Learning: Log all HTTP requests at INFO level for observability
        # - 2xx: INFO (success - need for Kibana queries on duration_ms)
        # - 4xx: INFO (client error, worth noting)
        # - 5xx: ERROR (server error, needs investigation)
        #
        # All requests are logged at INFO or higher so we can search by
        # duration_ms, status codes, and paths in Kibana.

        status_code = response.status_code
        log_level = "info"  # Changed from "debug" to "info"

        if status_code >= 500:
            log_level = "error"
        elif status_code >= 400:
            log_level = "info"
        elif duration_ms > 1000:
            # Slow request (>1s) even if successful
            # Learning: Performance issues are worth logging even if status is 200
            log_level = "warning"

        # Build log entry with ECS field names
        # =====================================
        log_data = {
            "http.request.method": method,
            "url.path": path,
            "url.query": query_params,
            "http.response.status_code": status_code,
            "event.duration": round(duration_ms * 1_000_000, 0),  # ECS uses nanoseconds
            "duration_ms": round(duration_ms, 2),  # Keep for readability
            "client.ip": client_ip,
            "user_agent.original": user_agent,
        }

        # Add error details if exception occurred
        if exception_raised:
            log_data["error_type"] = type(exception_raised).__name__
            log_data["error_message"] = str(exception_raised)

        # Log based on severity
        # =====================
        if log_level == "error":
            logger.error(
                "http_request_completed",
                **log_data,
                exc_info=exception_raised,  # Includes stack trace
            )
        elif log_level == "warning":
            logger.warning("http_request_slow", **log_data)
        else:
            # All successful requests (2xx, 3xx, 4xx) logged at INFO
            logger.info("http_request_completed", **log_data)

        # Re-raise exception if one occurred
        # ===================================
        # Learning: After logging, re-raise so FastAPI's exception handlers can
        # process it properly (e.g., return JSON error response instead of our
        # generic "Internal Server Error" text).
        #
        # Why not just let it propagate without catching?
        # Because we want to log the error with structured data (trace_id, etc.)
        # before it reaches the default error handler.
        if exception_raised:
            raise exception_raised

        return response


# Helper for Sampling
# ===================
# In high-traffic production systems, you might want to sample logs.


class SampledLoggingMiddleware(LoggingMiddleware):
    """
    Logging middleware with sampling for high-traffic services.

    Only logs a percentage of successful requests to reduce volume,
    but always logs errors.

    Usage:
        app.add_middleware(SampledLoggingMiddleware, sample_rate=0.01)  # Log 1%

    Learning: At 10,000 req/s, logging every request creates:
    - 864 million log entries/day
    - Significant Elasticsearch storage costs
    - Performance overhead from JSON serialization

    Sampling reduces volume while preserving error visibility.
    """

    def __init__(self, app, sample_rate: float = 0.1):
        """
        Args:
            app: FastAPI application
            sample_rate: Fraction of successful requests to log (0.0 to 1.0)
                        Errors are always logged regardless of sample_rate
        """
        super().__init__(app)
        self.sample_rate = sample_rate

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """
        Conditionally log based on sample rate and response status.

        Learning: Sampling should be trace-aware. If you sample 10% of requests,
        you should sample entire traces, not random log lines. Otherwise, you'll
        have incomplete traces in your logs.

        Advanced: Use trace_id hash to determine sampling (consistent sampling).
        If trace X is sampled on service A, it should also be sampled on service B.
        """
        import random

        # Check if we should sample this request
        should_sample = random.random() < self.sample_rate

        if should_sample:
            # Use parent class logic (normal logging)
            return await super().dispatch(request, call_next)
        else:
            # Skip logging for sampled-out requests
            # But still process the request normally
            response = await call_next(request)

            # Always log errors, even if sampled out
            if response.status_code >= 500:
                # Fallback to parent class logging
                return await super().dispatch(request, call_next)

            return response
