"""
Prometheus metrics definitions for the Order Service

This module centralizes all metric definitions to ensure consistency
and avoid duplicate metric registration errors.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# Create a custom registry (optional - can use default REGISTRY)
registry = CollectorRegistry()

# =============================================================================
# HTTP API METRICS
# =============================================================================

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests by method, endpoint, and status code group",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
    registry=registry,
)

# =============================================================================
# DATABASE METRICS
# =============================================================================

# Connection Pool Metrics
db_pool_in_use = Gauge(
    "db_pool_in_use",
    "Number of database connections currently in use",
    registry=registry,
)

db_pool_available = Gauge(
    "db_pool_available",
    "Number of idle database connections available",
    registry=registry,
)

db_pool_waiters = Gauge(
    "db_pool_waiters",
    "Number of threads waiting for a database connection",
    registry=registry,
)

db_pool_wait_seconds = Histogram(
    "db_pool_wait_seconds",
    "Time spent waiting for a database connection",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

# Query Metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query execution time in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=registry,
)

db_queries_total = Counter(
    "db_queries_total",
    "Total number of database queries by operation type",
    ["operation"],
    registry=registry,
)

db_query_errors_total = Counter(
    "db_query_errors_total",
    "Total number of database query errors by type",
    ["error_type"],
    registry=registry,
)

# =============================================================================
# REDIS METRICS
# =============================================================================

redis_commands_total = Counter(
    "redis_commands_total",
    "Total Redis commands executed by command type",
    ["command"],
    registry=registry,
)

redis_command_duration_seconds = Histogram(
    "redis_command_duration_seconds",
    "Redis command execution time in seconds",
    ["command"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    registry=registry,
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    registry=registry,
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    registry=registry,
)

redis_errors_total = Counter(
    "redis_errors_total",
    "Total Redis errors by type",
    ["error_type"],
    registry=registry,
)

# =============================================================================
# USER VALIDATION METRICS
# =============================================================================

user_validation_total = Counter(
    "user_validation_total",
    "Total user validation attempts by result",
    ["result"],  # cache_hit, cache_miss, not_found, inactive, error
    registry=registry,
)

user_validation_duration_seconds = Histogram(
    "user_validation_duration_seconds",
    "User validation latency in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

user_service_api_calls_total = Counter(
    "user_service_api_calls_total",
    "Total calls to User Service API",
    ["status"],  # success, not_found, failure, timeout
    registry=registry,
)

# =============================================================================
# KAFKA EVENT METRICS
# =============================================================================

kafka_events_published_total = Counter(
    "kafka_events_published_total",
    "Total events published to Kafka",
    ["topic", "event_type", "status"],
    registry=registry,
)

kafka_events_consumed_total = Counter(
    "kafka_events_consumed_total",
    "Total events consumed from Kafka",
    ["topic", "event_type", "status"],
    registry=registry,
)

kafka_publish_duration_seconds = Histogram(
    "kafka_publish_duration_seconds",
    "Time taken to publish events to Kafka",
    ["topic", "event_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=registry,
)

kafka_consumer_lag_messages = Gauge(
    "kafka_consumer_lag_messages",
    "Number of messages the consumer is lagging behind",
    ["topic", "consumer_group"],
    registry=registry,
)

kafka_events_duplicate_total = Counter(
    "kafka_events_duplicate_total",
    "Total duplicate events detected (idempotency check)",
    ["topic", "event_type"],
    registry=registry,
)

# =============================================================================
# OUTBOX PATTERN METRICS
# =============================================================================

outbox_events_pending = Gauge(
    "outbox_events_pending",
    "Number of unpublished events in the outbox table",
    registry=registry,
)

outbox_events_processed_total = Counter(
    "outbox_events_processed_total",
    "Total outbox events processed",
    ["status"],
    registry=registry,
)

outbox_publish_duration_seconds = Histogram(
    "outbox_publish_duration_seconds",
    "Time taken to publish events from outbox to Kafka",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=registry,
)

outbox_retry_attempts_total = Counter(
    "outbox_retry_attempts_total",
    "Total number of retry attempts for failed outbox events",
    ["event_type"],
    registry=registry,
)

# =============================================================================
# BACKGROUND TASK METRICS
# =============================================================================

background_tasks_running = Gauge(
    "background_tasks_running",
    "Number of background tasks currently running",
    ["task_name"],
    registry=registry,
)

background_task_errors_total = Counter(
    "background_task_errors_total",
    "Total errors in background tasks",
    ["task_name", "error_type"],
    registry=registry,
)
