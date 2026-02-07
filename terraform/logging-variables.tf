# Logging Infrastructure Variables
# Optimized for ARM Mac with Rancher Desktop (minimal resources)

variable "elasticsearch_node_count" {
  description = "Number of Elasticsearch nodes"
  type        = number
  default     = 1  # Single node for local development
}

variable "elasticsearch_storage_size" {
  description = "Storage size per Elasticsearch node"
  type        = string
  default     = "5Gi"  # Minimal storage for local dev
}

variable "elasticsearch_memory" {
  description = "Memory allocation per Elasticsearch node"
  type        = string
  default     = "1Gi"  # Conservative for ARM Mac
}

variable "elasticsearch_cpu" {
  description = "CPU allocation per Elasticsearch node"
  type        = string
  default     = "500m"  # Half a core
}

variable "log_retention_days" {
  description = "Number of days to retain logs before deletion"
  type        = number
  default     = 7  # 1 week for local dev (vs 30 for prod)
}

variable "kibana_memory" {
  description = "Memory allocation for Kibana"
  type        = string
  default     = "512Mi"  # Minimal for local dev
}

variable "kibana_cpu" {
  description = "CPU allocation for Kibana"
  type        = string
  default     = "250m"
}

variable "kibana_ingress_enabled" {
  description = "Enable Kibana ingress"
  type        = bool
  default     = false  # Use port-forward for local dev
}

variable "kibana_hostname" {
  description = "Hostname for Kibana ingress"
  type        = string
  default     = "kibana.local"
}

variable "deploy_logging_stack" {
  description = "Enable/disable logging stack deployment"
  type        = bool
  default     = true
}
