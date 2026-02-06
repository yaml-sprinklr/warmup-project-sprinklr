import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from app.core.config import settings
from app.core.redis import redis_client
from app.core.kafka import kafka_producer, kafka_consumer
from app.core.metrics import registry, background_tasks_running, background_task_errors_total
from app.api.main import api_router
from app.consumers import start_consumer
from app.processors import start_order_processor
from app.middleware.metrics_middleware import MetricsMiddleware

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    consumer_task = None
    processor_task = None

    logger.info("Starting Order Service...")

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

        logger.info("All services started")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        background_task_errors_total.labels(
            task_name="startup", error_type="startup_error"
        ).inc()
        raise

    yield

    logger.info("Shutting down Order Service...")

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

        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


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
                    logger.error(f"Background task {task_name} failed: {e}", exc_info=True)
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
    logger.debug("Serving metrics endpoint")
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


# Add metrics middleware
app.add_middleware(MetricsMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
