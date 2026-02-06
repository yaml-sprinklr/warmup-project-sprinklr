"""Kafka producer and consumer for event streaming"""

import json
import logging
import time
import asyncio
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.metrics import (
    kafka_events_published_total,
    kafka_events_consumed_total,
    kafka_publish_duration_seconds,
    kafka_consumer_lag_messages,
)

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

        start_time = time.time()
        try:
            await self.producer.send_and_wait(topic, value=event, key=key)
            duration = time.time() - start_time
            
            # Track successful publish
            kafka_events_published_total.labels(
                topic=topic, event_type=event_type, status="success"
            ).inc()
            kafka_publish_duration_seconds.labels(
                topic=topic, event_type=event_type
            ).observe(duration)
            
            logger.info(f"Published {event_type} to {topic} (event_id={event_id})")
            return event_id
        except KafkaError as e:
            # Track failed publish
            kafka_events_published_total.labels(
                topic=topic, event_type=event_type, status="failure"
            ).inc()
            logger.error(f"Failed to publish to {topic}: {e}")
            raise


class KafkaConsumerClient:
    """Async Kafka consumer"""

    def __init__(self, topics: list[str]):
        self.topics = topics
        self.consumer: AIOKafkaConsumer | None = None
        self._lag_task: asyncio.Task | None = None

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
            
            # Start lag tracking background task
            self._lag_task = asyncio.create_task(self._track_consumer_lag())
            
            logger.info(f"Kafka consumer started for topics: {self.topics}")
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise

    async def stop(self):
        """Stop Kafka consumer"""
        if self._lag_task and not self._lag_task.done():
            self._lag_task.cancel()
            try:
                await self._lag_task
            except asyncio.CancelledError:
                pass
        
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
    
    async def _track_consumer_lag(self):
        """Background task to track consumer lag"""
        while True:
            try:
                if self.consumer:
                    # Get assigned partitions
                    assigned = self.consumer.assignment()
                    
                    for tp in assigned:
                        try:
                            # Get current position (committed offset)
                            committed = await self.consumer.committed(tp)
                            if committed is None:
                                committed = 0
                            
                            # Get high water mark (latest offset)
                            highwater = await self.consumer.highwater(tp)
                            
                            # Calculate lag
                            lag = highwater - committed
                            
                            # Update metric
                            kafka_consumer_lag_messages.labels(
                                topic=tp.topic,
                                consumer_group=settings.KAFKA_CONSUMER_GROUP_ID
                            ).set(lag)
                        except Exception as e:
                            logger.debug(f"Error tracking lag for {tp}: {e}")
                
                # Update every 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in lag tracking: {e}")
                await asyncio.sleep(30)


# Global Kafka instances
kafka_producer = KafkaProducerClient()
kafka_consumer = KafkaConsumerClient(
    [
        settings.KAFKA_TOPIC_USER_CREATED,
        settings.KAFKA_TOPIC_USER_UPDATED,
        settings.KAFKA_TOPIC_USER_DELETED,
    ]
)
