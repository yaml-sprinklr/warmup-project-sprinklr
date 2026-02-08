environment = "dev"
namespace   = "order-service"

# Application Configuration
app_name             = "order-service"
app_image_repository = "order-service"
app_image_tag        = "ci"
app_replica_count    = 2  # Small for dev

# Keep worker images aligned with app
outbox_worker_image_tag     = "ci"
mock_user_producer_image_tag = "ci"

app_resources = {
  requests = {
    cpu    = "250m"
    memory = "256Mi"
  }
  limits = {
    cpu    = "500m"
    memory = "512Mi"
  }
}

# Database Configuration
postgres_database_name = "appdb"
postgres_storage_size  = "1Gi"  # Small for dev

postgres_resources = {
  requests = {
    cpu    = "250m"
    memory = "256Mi"
  }
  limits = {
    cpu    = "500m"
    memory = "512Mi"
  }
}

# Migration Configuration
migration_backoff_limit       = 3
migration_wait_for_completion = false  # Don't block terraform apply

# Feature Flags
enable_metrics     = true  # Disable monitoring in dev
enable_autoscaling = false  # Manual scaling in dev
enable_ingress     = false  # Use port-forward in dev

# Resource Labels
common_labels = {
  managed-by  = "terraform"
  environment = "dev"
  team        = "platform"
}



# Grafana admin password
grafana_admin_password = "admin"

# Enable Grafana ingress
grafana_ingress_enabled = false
grafana_hostname        = "grafana.yourdomain.com"

# Order Service namespace
order_service_namespace = "order-service"

# Deploy outbox worker monitoring
deploy_outbox_worker_monitor = true

# Prometheus retention
prometheus_retention      = "90d"
prometheus_retention_size = "200GB"
prometheus_storage_size   = "200Gi"
