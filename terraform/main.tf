# ============================================================================
# NAMESPACE
# ============================================================================

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


# ============================================================================
# DATABASE PASSWORD GENERATION
# ============================================================================

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


# ============================================================================
# POSTGRESQL DATABASE
# ============================================================================

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
    value = var.postgres_database_name
  }
  
  # Storage configuration
  set {
    name  = "primary.persistence.size"
    value = var.postgres_storage_size
  }
  
  # Resource requests
  set {
    name  = "primary.resources.requests.cpu"
    value = var.postgres_resources.requests.cpu
  }
  
  set {
    name  = "primary.resources.requests.memory"
    value = var.postgres_resources.requests.memory
  }
  
  # Resource limits
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

# ============================================================================
# DATABASE CONNECTION SECRET
# ============================================================================

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

  # Only store sensitive data in the secret
  data = {
    POSTGRES_PASSWORD = random_password.postgres_password.result
  }

  type       = "Opaque"
  depends_on = [helm_release.postgresql]
}

# ============================================================================
# APPLICATION CONFIGURATION (Non-sensitive)
# ============================================================================

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
    POSTGRES_SERVER = "${helm_release.postgresql.name}-postgresql"
    POSTGRES_PORT   = "5432"
    POSTGRES_DB     = var.postgres_database_name
    POSTGRES_USER   = "postgres"
  }

  depends_on = [
    helm_release.postgresql
  ]
}

# ============================================================================
# DATABASE MIGRATIONS JOB
# ============================================================================

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

  # Wait for completion setting from variables
  # In prod, this should be true to ensure migrations complete before app starts
  wait_for_completion = var.migration_wait_for_completion
}

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

resource "helm_release" "order_service" {
  name      = var.app_name
  chart     = var.helm_chart_path
  namespace = kubernetes_namespace.order_service.metadata[0].name
  
  wait    = true
  timeout = var.helm_timeout
  
  create_namespace = false
  
  # ===== IMAGE CONFIGURATION =====
  
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
    value = "Never"  # Always use local image for now
  }
  
  # ===== SCALING =====
  
  set {
    name  = "replicaCount"
    value = var.app_replica_count
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
    helm_release.postgresql,           # Database must be running
    kubernetes_config_map.app_config,  # Config must exist
    kubernetes_secret.db_credentials,  # Credentials must exist
    kubernetes_job_v1.db_migrations    # Migrations must complete first!
  ]
}
