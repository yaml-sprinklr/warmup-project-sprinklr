variable "environment" {
  type        = string
  description = "Environment name (dev, staging, prod)"
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace for the application"
  default     = "order-service"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.namespace))
    error_message = "Namespace must contain only lowercase letters, numbers, and hyphens."
  }
}

# APPLICATION CONFIGURATION

variable "app_name" {
  type        = string
  description = "Application name"
  default     = "order-service"
}

variable "app_image_repository" {
  type        = string
  description = "Docker image repository"
  default     = "order-service"
}

variable "app_image_tag" {
  type        = string
  description = "Docker image tag"
  default     = "v15"

  validation {
    condition     = can(regex("^v[0-9]+$", var.app_image_tag))
    error_message = "Image tag must be in format v1, v2, v3, etc."
  }
}

variable "app_replica_count" {
  type        = number
  description = "Number of application pod replicas"
  default     = 2

  validation {
    condition     = var.app_replica_count >= 1 && var.app_replica_count <= 100
    error_message = "Replica count must be between 1 and 100."
  }
}

variable "app_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for application pods"
  default = {
    requests = {
      cpu    = "250m"
      memory = "256Mi"
    }
    limits = {
      cpu    = "500m"
      memory = "512Mi"
    }
  }
}
# OUTBOX WORKER CONFIGURATION

variable "outbox_worker_enabled" {
  type        = bool
  description = "Enable outbox worker deployment"
  default     = true
}

variable "outbox_worker_image_repository" {
  type        = string
  description = "Outbox worker image repository"
  default     = "order-service"
}

variable "outbox_worker_image_tag" {
  type        = string
  description = "Outbox worker image tag"
  default     = "v15"

  validation {
    condition     = can(regex("^v[0-9]+$", var.outbox_worker_image_tag))
    error_message = "Image tag must be in format v1, v2, v3, etc."
  }
}

variable "outbox_worker_replica_count" {
  type        = number
  description = "Number of outbox worker replicas"
  default     = 1

  validation {
    condition     = var.outbox_worker_replica_count >= 1 && var.outbox_worker_replica_count <= 20
    error_message = "Replica count must be between 1 and 20."
  }
}

variable "outbox_worker_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for outbox worker"
  default = {
    requests = {
      cpu    = "100m"
      memory = "256Mi"
    }
    limits = {
      cpu    = "500m"
      memory = "512Mi"
    }
  }
}

# MOCK USER PRODUCER CONFIGURATION

variable "mock_user_producer_enabled" {
  type        = bool
  description = "Enable mock user producer deployment for testing"
  default     = true
}

variable "mock_user_producer_image_repository" {
  type        = string
  description = "Mock user producer image repository (same as main app)"
  default     = "order-service"
}

variable "mock_user_producer_image_tag" {
  type        = string
  description = "Mock user producer image tag (same as main app)"
  default     = "v15"

  validation {
    condition     = can(regex("^v[0-9]+$", var.mock_user_producer_image_tag))
    error_message = "Image tag must be in format v1, v2, v3, etc."
  }
}

variable "mock_user_producer_replica_count" {
  type        = number
  description = "Number of mock producer replicas (usually 1)"
  default     = 1

  validation {
    condition     = var.mock_user_producer_replica_count >= 1 && var.mock_user_producer_replica_count <= 5
    error_message = "Replica count must be between 1 and 5."
  }
}

variable "mock_user_producer_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for mock user producer"
  default = {
    requests = {
      cpu    = "50m"
      memory = "128Mi"
    }
    limits = {
      cpu    = "200m"
      memory = "256Mi"
    }
  }
}

# Event generation intervals (null = use app defaults)
variable "mock_user_producer_create_interval" {
  type        = number
  description = "Seconds between user creation events (null = use default from config)"
  default     = null
}

variable "mock_user_producer_update_interval" {
  type        = number
  description = "Seconds between user update events (null = use default from config)"
  default     = null
}

