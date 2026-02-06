# Monitoring stack variables

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "grafana_ingress_enabled" {
  description = "Enable Grafana ingress"
  type        = bool
  default     = false
}

variable "grafana_hostname" {
  description = "Hostname for Grafana ingress"
  type        = string
  default     = "grafana.local"
}

variable "order_service_namespace" {
  description = "Namespace where Order Service is deployed"
  type        = string
  default     = "order-service"
}

variable "deploy_outbox_worker_monitor" {
  description = "Deploy ServiceMonitor for outbox worker"
  type        = bool
  default     = true
}

variable "prometheus_retention" {
  description = "How long to retain Prometheus data"
  type        = string
  default     = "30d"
}

variable "prometheus_retention_size" {
  description = "Maximum size of Prometheus data (e.g., 50GB)"
  type        = string
  default     = "50GB"
}

variable "prometheus_storage_size" {
  description = "Storage size for Prometheus PVC (e.g., 50Gi)"
  type        = string
  default     = "50Gi"
}
