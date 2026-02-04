# NAMESPACE OUTPUTS

output "namespace_name" {
  description = "The Kubernetes namespace name"
  value       = kubernetes_namespace.order_service.metadata[0].name
}

output "namespace_id" {
  description = "The unique ID of the namespace"
  value       = kubernetes_namespace.order_service.id
}

# DATABASE OUTPUTS

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
  sensitive   = true
}

output "db_secret_name" {
  description = "The name of the Kubernetes secret containing DB credentials"
  value       = kubernetes_secret.db_credentials.metadata[0].name
}

# APPLICATION OUTPUTS

output "app_config_name" {
  description = "The name of the ConfigMap containing application configuration"
  value       = kubernetes_config_map.app_config.metadata[0].name
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

# MIGRATION OUTPUTS

output "migration_job_name" {
  description = "The name of the database migration job"
  value       = kubernetes_job_v1.db_migrations.metadata[0].name
}

# ACCESS INFORMATION

output "access_instructions" {
  description = "Instructions for accessing the order service"
  value = {
    environment = var.environment
    namespace   = kubernetes_namespace.order_service.metadata[0].name

    # Port forward command
    port_forward = "kubectl port-forward -n ${kubernetes_namespace.order_service.metadata[0].name} svc/${helm_release.order_service.name}-rest-api 8080:8000"

    # API endpoints to test
    health_check = "curl http://localhost:8080/api/v1/health/live"
    list_orders  = "curl http://localhost:8080/api/v1/orders"
    create_order = "curl -X POST http://localhost:8080/api/v1/orders -H 'Content-Type: application/json' -d '{\"user_id\": \"123e4567-e89b-12d3-a456-426614174000\", \"amount\": 100}'"

    # Useful kubectl commands
    get_pods            = "kubectl get pods -n ${kubernetes_namespace.order_service.metadata[0].name}"
    view_app_logs       = "kubectl logs -n ${kubernetes_namespace.order_service.metadata[0].name} -l app=${var.app_name} --tail=50"
    view_migration_logs = "kubectl logs -n ${kubernetes_namespace.order_service.metadata[0].name} -l component=migrations"
    check_migration     = "kubectl get job ${kubernetes_job_v1.db_migrations.metadata[0].name} -n ${kubernetes_namespace.order_service.metadata[0].name}"
  }
}

# ENVIRONMENT SUMMARY

output "deployment_summary" {
  description = "Summary of the deployed environment"
  value = {
    environment         = var.environment
    namespace           = var.namespace
    app_replicas        = var.app_replica_count
    app_image           = "${var.app_image_repository}:${var.app_image_tag}"
    database_size       = var.postgres_storage_size
    monitoring_enabled  = var.enable_metrics
    autoscaling_enabled = var.enable_autoscaling
  }
}
