"""
Structured Logging Configuration with structlog

This module configures the application's logging system using structlog,
which provides structured logging with context binding and flexible output formats.

Key Concepts:
- Processor Pipeline: Each log entry passes through a series of processors that
  transform, enrich, and format the log data
- Context Variables: Use contextvars to automatically include request-scoped data
  (trace_id, user_id) in all logs without manual passing
- Dual Output: Console-friendly format for development, JSON for production
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_service_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor: Add service-level metadata to every log entry.

    This ensures every log has identifying information about which service,
    environment, and version emitted it. Critical for multi-service debugging.

    Learning: Processors receive the event_dict and can modify it before the next
    processor runs. Order matters in the processor pipeline!
    """
    event_dict["service_name"] = settings.SERVICE_NAME
    event_dict["environment"] = settings.ENVIRONMENT
    event_dict["version"] = settings.SERVICE_VERSION
    return event_dict


def add_log_level(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor: Normalize log level to uppercase.

    Ensures consistency across all logs (ERROR not error, INFO not info).
    This makes Kibana queries case-insensitive and easier to write.

    Learning: structlog's add_log_level processor does this automatically,
    but we're implementing it manually to understand the mechanism.
    """
    if method_name:
        event_dict["level"] = method_name.upper()
    return event_dict


def rename_event_key(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor: Rename 'event' to 'message' for ELK compatibility.

    structlog uses 'event' as the key for log messages, but Elasticsearch
    and many log aggregators expect 'message'. This processor handles the rename.

    Learning: Field naming conventions matter for cross-tool compatibility.
    Kibana dashboards often assume 'message' exists.
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def drop_color_message_key(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor: Remove console-specific formatting keys before JSON rendering.

    When switching from console to JSON output, structlog may leave behind
    color formatting keys. This processor cleans them up.

    Learning: Different renderers expect different keys. Processors can clean up
    artifacts from previous processors.
    """
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """
    Configure the application's logging system with structlog.

    This function sets up:
    1. Python's standard logging to route to stdout
    2. structlog's processor pipeline
    3. Output format (console for dev, JSON for prod)
    4. Context variables integration for trace_id/span_id

    Call this ONCE at application startup.
    """

    # Step 1: Configure Python's standard logging
    # ============================================
    # structlog integrates with Python's logging module. We configure it to:
    # - Write to stdout (12-factor app principle)
    # - Use minimal formatting (structlog handles the formatting)
    # - Set log level from environment variable

    logging.basicConfig(
        format="%(message)s",  # structlog will format, so we use plain message
        stream=sys.stdout,  # 12-factor: always stdout, never files
        level=getattr(logging, settings.LOG_LEVEL.upper()),
    )

    # Disable uvicorn access logs (plain text, redundant with LoggingMiddleware)
    # Learning: uvicorn has its own access logger that outputs unstructured lines like:
    #   INFO 10.42.0.1:48500 - "GET /api/v1/health/live HTTP/1.1" 200
    # Our LoggingMiddleware already logs HTTP requests as structured JSON with
    # trace_id, duration_ms, etc. — so these are just noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Silence aiokafka's verbose consumer group logs
    # Learning: aiokafka logs every rebalance, partition assignment, and heartbeat
    # in plain text format. This clutters structured logs. We only want errors.
    logging.getLogger("aiokafka").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.consumer.group_coordinator").setLevel(logging.WARNING)

    # Step 2: Define the Processor Pipeline
    # ======================================
    # Each processor transforms the log event_dict in sequence.
    # Order is critical! Think of it as a Unix pipeline: log | proc1 | proc2 | ...

    shared_processors: list[Processor] = [
        # Merge contextvars (trace_id, span_id) into every log automatically
        # Learning: contextvars.ContextVar values are automatically included
        # without manual passing through function calls
        structlog.contextvars.merge_contextvars,
        # Add service metadata (service_name, environment, version)
        add_service_context,
        # Add timestamp in ISO 8601 format with UTC timezone
        # Learning: ISO 8601 is the standard for distributed systems because it's
        # unambiguous and sortable. "2025-02-07T14:23:45.123456Z"
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add log level (INFO, ERROR, etc.)
        add_log_level,
        # If an exception is logged, format the traceback
        # Learning: This captures the full stack trace and includes it in the
        # log output as 'exception' field
        structlog.processors.format_exc_info,
        # Rename 'event' key to 'message' for ELK compatibility
        rename_event_key,
        # Remove ANSI color codes if present (from console renderer)
        drop_color_message_key,
    ]

    # Step 3: Choose Renderer Based on Environment
    # =============================================
    # Development: Human-readable console output with colors
    # Production: Machine-readable JSON for Filebeat -> Elasticsearch

    if settings.LOG_FORMAT == "console":
        # Development mode: colorized, padded, human-friendly
        # Learning: ConsoleRenderer makes logs readable during local development
        # Example output:
        # 2025-02-07 14:23:45 [info     ] order_created    order_id=ord_123 user_id=usr_456
        renderer: Processor = structlog.dev.ConsoleRenderer(
            colors=True,  # ANSI color codes
            exception_formatter=structlog.dev.plain_traceback,  # Format exceptions nicely
        )
    else:
        # Production mode: JSON output for structured logging pipelines
        # Learning: JSONRenderer creates one JSON object per line (NDJSON format)
        # Filebeat parses this automatically with json.keys_under_root: true
        #
        # We use orjson for serialization (10x faster than stdlib json)
        import orjson

        def orjson_dumps(obj: Any, **kwargs: Any) -> str:
            """
            Serialize using orjson (fast C extension).

            Learning: At high throughput, JSON serialization becomes a bottleneck.
            orjson is 10x faster than stdlib json.dumps():
            - Standard json: ~50-100 µs per log
            - orjson: ~5-10 µs per log

            For 10,000 logs/second, this saves ~500ms of CPU time.
            """
            return orjson.dumps(obj).decode("utf-8")

        renderer = structlog.processors.JSONRenderer(serializer=orjson_dumps)

    # Step 4: Configure structlog
    # ============================
    # This is the main configuration that ties everything together

    structlog.configure(
        # Processor pipeline: shared processors + renderer
        processors=shared_processors + [renderer],
        # Use Python's logging module as the final output destination
        # Learning: structlog generates the log entry, logging module writes to stdout
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Cache logger instances for performance
        # Learning: Logger creation has overhead. Caching means we create once per module.
        cache_logger_on_first_use=True,
        # Wrapper class for the logger
        # Learning: BoundLogger supports method chaining like logger.bind(user_id=123)
        wrapper_class=structlog.stdlib.BoundLogger,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("order_created", order_id=order.id, user_id=user.id)

    Learning: Unlike print() or f-strings, structured logging separates the
    event name from the data. This makes logs machine-parseable:

    BAD:  logger.info(f"Created order {order_id} for user {user_id}")
    GOOD: logger.info("order_created", order_id=order_id, user_id=user_id)

    The GOOD approach lets you query Kibana: message:"order_created" AND user_id:"usr_123"
    """
    return structlog.get_logger(name)
