from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Order Service"
    API_V1_STR: str = "/api/v1"

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    # Redis Configuration (NEW)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Redis Cache TTLs (seconds)
    USER_CACHE_TTL: int = 86400  # 24 hours
    PROCESSED_EVENT_TTL: int = 604800  # 7 days

    # Kafka Configuration (NEW)
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_ID: str = "order-service"

    # Kafka Topics
    KAFKA_TOPIC_ORDER_CREATED: str = "order.created"
    KAFKA_TOPIC_ORDER_CONFIRMED: str = "order.confirmed"
    KAFKA_TOPIC_ORDER_SHIPPED: str = "order.shipped"
    KAFKA_TOPIC_ORDER_CANCELLED: str = "order.cancelled"
    KAFKA_TOPIC_USER_CREATED: str = "user.created"
    KAFKA_TOPIC_USER_UPDATED: str = "user.updated"
    KAFKA_TOPIC_USER_DELETED: str = "user.deleted"

    # External Services
    USER_SERVICE_URL: str = "http://localhost:8001"

    # Metrics Configuration
    ENABLE_METRICS: bool = True

    # Order Processor Configuration (seconds)
    ORDER_CONFIRM_DELAY: int = 30  # Time before auto-confirming pending orders
    ORDER_SHIP_DELAY: int = 120  # Time before auto-shipping confirmed orders (2 minutes)
    ORDER_PROCESSOR_INTERVAL: int = 10  # How often processor checks for orders

    # Mock User Producer Configuration (seconds)
    MOCK_USER_CREATE_INTERVAL: int = 10  # Create user every N seconds
    MOCK_USER_UPDATE_INTERVAL: int = 15  # Update user every N seconds
    MOCK_USER_DELETE_INTERVAL: int = 30  # Delete user every N seconds
    MOCK_USER_MAX_USERS: int = 50  # Maximum active users

    # Outbox Worker Configuration
    OUTBOX_BATCH_SIZE: int = 100  # Maximum events to process per batch
    OUTBOX_POLL_INTERVAL_SECONDS: int = 1  # How often to check for new events
    OUTBOX_ERROR_BACKOFF_SECONDS: int = 5  # Sleep duration after errors
    OUTBOX_MAX_RETRY_ATTEMPTS: int = 5  # Max attempts before flagging for manual intervention
    OUTBOX_ERROR_MESSAGE_MAX_LENGTH: int = 500  # Max characters to store in last_error field

    # Logging Configuration
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "json"  # json or console (console for dev, json for prod)
    ENVIRONMENT: str = "development"  # development, staging, production
    SERVICE_NAME: str = "order-service"
    SERVICE_VERSION: str = "v1.0.0"  # Deployment version (override with git SHA in prod)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        """Construct Redis connection URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()  # type: ignore
