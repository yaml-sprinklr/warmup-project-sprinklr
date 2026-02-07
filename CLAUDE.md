# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an order management microservice built with FastAPI, demonstrating event-driven architecture patterns on Kubernetes. The service manages order lifecycles (pending → confirmed → shipped) with transactional outbox pattern for reliable event publishing to Kafka.

**Tech Stack**: Python 3.14, FastAPI, PostgreSQL, Kafka (Strimzi), Redis, SQLModel, Alembic, uv (package manager), Terraform, Kubernetes, Helm

## Development Commands

### Local Development (Backend)

```bash
# Navigate to backend directory
cd backend/

# Run the FastAPI service (dev mode with hot reload)
uv run fastapi dev --host 0.0.0.0 app/main.py

# Run database migrations
uv run alembic upgrade head

# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Run the outbox worker (separate process)
uv run python -m app.workers.outbox_worker
```

### Docker/Kubernetes

```bash
# Build Docker image (from repository root)
nerdctl --namespace k8s.io build -t order-service:v11 .

# Deploy via Terraform (from terraform/ directory)
cd terraform/
terraform init
terraform plan
terraform apply

# Update image version
terraform apply -var="app_image_tag=v7"

# Access the application
kubectl port-forward -n order-service svc/order-service-rest-api 8080:8000

# View logs
kubectl logs -n order-service -l app=order-service --tail=100

# Check migrations
kubectl logs -n order-service -l component=migrations
```

### Useful Kubernetes Commands

```bash
# Get all resources in order-service namespace
kubectl get all -n order-service

# Port forward to PostgreSQL
kubectl port-forward -n order-service svc/order-service-postgres-postgresql 5432:5432

# Port forward to Kafka (if needed)
kubectl port-forward -n order-service svc/kafka-cluster-kafka-bootstrap 9092:9092

# Restart deployments
kubectl rollout restart deployment/order-service-rest-api -n order-service
```

## Architecture

### High-Level Components

1. **REST API** (`app/main.py`, `app/api/`): FastAPI application handling HTTP requests
2. **Background Processors** (`app/processors/`): Async tasks for order lifecycle automation
3. **Kafka Consumers** (`app/consumers/`): Process events from other services (e.g., user events)
4. **Outbox Worker** (`app/workers/outbox_worker.py`): Separate deployment that publishes events from outbox table to Kafka
5. **Database Layer** (`app/models.py`, `app/core/db.py`): SQLModel models and PostgreSQL connection

### Event-Driven Architecture

The service uses the **Transactional Outbox Pattern** to ensure reliable event publishing:

1. Business logic writes to database AND outbox table in same transaction
2. Outbox worker polls outbox table and publishes events to Kafka
3. This guarantees at-least-once delivery without distributed transactions

**Event Flow**:
- Order created → writes to `orders` + `outbox_events` → outbox worker publishes to `order.created` topic
- Order confirmed → writes to `orders` + `outbox_events` → publishes to `order.confirmed` topic
- Order shipped → writes to `orders` + `outbox_events` → publishes to `order.shipped` topic

### Key Design Patterns

**Outbox Pattern** (`app/services/outbox_service.py`):
- All events go through `OutboxService.create_event()` which writes to `outbox_events` table
- Separate worker process (`app/workers/outbox_worker.py`) publishes events asynchronously
- Row-level locking (`with_for_update(skip_locked=True)`) prevents duplicate processing in multi-replica setups

**Order Lifecycle Automation** (`app/processors/order_processor.py`):
- Background tasks simulate payment processing (pending → confirmed after 30s)
- Simulate fulfillment (confirmed → shipped after 120s)
- Uses row-level locking to prevent race conditions across replicas

**User Cache** (Redis):
- Kafka consumer (`app/consumers/user_consumer.py`) listens to user service events
- Caches user data in Redis for fast lookups
- TTL: 24 hours for user data, 7 days for processed event IDs (idempotency)

### Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app with lifespan management
│   ├── models.py            # SQLModel database models
│   ├── deps.py              # FastAPI dependencies (e.g., DB session)
│   ├── api/                 # REST API routes
│   │   └── routes/order.py  # Order CRUD endpoints
│   ├── core/                # Core infrastructure
│   │   ├── config.py        # Settings (from env vars)
│   │   ├── db.py            # PostgreSQL engine
│   │   ├── kafka.py         # Kafka producer/consumer setup
│   │   ├── redis.py         # Redis client
│   │   └── metrics.py       # Prometheus metrics
│   ├── events/              # Event schemas (Pydantic models)
│   ├── services/            # Business logic services
│   │   └── outbox_service.py
│   ├── processors/          # Background order processors
│   ├── consumers/           # Kafka consumers
│   ├── producers/           # Mock producers for testing
│   ├── workers/             # Standalone worker processes
│   │   └── outbox_worker.py
│   ├── middleware/          # Custom middleware (metrics)
│   └── alembic/             # Database migrations
├── Dockerfile
└── pyproject.toml           # uv dependencies
```

## Configuration

Configuration is managed via environment variables (see `app/core/config.py`):

**Database**:
- `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

**Kafka**:
- `KAFKA_BOOTSTRAP_SERVERS` (default: `localhost:9092`)
- `KAFKA_CONSUMER_GROUP_ID` (default: `order-service`)
- Topic names: `KAFKA_TOPIC_ORDER_CREATED`, etc.

**Redis**:
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
- `USER_CACHE_TTL` (default: 86400s = 24h)

**Order Processing**:
- `ORDER_CONFIRM_DELAY` (default: 30s) - delay before auto-confirming orders
- `ORDER_SHIP_DELAY` (default: 120s) - delay before auto-shipping orders
- `ORDER_PROCESSOR_INTERVAL` (default: 10s) - polling interval

**Outbox Worker**:
- `OUTBOX_BATCH_SIZE` (default: 100)
- `OUTBOX_POLL_INTERVAL_SECONDS` (default: 1)
- `OUTBOX_MAX_RETRY_ATTEMPTS` (default: 5)

## Database Migrations

Alembic is configured to read connection string from `app.core.config.settings`. The `env.py` imports settings directly.

**Workflow**:
1. Modify models in `app/models.py`
2. Generate migration: `uv run alembic revision --autogenerate -m "description"`
3. Review generated migration in `app/alembic/versions/`
4. Apply: `uv run alembic upgrade head`

**In Kubernetes**: Migrations run as a Kubernetes Job before the main deployment starts (see `terraform/main.tf`).

## Kafka Topics

The service uses Strimzi operator with declarative KafkaTopic CRDs managed by Terraform:

- `order.created` - New orders
- `order.confirmed` - Payment confirmed
- `order.shipped` - Order shipped
- `order.cancelled` - Order cancelled
- `user.created`, `user.updated`, `user.deleted` - User service events (consumed)

## Multi-Replica Safety

The application is designed to run multiple replicas safely:

1. **Outbox worker**: Uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent duplicate event publishing
2. **Order processor**: Uses same row-level locking for order state transitions
3. **Kafka consumers**: Consumer group ensures each message goes to one consumer
4. **Redis idempotency**: Event IDs tracked in Redis to prevent duplicate processing

## Monitoring

Prometheus metrics exposed at `/metrics`:
- HTTP request metrics (via middleware)
- Background task status (`background_tasks_running`)
- Outbox processing metrics (`outbox_events_processed_total`, `outbox_events_pending`)
- Kafka consumer/producer metrics

Grafana dashboards configured in `terraform/grafana/`.

## Testing the API

HTTPie examples in `backend/httpie/`:

```bash
# Create an order
http POST :8080/api/v1/orders user_id=user123 total_amount=99.99 currency=USD items:='[{"product_id":"prod1","quantity":2,"price":49.99}]'

# Get all orders
http GET :8080/api/v1/orders

# Check metrics
http GET :8080/metrics
```

## Important Notes

- The service runs two types of background tasks in the FastAPI process: Kafka consumer and order processor
- The outbox worker runs as a **separate Kubernetes deployment** (not in FastAPI process)
- When scaling replicas, ensure Kafka consumer group settings are correct to avoid duplicate processing
- Alembic migrations must complete before the API pods start (enforced via Terraform Job)
- Use `uv` (not pip) for all dependency management
