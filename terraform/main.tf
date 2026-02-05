# NAMESPACE

resource "kubernetes_namespace" "order_service" {
  metadata {
    name = var.namespace

    # Merge common labels with resource-specific labels
    labels = merge(
      var.common_labels,
      {
        app         = var.app_name
        environment = var.environment
      }
    )

    annotations = {
      description = "Namespace for ${var.app_name} and its dependencies"
      environment = var.environment
    }
  }
}

# DATABASE PASSWORD GENERATION

resource "random_password" "postgres_password" {
  length           = var.postgres_password_length
  special          = true
  upper            = true
  lower            = true
  numeric          = true
  override_special = "!#$%&*()-_=+[]{}:?"

  lifecycle {
    ignore_changes = [
      override_special,
    ]
  }
}

# POSTGRESQL DATABASE

resource "helm_release" "postgresql" {
  name       = "${var.app_name}-postgres"
  repository = "oci://registry-1.docker.io/bitnamicharts"
  chart      = "postgresql"
  version    = var.postgres_chart_version

  namespace = kubernetes_namespace.order_service.metadata[0].name

  wait    = true
  timeout = var.helm_timeout

  create_namespace = false

  # ===== HELM VALUES =====
  # These override the default values.yaml in the PostgreSQL chart
  # Same as: helm install --set key=value

  set_sensitive {
    name  = "auth.postgresPassword"
    value = random_password.postgres_password.result
    # ↑ Reference the random password we generated above
    # This creates another dependency: password must exist first!
  }

  set {
    name  = "auth.database"
    value = var.postgres_database_name
  }

  set {
    name  = "primary.persistence.size"
    value = var.postgres_storage_size
  }

  set {
    name  = "primary.resources.requests.cpu"
    value = var.postgres_resources.requests.cpu
  }

  set {
    name  = "primary.resources.requests.memory"
    value = var.postgres_resources.requests.memory
  }

  set {
    name  = "primary.resources.limits.cpu"
    value = var.postgres_resources.limits.cpu
  }

  set {
    name  = "primary.resources.limits.memory"
    value = var.postgres_resources.limits.memory
  }

  # Metrics (monitoring)
  set {
    name  = "metrics.enabled"
    value = var.enable_metrics
  }
}

# Redis

resource "helm_release" "redis" {
  name       = "${var.app_name}-redis"
  repository = "oci://registry-1.docker.io/bitnamicharts"
  chart      = "redis"
  version    = var.redis_chart_version
  namespace  = kubernetes_namespace.order_service.metadata[0].name

  wait    = true
  timeout = var.helm_timeout

  create_namespace = false

  set {
    name  = "auth.enabled"
    value = "false"
  }

  set {
    name  = "master.persistence.enabled"
    value = "false" # Cache doesn't need persistence
  }

  set {
    name  = "master.resources.requests.cpu"
    value = var.redis_resources.requests.cpu
  }

  set {
    name  = "master.resources.requests.memory"
    value = var.redis_resources.requests.memory
  }

  set {
    name  = "master.resources.limits.cpu"
    value = var.redis_resources.limits.cpu
  }

  set {
    name  = "master.resources.limits.memory"
    value = var.redis_resources.limits.memory
  }
}
# DATABASE CONNECTION SECRET

resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "${var.app_name}-db-credentials"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = merge(
      var.common_labels,
      {
        app       = var.app_name
        component = "database"
      }
    )
  }

  data = {
    POSTGRES_PASSWORD = random_password.postgres_password.result
  }

  type       = "Opaque"
  depends_on = [helm_release.postgresql]
}

# APPLICATION CONFIGURATION (Non-sensitive)

