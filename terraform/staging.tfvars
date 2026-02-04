environment = "staging"
namespace   = "order-service-staging"

# Application Configuration
app_replica_count = 3  # Middle ground between dev and prod

app_resources = {
  requests = {
    cpu    = "500m"
    memory = "512Mi"
  }
  limits = {
    cpu    = "1000m"
    memory = "1Gi"
  }
}

# Database Configuration
postgres_storage_size = "10Gi"  # Staging data (subset of prod)

postgres_resources = {
  requests = {
    cpu    = "500m"
    memory = "1Gi"
  }
  limits = {
    cpu    = "1000m"
    memory = "2Gi"
  }
}

# Migration Configuration
migration_backoff_limit       = 4
migration_wait_for_completion = true  # Wait in staging too

# Feature Flags
enable_metrics     = true   # Test monitoring in staging
enable_autoscaling = false  # Manual control in staging
enable_ingress     = true   # Test ingress configuration

# Resource Labels
common_labels = {
  managed-by  = "terraform"
  environment = "staging"
  team        = "platform"
}
