import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from app.core.config import settings
from app.core.redis import redis_client
from app.core.kafka import kafka_producer, kafka_consumer
from app.core.metrics import (
    registry,
    background_tasks_running,
    background_task_errors_total,
)
from app.api.main import api_router
from app.consumers import start_consumer
from app.processors import start_order_processor
from app.middleware.metrics_middleware import MetricsMiddleware
from app.middleware.tracing_middleware import TracingMiddleware
from app.middleware.logging_middleware import LoggingMiddleware

# Configure structured logging with structlog
# Learning: This must be called BEFORE any logger.get_logger() calls
# to ensure all loggers use the structlog configuration
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    consumer_task = None
    processor_task = None

    logger.info("application_starting", service=settings.SERVICE_NAME, environment=settings.ENVIRONMENT)

    try:
        await redis_client.connect()
        await kafka_producer.start()
        await kafka_consumer.start()

        # Start background tasks
        consumer_task = asyncio.create_task(start_consumer(), name="kafka-consumer")
        processor_task = asyncio.create_task(
            start_order_processor(), name="order-processor"
        )

        # Track background tasks
        background_tasks_running.labels(task_name="kafka-consumer").set(1)
        background_tasks_running.labels(task_name="order-processor").set(1)

        # Monitor task health
        asyncio.create_task(monitor_background_tasks(consumer_task, processor_task))

        logger.info("application_started",
                   redis_connected=True,
                   kafka_connected=True,
                   background_tasks=["kafka-consumer", "order-processor"])
    except Exception as e:
        logger.error("application_startup_failed", error_type=type(e).__name__, error_message=str(e), exc_info=True)
        background_task_errors_total.labels(
            task_name="startup", error_type="startup_error"
        ).inc()
        raise

    yield

    logger.info("application_shutting_down")

    try:
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            background_tasks_running.labels(task_name="kafka-consumer").set(0)

        if processor_task and not processor_task.done():
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
            background_tasks_running.labels(task_name="order-processor").set(0)

        await kafka_consumer.stop()
        await kafka_producer.stop()
        await redis_client.disconnect()

        logger.info("application_shutdown_complete")
    except Exception as e:
        logger.error("application_shutdown_error", error_type=type(e).__name__, error_message=str(e), exc_info=True)


async def monitor_background_tasks(*tasks):
    """Monitor background tasks and update metrics on failure"""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds

        for task in tasks:
            if task.done() and not task.cancelled():
                task_name = task.get_name()
                try:
                    # This will raise if task had exception
                    task.result()
                except Exception as e:
                    logger.error(
                        "background_task_failed",
                        task_name=task_name,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        exc_info=True
                    )
                    background_tasks_running.labels(task_name=task_name).set(0)
                    background_task_errors_total.labels(
                        task_name=task_name, error_type=type(e).__name__
                    ).inc()
                break


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    logger.debug("metrics_endpoint_served")
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


# Add middlewares
# ===============
# Learning: Middleware execution order is REVERSE of registration order!
#
# Registration order (below):
#   1. MetricsMiddleware
#   2. LoggingMiddleware
#   3. TracingMiddleware
#
# Execution order (incoming request):
#   TracingMiddleware → LoggingMiddleware → MetricsMiddleware → Route Handler
#
# Why this order?
# 1. TracingMiddleware runs FIRST to set up trace context (trace_id, span_id)
# 2. LoggingMiddleware runs SECOND so it can include trace_id in request logs
# 3. MetricsMiddleware runs THIRD to record metrics
#
# This ensures trace_id is available in all logs and metrics!

app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(TracingMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
