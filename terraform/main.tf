# Namespace

resource "kubernetes_namespace" "order_service" {
  metadata {
    name = "order-service"

    labels = {
      managed-by  = "terraform"
      app         = "order-service"
      environment = "dev"
    }
    annotations = {
      description = "Namespace for order service and its dependencies"
    }
  }
}


# Database Password Generation

resource "random_password" "postgres_password" {
  length           = 16
  special          = true
  upper            = true
  lower            = true
  numeric          = true
  override_special = "!#$%&*()-_=+[]{}:?"

  lifecycle {
    ignore_changes = [
      # Don't regenerate if these change
      override_special,
    ]
  }
}


# Postgres Database

resource "helm_release" "postgresql" {
  name       = "my-pg-release"
  repository = "oci://registry-1.docker.io/bitnamicharts"
  chart      = "postgresql"
  version    = "18.2.3"
  wait       = true
  timeout    = 300
  namespace  = kubernetes_namespace.order_service.metadata[0].name

  create_namespace = false

  # ===== HELM VALUES =====
  # These override the default values.yaml in the PostgreSQL chart
  # Same as: helm install --set key=value

  # Set the PostgreSQL password
  set_sensitive {
    name  = "auth.postgresPassword"
    value = random_password.postgres_password.result
    # ↑ Reference the random password we generated above
    # This creates another dependency: password must exist first!
  }

  # Database name
  set {
    name  = "auth.database"
    value = "appdb"
  }
  set {
    name  = "primary.persistence.size"
    value = "1Gi"
  }
  set {
    name  = "primary.resources.requests.cpu"
    value = "250m"
  }
  set {
    name  = "primary.resources.limits.memory"
    value = "512Mi"
  }
  set {
    name  = "primary.resources.limits.cpu"
    value = "500m"
  }
  set {
    name  = "metrics.enabled"
    value = "false"
  }
}

# Database Connection Secret

resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "db-credentials"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = {
      app        = "order-service"
      managed-by = "terraform"
    }
  }

  # Only store sensitive data in the secret
  data = {
    POSTGRES_PASSWORD = random_password.postgres_password.result
  }

  type       = "Opaque"
  depends_on = [helm_release.postgresql]
}

# APPLICATION CONFIGURATION (Non-sensitive)

resource "kubernetes_config_map" "app_config" {
  metadata {
    name      = "order-service-config"
    namespace = kubernetes_namespace.order_service.metadata[0].name
    labels = {
      app        = "order-service"
      managed-by = "terraform"
    }
  }

  data = {
    POSTGRES_SERVER = "${helm_release.postgresql.name}-postgresql"
    POSTGRES_PORT   = "5432"
    POSTGRES_DB     = "appdb"
    POSTGRES_USER   = "postgres"
  }

  depends_on = [
    helm_release.postgresql
  ]
}

# DATABASE MIGRATIONS JOB

