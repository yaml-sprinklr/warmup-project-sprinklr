import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from app.core.config import settings
from app.core.redis import redis_client
from app.core.kafka import kafka_producer, kafka_consumer

# from app.core.metrics import registry
from app.api.main import api_router
from app.consumers import start_consumer
from app.processors import start_order_processor

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

        consumer_task = asyncio.create_task(start_consumer(), name="kafka-consumer")
        processor_task = asyncio.create_task(
            start_order_processor(), name="order-processor"
        )

        logger.info("All services started")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
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

        if processor_task and not processor_task.done():
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass

        await kafka_consumer.stop()
        await kafka_producer.stop()
        await redis_client.disconnect()

        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_STR)


# @app.get("/metrics")
# async def metrics():
#     """Prometheus metrics endpoint"""
# return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

