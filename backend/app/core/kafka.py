"""Kafka producer and consumer for event streaming"""

import json
import logging
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


class KafkaProducerClient:
    """Async Kafka producer"""

    def __init__(self):
        self.producer: AIOKafkaProducer | None = None

    async def start(self):
        """Start Kafka producer"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",  # Wait for all replicas
                compression_type="gzip",
                request_timeout_ms=30000,
            )
            await self.producer.start()
            logger.info(f"Kafka producer started: {settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise

    async def stop(self):
        """Stop Kafka producer"""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def publish_event(
        self, topic: str, event_type: str, data: dict[str, Any], key: str | None = None
    ) -> str:
        """
        Publish event to Kafka topic

        Args:
            topic: Kafka topic name
            event_type: Type of event (e.g., "order.created")
            data: Event payload
            key: Partition key (usually user_id)

        Returns:
            event_id: Unique event ID
        """
        if not self.producer:
            raise RuntimeError("Kafka producer not started")

        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0",
            "data": data,
        }

        try:
            await self.producer.send_and_wait(topic, value=event, key=key)
            logger.info(f"Published {event_type} to {topic} (event_id={event_id})")
            return event_id
        except KafkaError as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            raise


class KafkaConsumerClient:
    """Async Kafka consumer"""

    def __init__(self, topics: list[str]):
        self.topics = topics
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self):
        """Start Kafka consumer"""
        try:
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.KAFKA_CONSUMER_GROUP_ID,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",  # Start from beginning if no offset
                enable_auto_commit=False,  # Manual commit for at-least-once
                max_poll_records=100,
                session_timeout_ms=30000,
                max_poll_interval_ms=300000,  # 5 minutes
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer started for topics: {self.topics}")
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise

    async def stop(self):
        """Stop Kafka consumer"""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume_messages(self):
        """Async generator yielding messages"""
        if not self.consumer:
            raise RuntimeError("Kafka consumer not started")

        async for message in self.consumer:
            yield message

    async def commit(self):
        """Commit current offset"""
        if self.consumer:
            await self.consumer.commit()


# Global Kafka instances
kafka_producer = KafkaProducerClient()
kafka_consumer = KafkaConsumerClient(
    [
        settings.KAFKA_TOPIC_USER_CREATED,
        settings.KAFKA_TOPIC_USER_UPDATED,
        settings.KAFKA_TOPIC_USER_DELETED,
    ]
)
