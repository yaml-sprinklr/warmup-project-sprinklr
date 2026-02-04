environment = "prod"
namespace   = "order-service-prod"

# Application Configuration
app_replica_count = 10  # High availability for prod

app_resources = {
  requests = {
    cpu    = "1000m"   # 1 CPU core
    memory = "1Gi"
  }
  limits = {
    cpu    = "2000m"   # 2 CPU cores
    memory = "2Gi"
  }
}

# Database Configuration
postgres_storage_size = "50Gi"  # Production data

postgres_resources = {
  requests = {
    cpu    = "1000m"   # 1 CPU core
    memory = "2Gi"
  }
  limits = {
    cpu    = "2000m"   # 2 CPU cores
    memory = "4Gi"
  }
}

# Migration Configuration
migration_backoff_limit       = 5     # More retries for prod
migration_wait_for_completion = true  # Block until migrations complete!

migration_resources = {
  requests = {
    cpu    = "500m"
    memory = "512Mi"
  }
  limits = {
    cpu    = "1000m"
    memory = "1Gi"
  }
}

# Feature Flags
enable_metrics     = true   # Enable monitoring in prod
enable_autoscaling = true   # Auto-scale based on load
enable_ingress     = true   # External access in prod

# Resource Labels
common_labels = {
  managed-by  = "terraform"
  environment = "prod"
  team        = "platform"
  cost-center = "engineering"
}