resource "kubernetes_config_map" "app_config" {
  metadata {
    name      = "${var.app_name}-config"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = merge(
      var.common_labels,
      {
        app       = var.app_name
        component = "configuration"
      }
    )
  }

  data = {
    # PostgreSQL Configuration
    POSTGRES_SERVER = "${helm_release.postgresql.name}-postgresql"
    POSTGRES_PORT   = "5432"
    POSTGRES_DB     = var.postgres_database_name
    POSTGRES_USER   = "postgres"

    # Redis Configuration (NEW)
    REDIS_HOST = "${helm_release.redis.name}-master"
    REDIS_PORT = "6379"
    REDIS_DB   = "0"

    # Kafka Configuration (NEW)
    KAFKA_BOOTSTRAP_SERVERS = "${var.app_name}-kafka-kafka-bootstrap:9092"
    KAFKA_CONSUMER_GROUP_ID = "order-service"

    # Kafka Topics
    KAFKA_TOPIC_ORDER_CREATED   = "order.created"
    KAFKA_TOPIC_ORDER_CONFIRMED = "order.confirmed"
    KAFKA_TOPIC_ORDER_SHIPPED   = "order.shipped"
    KAFKA_TOPIC_ORDER_CANCELLED = "order.cancelled"
    KAFKA_TOPIC_USER_CREATED    = "user.created"
    KAFKA_TOPIC_USER_UPDATED    = "user.updated"
    KAFKA_TOPIC_USER_DELETED    = "user.deleted"

    # User Service API (for fallback)
    USER_SERVICE_URL = var.user_service_url
  }

  depends_on = [
    helm_release.postgresql,
    helm_release.redis,
    kubernetes_manifest.kafka_cluster
  ]
}

# DATABASE MIGRATIONS JOB

resource "kubernetes_job_v1" "db_migrations" {
  metadata {
    name      = "${var.app_name}-migrations"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = merge(
      var.common_labels,
      {
        app       = var.app_name
        component = "migrations"
      }
    )
  }

  spec {
    backoff_limit = var.migration_backoff_limit

    ttl_seconds_after_finished = 300

    template {
      metadata {
        labels = {
          app       = var.app_name
          component = "migrations"
        }
      }

      spec {
        restart_policy = "OnFailure"

        container {
          name  = "alembic-migrations"
          image = "${var.app_image_repository}:${var.app_image_tag}"

          command = [
            "/bin/sh",
            "-c",
            "cd /app/backend && uv run alembic upgrade head"
          ]

          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.db_credentials.metadata[0].name
            }
          }

          resources {
            requests = {
              cpu    = var.migration_resources.requests.cpu
              memory = var.migration_resources.requests.memory
            }
            limits = {
              cpu    = var.migration_resources.limits.cpu
              memory = var.migration_resources.limits.memory
            }
          }
        }
      }
    }
  }

  depends_on = [
    helm_release.postgresql,
    kubernetes_config_map.app_config,
    kubernetes_secret.db_credentials
  ]

  # This ensures the job is deleted and recreated if config changes
  # Without this, Terraform can't update jobs (they're immutable)
  lifecycle {
    replace_triggered_by = [
      kubernetes_config_map.app_config,
      kubernetes_secret.db_credentials
    ]
  }

  # Wait for compxletion setting from variables
  # In prod, this should be true to ensure migrations complete before app starts
  wait_for_completion = var.migration_wait_for_completion
}

# FASTAPI APPLICATION

resource "helm_release" "order_service" {
  name      = var.app_name
  chart     = var.helm_chart_path
  namespace = kubernetes_namespace.order_service.metadata[0].name

  wait    = true
  timeout = var.helm_timeout

  create_namespace = false

  set {
    name  = "image.repository"
    value = var.app_image_repository
  }

  set {
    name  = "image.tag"
    value = var.app_image_tag
  }

  set {
    name  = "image.pullPolicy"
    value = "Never" # Always use local image for now
  }

  set {
    name  = "replicaCount"
    value = var.app_replica_count
  }

  set {
    name  = "envFromConfigMap"
    value = kubernetes_config_map.app_config.metadata[0].name
  }

  set {
    name  = "envFromSecret"
    value = kubernetes_secret.db_credentials.metadata[0].name
  }

  depends_on = [
    helm_release.postgresql,
    helm_release.redis,
    helm_release.strimzi_operator,
    kubernetes_manifest.kafka_cluster,
    kubernetes_manifest.topic_order_created,
    kubernetes_manifest.topic_order_confirmed,
    kubernetes_manifest.topic_order_shipped,
    kubernetes_manifest.topic_order_cancelled,
    kubernetes_manifest.topic_user_created,
    kubernetes_manifest.topic_user_updated,
    kubernetes_manifest.topic_user_deleted,
    kubernetes_config_map.app_config,
    kubernetes_secret.db_credentials,
    kubernetes_job_v1.db_migrations
  ]
}

# OUTBOX WORKER DEPLOYMENT