resource "kubernetes_job_v1" "db_migrations" {
  metadata {
    name      = "db-migrations"
    namespace = kubernetes_namespace.order_service.metadata[0].name

    labels = {
      app        = "order-service"
      component  = "migrations"
      managed-by = "terraform"
    }
  }

  spec {
    backoff_limit = 3

    ttl_seconds_after_finished = 300

    template {
      metadata {
        labels = {
          app       = "order-service"
          component = "migrations"
        }
      }

      spec {
        # Jobs must have restartPolicy: OnFailure or Never
        # OnFailure = retry in same pod
        # Never = create new pod for each retry
        restart_policy = "OnFailure"

        container {
          name  = "alembic-migrations"
          image = "order-service:v6" # Same image as your app

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
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "250m"
              memory = "256Mi"
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

  # Don't wait for completion during terraform apply
  # This allows terraform to proceed while job runs
  wait_for_completion = false

  # However, we can optionally wait with a timeout
  # Uncomment to wait up to 5 minutes for migrations to complete:
  # wait_for_completion = true
  # timeouts {
  #   create = "5m"
  #   update = "5m"
  # }
}

# FastAPI application for order-service

resource "helm_release" "order_service" {
  name             = "order-service"
  chart            = "../helm/rest-api"
  namespace        = kubernetes_namespace.order_service.metadata[0].name
  wait             = true
  timeout          = 300
  create_namespace = false

  # Overriding values from values.yaml
  set {
    name  = "image.repository"
    value = "order-service"
  }

  set {
    name  = "image.repository"
    value = "order-service"
  }

  set {
    name  = "image.tag"
    value = "v6"
  }

  set {
    name  = "image.pullPolicy"
    value = "Never" # Use local image, don't pull from registry
  }

  # Replica count
  set {
    name  = "replicaCount"
    value = "2"
  }

  # Reference the ConfigMap for non-sensitive config
  set {
    name  = "envFromConfigMap"
    value = kubernetes_config_map.app_config.metadata[0].name
  }

  # Reference the Secret for sensitive data
  set {
    name  = "envFromSecret"
    value = kubernetes_secret.db_credentials.metadata[0].name
  }

  # ===== DEPENDENCIES =====
  # Ensure migrations complete before app starts
  depends_on = [
    helm_release.postgresql,          # Database must be running
    kubernetes_config_map.app_config, # Config must exist
    kubernetes_secret.db_credentials, # Credentials must exist
    kubernetes_job_v1.db_migrations   # Migrations must complete first! ← NEW!
  ]
}
# FastAPI application Outputs

output "migration_job_name" {
  description = "The name of the database migration job"
  value       = kubernetes_job_v1.db_migrations.metadata[0].name
}

output "migration_status" {
  description = "Check migration job status with this command"
  value       = "kubectl get job ${kubernetes_job_v1.db_migrations.metadata[0].name} -n ${kubernetes_namespace.order_service.metadata[0].name}"
}

output "migration_logs" {
  description = "View migration logs with this command"
  value       = "kubectl logs -n ${kubernetes_namespace.order_service.metadata[0].name} -l component=migrations"
}

output "order_service_release_name" {
  description = "The Helm release name for order service"
  value       = helm_release.order_service.name
}

output "order_service_namespace" {
  description = "The namespace where order service is deployed"
  value       = helm_release.order_service.namespace
}

output "order_service_status" {
  description = "The status of the order service Helm release"
  value       = helm_release.order_service.status
}

output "order_service_access" {
  description = "How to access your order service locally"
  value = {
    namespace    = helm_release.order_service.namespace
    service_name = "${helm_release.order_service.name}-rest-api"
    port         = 8000
    port_forward = "kubectl port-forward -n ${helm_release.order_service.namespace} svc/${helm_release.order_service.name}-rest-api 8080:8000"
    test_api     = "curl http://localhost:8080/api/v1/orders"
  }
}

# Other Outputs

output "namespace_name" {
  description = "The name of the created namespace"
  value       = kubernetes_namespace.order_service.metadata[0].name
}


output "namespace_id" {
  description = "The unique ID of the namespace"
  value       = kubernetes_namespace.order_service.id
}


output "postgresql_release_name" {
  description = "The Helm release name for PostgreSQL"
  value       = helm_release.postgresql.name
}

output "postgresql_service_name" {
  description = "The Kubernetes service name for PostgreSQL"
  value       = "${helm_release.postgresql.name}-postgresql"
}

output "postgresql_host" {
  description = "The full DNS name to connect to PostgreSQL from within the cluster"
  value       = "${helm_release.postgresql.name}-postgresql.${kubernetes_namespace.order_service.metadata[0].name}.svc.cluster.local"
}

output "db_password" {
  description = "The PostgreSQL password (sensitive)"
  value       = random_password.postgres_password.result
  sensitive   = true # Won't display in terminal output
}

output "db_secret_name" {
  description = "The name of the Kubernetes secret containing DB credentials"
  value       = kubernetes_secret.db_credentials.metadata[0].name
}

output "app_config_name" {
  description = "The name of the ConfigMap containing application configuration"
  value       = kubernetes_config_map.app_config.metadata[0].name
}
