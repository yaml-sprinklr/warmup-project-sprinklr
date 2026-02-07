# Data source to read Elasticsearch secret from elastic-system namespace
data "kubernetes_secret_v1" "elasticsearch_user" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "order-service-es-es-elastic-user"
    namespace = "elastic-system"
  }

  depends_on = [kubernetes_manifest.elasticsearch_cluster]
}

# Copy Elasticsearch secret to order-service namespace
# Filebeat needs access to Elasticsearch credentials
resource "kubernetes_secret_v1" "elasticsearch_user_copy" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "order-service-es-es-elastic-user"
    namespace = var.namespace
    labels = {
      app = "filebeat"
    }
  }

  data = data.kubernetes_secret_v1.elasticsearch_user[0].data
  type = "Opaque"

  depends_on = [data.kubernetes_secret_v1.elasticsearch_user]
}

# Filebeat ServiceAccount
resource "kubernetes_service_account" "filebeat" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "filebeat"
    namespace = var.namespace
    labels = {
      app = "filebeat"
    }
  }
}

# Filebeat ClusterRole for Kubernetes metadata enrichment
resource "kubernetes_cluster_role" "filebeat" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name = "filebeat"
    labels = {
      app = "filebeat"
    }
  }

  rule {
    api_groups = [""]
    resources  = ["pods", "namespaces", "nodes"]
    verbs      = ["get", "list", "watch"]
  }
}

# Bind Filebeat ServiceAccount to ClusterRole
resource "kubernetes_cluster_role_binding" "filebeat" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name = "filebeat"
    labels = {
      app = "filebeat"
    }
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.filebeat[0].metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.filebeat[0].metadata[0].name
    namespace = var.namespace
  }
}

# Filebeat ConfigMap
# Collects logs from all pods and ships to Elasticsearch
resource "kubernetes_config_map" "filebeat_config" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "filebeat-config"
    namespace = var.namespace
    labels = {
      app = "filebeat"
    }
  }

  data = {
    "filebeat.yml" = <<-EOT
      # Filebeat configuration for order-service logs
      filebeat.inputs:
      - type: filestream
        id: ${var.app_name}-logs
        paths:
          - /var/log/pods/${var.namespace}_*/*/*.log

        # Parse container logs (CRI format), then decode JSON if present
        parsers:
          - container: ~

        # Add Kubernetes metadata
        processors:
          - add_kubernetes_metadata:
              host: $${NODE_NAME}
              matchers:
              - logs_path:
                  logs_path: "/var/log/pods/"

          # Decode JSON only when the message looks like JSON
          - decode_json_fields:
              fields: ["message"]
              target: ""
              overwrite_keys: true
              add_error_key: true
              when:
                regexp:
                  message: '^\{'

          # Drop Filebeat's own logs
          - drop_event:
              when:
                equals:
                  kubernetes.container.name: "filebeat"

          - add_cloud_metadata: ~
          - add_host_metadata: ~

      # Elasticsearch output
      output.elasticsearch:
        hosts: ["https://order-service-es-es-http.${kubernetes_namespace.elastic_system[0].metadata[0].name}.svc.cluster.local:9200"]
        index: "order-service-%%{+yyyy.MM.dd}"
        username: "elastic"
        password: "$${ELASTICSEARCH_PASSWORD}"
        ssl:
          enabled: true
          verification_mode: none
        ilm:
          enabled: true
          rollover_alias: "order-service"
          pattern: "{now/d}-000001"
          policy_name: "order-service-logs"

      # Setup template configuration (required for custom index)
      setup.template.name: "order-service"
      setup.template.pattern: "order-service-*"
      setup.template.enabled: true
      setup.template.overwrite: false

      logging:
        level: info
        to_stderr: true
        json: true

      monitoring:
        enabled: false

      http:
        enabled: true
        host: 0.0.0.0
        port: 5066
    EOT
  }

  depends_on = [kubernetes_manifest.elasticsearch_cluster]
}

# Filebeat DaemonSet
# Runs on every node to collect logs
resource "kubernetes_daemonset" "filebeat" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "filebeat"
    namespace = var.namespace
    labels = {
      app = "filebeat"
    }
  }

  spec {
    selector {
      match_labels = {
        app = "filebeat"
      }
    }

    template {
      metadata {
        labels = {
          app = "filebeat"
        }
      }

      spec {
        service_account_name            = kubernetes_service_account.filebeat[0].metadata[0].name
        termination_grace_period_seconds = 30
        host_network                     = true
        dns_policy                       = "ClusterFirstWithHostNet"

        # ARM64 node selector
        node_selector = {
          "kubernetes.io/arch" = "arm64"
        }

        container {
          name  = "filebeat"
          image = "docker.elastic.co/beats/filebeat:8.16.1"
          args  = ["-c", "/etc/filebeat.yml", "-e"]

          env {
            name  = "ELASTICSEARCH_PASSWORD"
            value_from {
              secret_key_ref {
                name = "order-service-es-es-elastic-user"
                key  = "elastic"
              }
            }
          }

          env {
            name = "NODE_NAME"
            value_from {
              field_ref {
                field_path = "spec.nodeName"
              }
            }
          }

          resources {
            limits = {
              memory = "200Mi"
              cpu    = "100m"
            }
            requests = {
              cpu    = "50m"
              memory = "100Mi"
            }
          }

          security_context {
            run_as_user = 0
            privileged  = false
            capabilities {
              drop = ["ALL"]
              add  = ["DAC_READ_SEARCH"]
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/filebeat.yml"
            read_only  = true
            sub_path   = "filebeat.yml"
          }

          volume_mount {
            name       = "data"
            mount_path = "/usr/share/filebeat/data"
          }

          volume_mount {
            name       = "varlibdockercontainers"
            mount_path = "/var/lib/docker/containers"
            read_only  = true
          }

          volume_mount {
            name       = "varlog"
            mount_path = "/var/log"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 5066
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 5066
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }
        }

        volume {
          name = "config"
          config_map {
            name         = kubernetes_config_map.filebeat_config[0].metadata[0].name
            default_mode = "0600"
          }
        }

        volume {
          name = "varlibdockercontainers"
          host_path {
            path = "/var/lib/docker/containers"
          }
        }

        volume {
          name = "varlog"
          host_path {
            path = "/var/log"
          }
        }

        volume {
          name = "data"
          host_path {
            path = "/var/lib/filebeat-data"
            type = "DirectoryOrCreate"
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_config_map.filebeat_config,
    kubernetes_secret_v1.elasticsearch_user_copy,
    kubernetes_manifest.elasticsearch_cluster,
    kubernetes_service_account.filebeat,
    kubernetes_cluster_role_binding.filebeat
  ]
}