resource "kubernetes_deployment_v1" "outbox_worker" {
  count = var.outbox_worker_enabled ? 1 : 0

  metadata {
    name      = "${var.app_name}-outbox-worker"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = merge(
      var.common_labels,
      {
        app       = var.app_name
        component = "outbox-worker"
      }
    )
  }

  spec {
    replicas = var.outbox_worker_replica_count

    selector {
      match_labels = {
        app       = var.app_name
        component = "outbox-worker"
      }
    }

    template {
      metadata {
        labels = {
          app       = var.app_name
          component = "outbox-worker"
        }
      }

      spec {
        container {
          name  = "outbox-worker"
          image = "${var.outbox_worker_image_repository}:${var.outbox_worker_image_tag}"

          command = ["python", "-m", "app.workers.outbox_worker"]

          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.db_credentials.metadata[0].name
            }
          }

          resources {
            requests = {
              cpu    = var.outbox_worker_resources.requests.cpu
              memory = var.outbox_worker_resources.requests.memory
            }
            limits = {
              cpu    = var.outbox_worker_resources.limits.cpu
              memory = var.outbox_worker_resources.limits.memory
            }
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_config_map.app_config,
    kubernetes_secret.db_credentials,
    kubernetes_job_v1.db_migrations
  ]
}

# MOCK USER PRODUCER DEPLOYMENT (for testing)

resource "kubernetes_deployment_v1" "mock_user_producer" {
  count = var.mock_user_producer_enabled ? 1 : 0

  metadata {
    name      = "${var.app_name}-mock-user-producer"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = merge(
      var.common_labels,
      {
        app       = var.app_name
        component = "mock-user-producer"
      }
    )

    annotations = {
      description = "Mock user service that produces user lifecycle events for testing"
    }
  }

  spec {
    replicas = var.mock_user_producer_replica_count

    selector {
      match_labels = {
        app       = var.app_name
        component = "mock-user-producer"
      }
    }

    template {
      metadata {
        labels = {
          app       = var.app_name
          component = "mock-user-producer"
        }

        annotations = {
          "prometheus.io/scrape" = "false" # No metrics endpoint yet
        }
      }

      spec {
        restart_policy = "Always"

        container {
          name  = "mock-producer"
          image = "${var.mock_user_producer_image_repository}:${var.mock_user_producer_image_tag}"

          command = ["python", "-m", "app.producers.user_producer_mock"]

          # Load Kafka configuration from ConfigMap
          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }

          # Override default intervals if specified
          dynamic "env" {
            for_each = var.mock_user_producer_create_interval != null ? [1] : []
            content {
              name  = "MOCK_USER_CREATE_INTERVAL"
              value = tostring(var.mock_user_producer_create_interval)
            }
          }

          dynamic "env" {
            for_each = var.mock_user_producer_update_interval != null ? [1] : []
            content {
              name  = "MOCK_USER_UPDATE_INTERVAL"
              value = tostring(var.mock_user_producer_update_interval)
            }
          }

          dynamic "env" {
            for_each = var.mock_user_producer_delete_interval != null ? [1] : []
            content {
              name  = "MOCK_USER_DELETE_INTERVAL"
              value = tostring(var.mock_user_producer_delete_interval)
            }
          }

          dynamic "env" {
            for_each = var.mock_user_producer_max_users != null ? [1] : []
            content {
              name  = "MOCK_USER_MAX_USERS"
              value = tostring(var.mock_user_producer_max_users)
            }
          }

          resources {
            requests = {
              cpu    = var.mock_user_producer_resources.requests.cpu
              memory = var.mock_user_producer_resources.requests.memory
            }
            limits = {
              cpu    = var.mock_user_producer_resources.limits.cpu
              memory = var.mock_user_producer_resources.limits.memory
            }
          }

          # Liveness probe - check if process is alive
          liveness_probe {
            exec {
              command = ["pgrep", "-f", "user_producer_mock"]
            }
            initial_delay_seconds = 10
            period_seconds        = 30
            timeout_seconds       = 5
            failure_threshold     = 3
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_config_map.app_config,
    kubernetes_manifest.kafka_cluster,
    kubernetes_manifest.topic_user_created,
    kubernetes_manifest.topic_user_updated,
    kubernetes_manifest.topic_user_deleted
  ]
}


# STRIMZI KAFKA OPERATOR
resource "helm_release" "strimzi_operator" {
  name       = "strimzi-kafka-operator"
  repository = "https://strimzi.io/charts/"
  chart      = "strimzi-kafka-operator"
  version    = "0.50.0" # Latest stable as of Feb 2026
  namespace  = kubernetes_namespace.order_service.metadata[0].name

  wait    = true
  timeout = var.helm_timeout

  create_namespace = false

  # Operator configuration
  set {
    name  = "watchAnyNamespace"
    value = "false" # Only watch this namespace
  }

  set {
    name  = "resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "200m"
  }

  set {
    name  = "resources.limits.memory"
    value = "256Mi"
  }
}


# KAFKA NODE POOL (required by Strimzi 0.50+)

resource "kubernetes_manifest" "kafka_node_pool" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaNodePool"
    metadata = {
      name      = "${var.app_name}-kafka-pool"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = merge(
        var.common_labels,
        {
          app                  = var.app_name
          component            = "kafka"
          "strimzi.io/cluster" = "${var.app_name}-kafka"
        }
      )
    }
    spec = {
      replicas = 1
      roles    = ["broker", "controller"]
      storage = {
        type = "ephemeral" # No persistence for local dev
      }
      resources = {
        requests = {
          cpu    = var.kafka_resources.requests.cpu
          memory = var.kafka_resources.requests.memory
        }
        limits = {
          cpu    = var.kafka_resources.limits.cpu
          memory = var.kafka_resources.limits.memory
        }
      }
    }
  }

  depends_on = [helm_release.strimzi_operator]
}


# KAFKA CLUSTER (using Strimzi CRD with KRaft mode)

resource "kubernetes_manifest" "kafka_cluster" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "Kafka"
    metadata = {
      name      = "${var.app_name}-kafka"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = merge(
        var.common_labels,
        {
          app       = var.app_name
          component = "kafka"
        }
      )
      annotations = {
        "strimzi.io/node-pools" = "enabled"
        "strimzi.io/kraft"      = "enabled"
      }
    }
    spec = {
      # Kafka broker configuration with KRaft mode
      kafka = {
        version  = "4.1.1"
        replicas = 1

        metadataVersion = "4.1-IV1" # KRaft metadata version

        listeners = [
          {
            name = "plain"
            port = 9092
            type = "internal"
            tls  = false
          }
        ]

        config = {
          "offsets.topic.replication.factor"         = 1
          "transaction.state.log.replication.factor" = 1
          "transaction.state.log.min.isr"            = 1
          "default.replication.factor"               = 1
          "min.insync.replicas"                      = 1
          "auto.create.topics.enable"                = false
          "log.retention.hours"                      = 168
          "log.segment.bytes"                        = 1073741824
          "compression.type"                         = "producer"
        }
      }

      # Entity Operator (manages topics and users)
      entityOperator = {
        topicOperator = {
          resources = {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "200m"
              memory = "256Mi"
            }
          }
        }
        userOperator = {
          resources = {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "200m"
              memory = "256Mi"
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.strimzi_operator, kubernetes_manifest.kafka_node_pool]
}


# KAFKA TOPICS (using Strimzi KafkaTopic CRD)

# Topics WE PRODUCE (for Team 3 & Team 4 to consume)

resource "kubernetes_manifest" "topic_order_created" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "order.created"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1 # Dev: 1, Prod: 3
      config = {
        "retention.ms"     = "604800000"  # 7 days
        "segment.bytes"    = "1073741824" # 1 GB
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

resource "kubernetes_manifest" "topic_order_confirmed" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "order.confirmed"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

resource "kubernetes_manifest" "topic_order_shipped" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "order.shipped"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

resource "kubernetes_manifest" "topic_order_cancelled" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "order.cancelled"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

# Topics WE CONSUME (from Team 1 - User Service)
# Note: In real scenario, Team 1 would create these
# For local simulation, we create them here

resource "kubernetes_manifest" "topic_user_created" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "user.created"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

resource "kubernetes_manifest" "topic_user_updated" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "user.updated"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}

resource "kubernetes_manifest" "topic_user_deleted" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "KafkaTopic"
    metadata = {
      name      = "user.deleted"
      namespace = kubernetes_namespace.order_service.metadata[0].name
      labels = {
        "strimzi.io/cluster" = "${var.app_name}-kafka"
      }
    }
    spec = {
      partitions = 3
      replicas   = 1
      config = {
        "retention.ms"     = "604800000"
        "segment.bytes"    = "1073741824"
        "compression.type" = "producer"
        "cleanup.policy"   = "delete"
      }
    }
  }

  depends_on = [kubernetes_manifest.kafka_cluster]
}
