# Filebeat Setup Job
# Runs 'filebeat setup' to create index patterns and load dashboards
resource "kubernetes_job_v1" "filebeat_setup" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "filebeat-setup"
    namespace = var.namespace
    labels = {
      app       = "filebeat-setup"
      component = "logging-init"
    }
  }

  spec {
    template {
      metadata {
        labels = {
          app = "filebeat-setup"
        }
      }

      spec {
        restart_policy = "OnFailure"

        container {
          name  = "filebeat-setup"
          image = "docker.elastic.co/beats/filebeat:8.16.1"

          # Run setup command
          args = [
            "setup",
            "--index-management", # Create index pattern
            "--dashboards",       # Load dashboards (if available)
            "-E", "output.elasticsearch.hosts=['order-service-es-es-http.${kubernetes_namespace.elastic_system[0].metadata[0].name}.svc.cluster.local:9200']",
            "-E", "output.elasticsearch.username=elastic",
            "-E", "output.elasticsearch.password=$(ELASTICSEARCH_PASSWORD)",
            "-E", "output.elasticsearch.ssl.enabled=true",
            "-E", "output.elasticsearch.ssl.verification_mode=none",
            "-E", "setup.kibana.host=order-service-kibana-kb-http.${kubernetes_namespace.elastic_system[0].metadata[0].name}.svc.cluster.local:5601"
          ]

          env {
            name = "ELASTICSEARCH_PASSWORD"
            value_from {
              secret_key_ref {
                name = "order-service-es-elastic-user"
                key  = "elastic"
              }
            }
          }

          resources {
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
      }
    }

    backoff_limit = 3
    ttl_seconds_after_finished = 300 # Clean up job after 5 minutes
  }

  depends_on = [
    kubernetes_manifest.elasticsearch_cluster,
    kubernetes_manifest.kibana_instance
  ]
}
