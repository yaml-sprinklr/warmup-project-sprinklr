# REST API

Object -> orders

## Operations

- Create orders
- Read orders
- Update orders
- Delete orders

## Routes

- HTTP GET '/' -> get_all_orders
- HTTP GET -> '/<id>' -> get_order_by_id
- HTTP POST '/' -> create_new_order
- HTTP PUT '/<id>' -> update_order_by_id
- HTTP DELETE '/<id>' -> delete_order_by_id

## Events

Orders have a life cycle.

Possible status of an order:

- CREATED
- CONFIRMED
- SHIPPED

### How do orders progress in their life cycle

- created → (delay) → confirmed → (delay) → shipped
- we can mock this using asyncio.sleep()

## Uvicorn or Gunicorn

Uvicorn natively supports ASGI, which is what FastAPI requires. But, Gunicorn can control Uvicorn to run multiple instances of it. This allows us to achieve both parallelism and concurrency. But, when we're using an orchestrator like K8s, we can leave out this load management to the cluster level.

source -> <https://stackoverflow.com/a/71546833>

## Alembic

I have setup alembic using its `env.py` file to use the correct connection string by importing it from `app.core.config.settings`

In the most basic setup, postgres is running on top of containerd using:

```
nerdctl run --name local-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=appdb \
  -p 5432:5432 \
  -d postgres
```

After writing up all the models using sqlmodel, an alembic revision is created. Then, migration is run to make the db up to date with all the models. For now, there is no seed data.

## Docker

<https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/Dockerfile>
<https://github.com/astral-sh/uv-docker-example/blob/main/Dockerfile>
Taking these 2 repos as reference for creating the Dockerfile.

## Notes

- explore certificates and add https support.

## Progression (milestones)

### Milestone 1

1. Run FastAPI as a native process directly from the macOS zsh shell
2. Run postgres using a container on top of containerd
3. Containerize the FastAPI application and run it; connect it to the containerized postgres using a network bridge created nerdctl which in turn uses a CNI plugin to create that network.
4. Install a postgres chart in the k8s cluster using helm. Create a helm chart for the FastAPI application and install a release of it in the cluster. Port forward the requests from local port 8080 to (pod?/service?) port 8000. Alembic migrations had to be run manually by port forwarding the postgres 5432 port from local to (pod?/service?), and running `alembic upgrade head` with proper environment variables for connecting to the correct db, host, and user used by the postgres instance in k8s.

```
export POSTGRES_SERVER=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=postgres
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=RpHaLo4txB
```

Note: A later task would be to automatically running migrations whenever required?

Liveness and Readiness routes were also added in this milestone.

Cute: add some illustrations for these milestones
5. `terraform apply` spins up the service and database.
Note: What are the best practices of using terraform with k8s? which backend should be used -> local or k8s
=> Currently, using local without much analysis of choices.

### Milestone 2

1. Adding Kafka
2. Using python library `tenacity` for retrying logic.
3. `aiokafka` vs `confluent-kafka`
4. strimzi vs bitnami helm chart => A Helm chart (like Bitnami’s) does not do reconciliation—it only deploys resources once.
Strimzi Advantages:
Kubernetes-native: Uses CRDs (Custom Resource Definitions) - more aligned with modern K8s practices
Operator pattern: Continuous reconciliation - if something breaks, Strimzi auto-heals
Declarative topics: Create Kafka topics as Kubernetes resources (KafkaTopic CRD)
Production-ready: Rolling updates, monitoring, TLS, ACLs out of the box
Better for learning: Understand operators, CRDs, and how production Kafka works
Aligns with your milestone: "Kafka topic(s) created declaratively (CRD or Helm values) via Terraform"
Helm Chart Limitations:
No reconciliation (deploy once and forget)
Topics created via scripts, not declaratively
Harder to manage at scale
5. KafkaNodePool
6. tenacity
remaining to implement -> metrics
7. Problem: When you scale the API to multiple replicas, you get:
2 replicas = 2 consumers + 2 processors competing
Kafka consumer group helps with consumer (only 1 gets each message)
But processor loops will all try to process orders (race conditions)

```
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background tasks IN THE SAME PROCESS as FastAPI
    consumer_task = asyncio.create_task(start_consumer(), name="kafka-consumer")
    processor_task = asyncio.create_task(start_order_processor(), name="order-processor")
```

1. use redis for outbox pattern?
2. leaving out nitty gritty of asyncio for now
3. TODO: load test

### Milestone 3


