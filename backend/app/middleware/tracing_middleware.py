"""
Tracing Middleware for W3C Trace Context Propagation

This middleware handles the extraction and injection of trace context from/to
HTTP requests, implementing the W3C Trace Context specification.

Responsibilities:
1. Extract traceparent header from incoming requests
2. Generate new trace if header is missing
3. Set trace context in contextvars for automatic log inclusion
4. Inject traceparent header into outgoing responses
5. Bind trace_id/span_id to structlog for automatic logging

Learning: Middleware in FastAPI/Starlette runs for every HTTP request before
the route handler executes. This is the perfect place to set up request-scoped
context (trace_id, request_id, etc.).
"""

import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.tracing import (
    TraceContext,
    create_trace_context,
    set_trace_context,
    clear_trace_context,
)

logger = structlog.get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for distributed tracing using W3C Trace Context.

    How It Works:
    ------------
    1. Request arrives → Check for 'traceparent' header
    2. If present → Parse and continue trace with new span
    3. If absent → Start new trace
    4. Set trace context in contextvars (makes it available to all async code)
    5. Bind to structlog (all logs automatically include trace_id/span_id)
    6. Call next middleware/route handler
    7. Add traceparent to response headers (for client visibility)
    8. Clean up context

    Learning: BaseHTTPMiddleware provides dispatch() method that wraps each request.
    We can modify the request before it reaches the handler and modify the response
    before it's sent to the client.

    Call Graph:
    ----------
    Client → TracingMiddleware → LoggingMiddleware → Route Handler
                    ↓ (sets trace context)
                    ↓ (all subsequent code sees trace_id)
                    ↓
            Route Handler logs → automatically include trace_id
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """
        Process each HTTP request to extract/generate trace context.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in the chain

        Returns:
            HTTP response with traceparent header added

        Learning: This method is called for EVERY request. Order of middleware
        registration matters! TracingMiddleware should be registered BEFORE
        LoggingMiddleware so trace_id is available when logging the request.
        """

        # Step 1: Extract or Generate Trace Context
        # ==========================================

        # Check for W3C traceparent header
        traceparent_header = request.headers.get("traceparent")

        trace_context: TraceContext

        if traceparent_header:
            # Continue existing trace from upstream service
            # Learning: If another service called us, they sent traceparent.
            # We parse it to extract trace_id and their span_id (our parent).
            parsed_context = TraceContext.from_traceparent_header(traceparent_header)

            if parsed_context:
                trace_context = parsed_context
                logger.debug(
                    "trace_context_extracted",
                    **{"trace.id": trace_context.trace_id},
                    parent_span_id=trace_context.parent_span_id,
                    **{"span.id": trace_context.span_id},
                )
            else:
                # Malformed header, start new trace
                trace_context = create_trace_context()
                logger.warning(
                    "trace_context_invalid_header",
                    traceparent=traceparent_header,
                    **{"trace.id": trace_context.trace_id},
                )
        else:
            # No traceparent header, start new trace
            # Learning: This is the root span (entry point to distributed trace).
            # Common for:
            # - Direct browser requests
            # - External API calls not using traceparent
            # - First service in the call chain
            trace_context = create_trace_context()
            logger.debug(
                "trace_context_generated",
                **{"trace.id": trace_context.trace_id},
                **{"span.id": trace_context.span_id},
            )

        # Step 2: Generate Request ID
        # ============================
        # Request ID is different from trace_id:
        # - trace_id: Spans multiple services, same for entire user action
        # - request_id: Unique to THIS HTTP request only
        #
        # Why both?
        # - trace_id: "Find all logs for this user action across all services"
        # - request_id: "Find all logs for this specific HTTP request"
        #
        # Example: User action triggers 3 retries to your service
        # - Same trace_id for all 3 requests
        # - Different request_id for each retry
        request_id = str(uuid.uuid4())

        # Step 3: Set Trace Context in ContextVars
        # =========================================
        # This makes trace_id/span_id available to all async code without
        # manually passing them through function calls.
        set_trace_context(trace_context)

        # Step 4: Bind to Structlog
        # ==========================
        # structlog's contextvars processor will automatically include these
        # in every log entry for this request.
        #
        # Learning: bind_contextvars() adds data to the context that persists
        # for all log calls. We don't need to pass trace_id to every logger.info()!
        # Using ECS (Elastic Common Schema) field names for Elasticsearch compatibility
        structlog.contextvars.bind_contextvars(
            **{"trace.id": trace_context.trace_id},
            **{"span.id": trace_context.span_id},
            parent_span_id=trace_context.parent_span_id,
            request_id=request_id,
        )

        # Step 5: Call Next Middleware/Handler
        # =====================================
        try:
            response = await call_next(request)

            # Step 6: Add Trace Context to Response Headers
            # ==============================================
            # Why expose trace_id to clients?
            # 1. API consumers can log it for support requests
            # 2. Frontend can display it in error UI ("Report this ID: abc123...")
            # 3. Enables correlation between client logs and server logs
            #
            # Security consideration: trace_id doesn't leak sensitive data,
            # it's just a random UUID. Safe to expose publicly.
            response.headers["X-Trace-Id"] = trace_context.trace_id
            response.headers["X-Request-Id"] = request_id

            # Also include full traceparent for W3C compliance
            # (useful if response triggers client-side requests)
            response.headers["traceparent"] = trace_context.to_traceparent_header()

            return response

        finally:
            # Step 7: Cleanup
            # ===============
            # Clear contextvars to prevent leakage between requests.
            #
            # Learning: In theory, contextvars are automatically isolated per request.
            # However, explicit cleanup is a defensive practice and helps with testing.
            structlog.contextvars.clear_contextvars()
            clear_trace_context()


# Dependency for Route Handlers
# =============================
# If you want to access trace context in a route handler, use this dependency.


def get_current_trace_context() -> TraceContext | None:
    """
    FastAPI dependency to get current trace context.

    Usage in route handler:
        @app.get("/orders")
        async def get_orders(
            trace_ctx: TraceContext | None = Depends(get_current_trace_context)
        ):
            if trace_ctx:
                # Make outgoing HTTP call with traceparent
                headers = {"traceparent": trace_ctx.to_traceparent_header()}
                await httpx.get("http://other-service/api", headers=headers)

    Learning: Dependencies in FastAPI are called for each request and can
    access request-scoped data (like contextvars).
    """
    from app.core.tracing import get_trace_context

    return get_trace_context()
