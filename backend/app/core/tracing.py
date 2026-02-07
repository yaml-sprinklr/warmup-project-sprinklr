"""
Distributed Tracing Context Management

This module implements W3C Trace Context propagation manually to understand
the internals of distributed tracing before using full OpenTelemetry auto-instrumentation.

Key Concepts:
- trace_id: Unique identifier for an entire request flow across all services (128-bit)
- span_id: Unique identifier for a specific operation within a trace (64-bit)
- parent_span_id: Links spans together to form a call hierarchy
- W3C Trace Context: Standard header format for propagating trace context

Learning Resources:
- W3C Trace Context spec: https://www.w3.org/TR/trace-context/
- OpenTelemetry trace spec: https://opentelemetry.io/docs/specs/otel/trace/api/
"""

import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

# Context Variables for Async-Safe Storage
# =========================================
# In async Python, multiple coroutines share the same thread, so thread-locals
# don't work. contextvars provide isolated storage that automatically propagates
# to child async tasks.
#
# Learning: When you await or create_task(), Python automatically copies the
# context to the child task. This is how trace_id "follows" the request through
# all async operations.
#
# Using ECS (Elastic Common Schema) field names with dot notation for better
# compatibility with Elasticsearch and other observability tools.

trace_id_var: ContextVar[Optional[str]] = ContextVar("trace.id", default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar("span.id", default=None)
parent_span_id_var: ContextVar[Optional[str]] = ContextVar(
    "parent_span_id", default=None
)


@dataclass
class TraceContext:
    """
    Represents W3C Trace Context information.

    W3C Trace Context Format (traceparent header):
    ----------------------------------------------
    00-{trace_id}-{parent_span_id}-{trace_flags}

    Components:
    - version: Always "00" (current spec version)
    - trace_id: 32 hex chars (128 bits) - uniquely identifies the entire trace
    - parent_span_id: 16 hex chars (64 bits) - identifies the calling span
    - trace_flags: 2 hex chars (8 bits) - sampling and other flags
      - 01 = sampled (record this trace)
      - 00 = not sampled (don't record, but propagate ID)

    Example:
    traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

    Learning: This format is standardized so all services (regardless of language/framework)
    can propagate traces. If service A (Python) calls service B (Go), the trace continues.
    """

    trace_id: str  # 32 hex characters (128 bits)
    span_id: str  # 16 hex characters (64 bits)
    parent_span_id: Optional[str] = None  # 16 hex characters (64 bits)
    sampled: bool = True  # Whether to record this trace
    version: str = "00"  # W3C Trace Context version

    def to_traceparent_header(self) -> str:
        """
        Format as W3C traceparent header value.

        Returns:
            String like "00-{trace_id}-{span_id}-01"

        Learning: The third position uses span_id, not parent_span_id!
        This is because the header represents the CURRENT span's context.
        When service B receives this header, span_id becomes its parent_span_id.
        """
        trace_flags = "01" if self.sampled else "00"
        return f"{self.version}-{self.trace_id}-{self.span_id}-{trace_flags}"

    @classmethod
    def from_traceparent_header(cls, header_value: str) -> Optional["TraceContext"]:
        """
        Parse W3C traceparent header into TraceContext.

        Args:
            header_value: String like "00-{trace_id}-{span_id}-{flags}"

        Returns:
            TraceContext object, or None if invalid format

        Learning: Robust parsing is critical. Malformed headers from external
        services shouldn't crash your service. Validate lengths and format.

        Validation Rules:
        - Must have exactly 4 parts separated by '-'
        - trace_id must be 32 hex chars (not all zeros)
        - span_id must be 16 hex chars (not all zeros)
        - version must be "00" (reject future versions we don't understand)
        """
        try:
            parts = header_value.split("-")
            if len(parts) != 4:
                return None

            version, trace_id, parent_span_id_from_header, trace_flags = parts

            # Validate version (must be 00)
            if version != "00":
                return None

            # Validate trace_id length and format
            if len(trace_id) != 32 or trace_id == "0" * 32:
                return None

            # Validate span_id length and format
            if (
                len(parent_span_id_from_header) != 16
                or parent_span_id_from_header == "0" * 16
            ):
                return None

            # Check if hex
            int(trace_id, 16)
            int(parent_span_id_from_header, 16)

            # Parse sampled flag (bit 0 of trace_flags)
            sampled = (int(trace_flags, 16) & 0x01) == 0x01

            # Generate new span_id for this service's span
            # Learning: We inherit trace_id, but create a NEW span_id because
            # this is a new operation (span) in the distributed trace
            new_span_id = generate_span_id()

            return cls(
                version=version,
                trace_id=trace_id,
                span_id=new_span_id,
                parent_span_id=parent_span_id_from_header,  # The span_id from the header
                sampled=sampled,
            )

        except (ValueError, AttributeError):
            # Malformed header, return None
            return None


def generate_trace_id() -> str:
    """
    Generate a new 128-bit trace ID as 32 hex characters.

    Learning: Why 128 bits?
    - Ensures global uniqueness across all services/time without coordination
    - At 1 billion traces/second, 50% collision probability after 5 billion years
    - Uses cryptographically secure random (secrets module, not random module)

    Format:
        32 hex characters (128 bits)
        Example: "4bf92f3577b34da6a3ce929d0e0e4736"

    Why secrets.token_bytes() instead of random.randint()?
    - secrets is cryptographically secure (uses OS entropy)
    - random is pseudo-random (predictable, insecure)
    - For distributed systems, unpredictability prevents ID guessing attacks
    """
    return secrets.token_bytes(16).hex()  # 16 bytes = 128 bits = 32 hex chars


def generate_span_id() -> str:
    """
    Generate a new 64-bit span ID as 16 hex characters.

    Learning: Why 64 bits (not 128 like trace_id)?
    - Span IDs only need to be unique within a single trace
    - With trace_id providing namespace, 64 bits is sufficient
    - Smaller size = less overhead in headers/storage

    Format:
        16 hex characters (64 bits)
        Example: "00f067aa0ba902b7"
    """
    return secrets.token_bytes(8).hex()  # 8 bytes = 64 bits = 16 hex chars


def create_trace_context(
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    sampled: bool = True,
) -> TraceContext:
    """
    Create a new trace context, generating IDs as needed.

    Args:
        trace_id: Existing trace ID to continue, or None to start new trace
        parent_span_id: Parent span ID, or None if this is the root span
        sampled: Whether to record this trace

    Returns:
        TraceContext with trace_id, new span_id, and optional parent_span_id

    Learning: This function handles two scenarios:
    1. Starting a new trace (trace_id=None): Generate both trace_id and span_id
    2. Continuing a trace (trace_id provided): Keep trace_id, generate new span_id

    Usage:
        # Start new trace
        ctx = create_trace_context()

        # Continue existing trace
        ctx = create_trace_context(trace_id="abc123...", parent_span_id="def456...")
    """
    return TraceContext(
        trace_id=trace_id or generate_trace_id(),
        span_id=generate_span_id(),
        parent_span_id=parent_span_id,
        sampled=sampled,
    )


def set_trace_context(context: TraceContext) -> None:
    """
    Store trace context in contextvars for automatic inclusion in logs.

    Learning: By setting these ContextVar values, structlog's merge_contextvars
    processor will automatically include trace_id and span_id in every log entry.

    This means you never have to manually pass trace_id to logging calls:

        set_trace_context(context)
        logger.info("order_created", order_id=order.id)
        # Log automatically includes trace_id and span_id!

    Args:
        context: TraceContext to set as current
    """
    trace_id_var.set(context.trace_id)
    span_id_var.set(context.span_id)
    if context.parent_span_id:
        parent_span_id_var.set(context.parent_span_id)


def get_trace_context() -> Optional[TraceContext]:
    """
    Retrieve the current trace context from contextvars.

    Returns:
        TraceContext if set, None otherwise

    Learning: This is safe to call from any async function because contextvars
    are automatically isolated per request. Multiple concurrent requests won't
    interfere with each other.

    Usage:
        context = get_trace_context()
        if context:
            # Include in outgoing HTTP requests
            headers["traceparent"] = context.to_traceparent_header()
    """
    trace_id = trace_id_var.get()
    if not trace_id:
        return None

    return TraceContext(
        trace_id=trace_id,
        span_id=span_id_var.get() or generate_span_id(),
        parent_span_id=parent_span_id_var.get(),
    )


def clear_trace_context() -> None:
    """
    Clear trace context from contextvars.

    Learning: Normally not needed because contextvars are automatically isolated
    per request. However, useful for:
    - Testing (clean state between tests)
    - Background workers that process multiple items (clean between items)
    """
    trace_id_var.set(None)
    span_id_var.set(None)
    parent_span_id_var.set(None)


def format_trace_id_for_sql_comment(trace_id: str, span_id: str) -> str:
    """
    Format trace context as SQL comment for database query correlation.

    Returns a SQL comment that can be appended to queries:
        /* traceparent='00-{trace_id}-{span_id}-01' */

    Learning: PostgreSQL logs can include SQL comments. By adding trace context
    to queries, you can correlate slow query logs with application traces.

    Example:
        SELECT * FROM orders WHERE id = 'ord_123'
        /* traceparent='00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' */

    In PostgreSQL logs:
        2025-02-07 14:23:45.123 UTC [12345] LOG: duration: 1234.567 ms
        statement: SELECT * FROM orders WHERE id = 'ord_123'
        /* traceparent='00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' */

    Now you can search Elasticsearch for the trace_id to find both application
    logs AND database slow query logs!
    """
    return f"/* traceparent='00-{trace_id}-{span_id}-01' */"


# Kafka Header Helpers
# ====================
# Kafka headers are binary key-value pairs. We need to encode/decode trace context.


def inject_trace_context_to_kafka_headers(
    headers: list[tuple[str, bytes]] | None = None,
) -> list[tuple[str, bytes]]:
    """
    Inject current trace context into Kafka message headers.

    Args:
        headers: Existing headers list, or None to create new list

    Returns:
        Headers list with traceparent header added

    Learning: Kafka headers are list of (key: str, value: bytes) tuples.
    We encode the W3C traceparent header for propagation across Kafka.

    Usage:
        headers = inject_trace_context_to_kafka_headers()
        producer.send("topic", value=data, headers=headers)
    """
    if headers is None:
        headers = []

    context = get_trace_context()
    if context:
        # Encode traceparent header as bytes
        traceparent = context.to_traceparent_header()
        headers.append(("traceparent", traceparent.encode("utf-8")))

    return headers


def extract_trace_context_from_kafka_headers(
    headers: list[tuple[str, bytes]] | None,
) -> Optional[TraceContext]:
    """
    Extract trace context from Kafka message headers.

    Args:
        headers: Kafka message headers as list of (key, value) tuples

    Returns:
        TraceContext if traceparent header found, None otherwise

    Learning: When consuming Kafka messages, extract trace context and set it
    so all subsequent logs include the trace_id. This continues the trace from
    the producer.

    Usage:
        for message in consumer:
            context = extract_trace_context_from_kafka_headers(message.headers)
            if context:
                set_trace_context(context)
            process_message(message)
    """
    if not headers:
        return None

    for key, value in headers:
        if key == "traceparent":
            header_value = value.decode("utf-8")
            return TraceContext.from_traceparent_header(header_value)

    return None