variable "mock_user_producer_delete_interval" {
  type        = number
  description = "Seconds between user deletion events (null = use default from config)"
  default     = null
}

variable "mock_user_producer_max_users" {
  type        = number
  description = "Maximum number of active users (null = use default from config)"
  default     = null
}

# POSTGRES DATABASE CONFIGURATION

variable "postgres_chart_version" {
  type        = string
  description = "PostgreSQL Helm chart version"
  default     = "18.2.3"
}

variable "postgres_database_name" {
  type        = string
  description = "PostgreSQL database name"
  default     = "appdb"
}

variable "postgres_storage_size" {
  type        = string
  description = "PostgreSQL persistent volume size"
  default     = "1Gi"

  validation {
    condition     = can(regex("^[0-9]+(Mi|Gi|Ti)$", var.postgres_storage_size))
    error_message = "Storage size must be in format like 1Gi, 500Mi, 2Ti."
  }
}

variable "postgres_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for PostgreSQL"
  default = {
    requests = {
      cpu    = "250m"
      memory = "256Mi"
    }
    limits = {
      cpu    = "500m"
      memory = "512Mi"
    }
  }
}

variable "postgres_password_length" {
  type        = number
  description = "Length of the generated PostgreSQL password"
  default     = 16

  validation {
    condition     = var.postgres_password_length >= 12 && var.postgres_password_length <= 128
    error_message = "Password length must be between 12 and 128 characters."
  }
}

# REDIS CONFIGURATION
variable "redis_chart_version" {
  type        = string
  description = "Redis Helm Chart version"
  default     = "24.1.3"
}

variable "redis_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for Redis"
  default = {
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

# MIGRATION JOB CONFIGURATION

variable "migration_backoff_limit" {
  type        = number
  description = "Number of retries for migration job before marking as failed"
  default     = 3

  validation {
    condition     = var.migration_backoff_limit >= 0 && var.migration_backoff_limit <= 10
    error_message = "Backoff limit must be between 0 and 10."
  }
}

variable "migration_wait_for_completion" {
  type        = bool
  description = "Wait for migration job to complete during terraform apply"
  default     = false
}

variable "migration_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for migration job"
  default = {
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

# HELM CONFIGURATION

variable "helm_timeout" {
  type        = number
  description = "Timeout in seconds for Helm operations"
  default     = 300

  validation {
    condition     = var.helm_timeout >= 60 && var.helm_timeout <= 1800
    error_message = "Helm timeout must be between 60 and 1800 seconds."
  }
}

variable "helm_chart_path" {
  type        = string
  description = "Path to local Helm chart (relative to terraform directory)"
  default     = "../helm/rest-api"
}

# MONITORING & OBSERVABILITY

variable "enable_metrics" {
  type        = bool
  description = "Enable Prometheus metrics for PostgreSQL"
  default     = false
}

# RESOURCE TAGGING

variable "common_labels" {
  type        = map(string)
  description = "Common labels to apply to all resources"
  default = {
    managed-by = "terraform"
  }
}

# FEATURE FLAGS

variable "enable_autoscaling" {
  type        = bool
  description = "Enable horizontal pod autoscaling"
  default     = false
}

variable "enable_ingress" {
  type        = bool
  description = "Enable ingress for external access"
  default     = false
}


# USER SERVICE (EXTERNAL)
variable "user_service_url" {
  type        = string
  description = "URL for Team 1's User Service API"
  default     = "http://user-service.user-service.svc.cluster.local:8000"
}


# KAFKA CONFIGURATION (Strimzi)

variable "kafka_resources" {
  type = object({
    requests = object({
      cpu    = string
      memory = string
    })
    limits = object({
      cpu    = string
      memory = string
    })
  })
  description = "Resource requests and limits for Kafka brokers"
  default = {
    requests = {
      cpu    = "200m"
      memory = "512Mi"
    }
    limits = {
      cpu    = "400m"
      memory = "1Gi"
    }
  }
}
