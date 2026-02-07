# Logging Infrastructure with Elasticsearch and Kibana
# Optimized for ARM Mac with Rancher Desktop
#
# Architecture:
# - ECK Operator manages Elasticsearch and Kibana
# - Single-node Elasticsearch (1GB RAM, 5GB storage)
# - Kibana for log visualization
# - Filebeat deployed via Helm chart (in helm/rest-api)

# Create namespace for Elastic stack
resource "kubernetes_namespace" "elastic_system" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name = "elastic-system"
    labels = {
      name = "elastic-system"
    }
  }
}

# Install ECK (Elastic Cloud on Kubernetes) Operator
# This operator manages Elasticsearch and Kibana lifecycle
resource "helm_release" "eck_operator" {
  count = var.deploy_logging_stack ? 1 : 0

  name       = "elastic-operator"
  repository = "https://helm.elastic.co"
  chart      = "eck-operator"
  version    = "2.15.0"  # Latest stable version
  namespace  = kubernetes_namespace.elastic_system[0].metadata[0].name

  wait          = true
  wait_for_jobs = true
  timeout       = 300

  # Resource limits for operator (very lightweight)
  set {
    name  = "resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "resources.limits.memory"
    value = "150Mi"
  }

  set {
    name  = "resources.requests.cpu"
    value = "50m"
  }

  set {
    name  = "resources.requests.memory"
    value = "100Mi"
  }

  depends_on = [kubernetes_namespace.elastic_system]
}

# Elasticsearch Cluster
# Single-node cluster optimized for ARM Mac
resource "kubernetes_manifest" "elasticsearch_cluster" {
  count = var.deploy_logging_stack ? 1 : 0

  field_manager {
    force_conflicts = true
  }

  manifest = {
    apiVersion = "elasticsearch.k8s.elastic.co/v1"
    kind       = "Elasticsearch"
    metadata = {
      name      = "order-service-es"
      namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    }
    spec = {
      version = "8.16.1"  # Latest 8.x version with ARM support

      # Single-node cluster (no high availability for local dev)
      nodeSets = [
        {
          name  = "default"
          count = var.elasticsearch_node_count

          config = {
            # Disable machine learning (saves resources)
            "node.roles" = ["master", "data", "ingest"]
            "xpack.ml.enabled" = false

            # Reduce memory usage
            "indices.memory.index_buffer_size" = "128mb"
            "indices.queries.cache.size" = "5%"
          }

          podTemplate = {
            spec = {
              # ARM64 architecture support
              nodeSelector = {
                "kubernetes.io/arch" = "arm64"
              }

              containers = [
                {
                  name = "elasticsearch"

                  # Resource limits (conservative for ARM Mac)
                  resources = {
                    requests = {
                      memory = var.elasticsearch_memory
                      cpu    = var.elasticsearch_cpu
                    }
                    limits = {
                      memory = var.elasticsearch_memory
                      cpu    = "1000m"  # Allow bursting to 1 core
                    }
                  }

                  # JVM heap size (50% of container memory)
                  env = [
                    {
                      name  = "ES_JAVA_OPTS"
                      value = "-Xms512m -Xmx512m"
                    }
                  ]
                }
              ]
            }
          }

          # Persistent storage
          volumeClaimTemplates = [
            {
              metadata = {
                name = "elasticsearch-data"
              }
              spec = {
                accessModes = ["ReadWriteOnce"]
                resources = {
                  requests = {
                    storage = var.elasticsearch_storage_size
                  }
                }
              }
            }
          ]
        }
      ]
    }
  }

  depends_on = [helm_release.eck_operator]
}

# Kibana Instance
# Uses terraform_data + kubectl apply instead of kubernetes_manifest
# to avoid the "Provider produced inconsistent result after apply" bug
# with ECK CRDs in the hashicorp/kubernetes provider.
resource "terraform_data" "kibana_instance" {
  count = var.deploy_logging_stack ? 1 : 0

  triggers_replace = [
    var.kibana_memory,
    var.kibana_cpu,
    kubernetes_namespace.elastic_system[0].metadata[0].name,
  ]

  provisioner "local-exec" {
    command = <<-EOT
cat > /tmp/tf-kibana-cr.yaml <<'KIBANA_YAML'
apiVersion: kibana.k8s.elastic.co/v1
kind: Kibana
metadata:
  name: order-service-kibana
  namespace: ${kubernetes_namespace.elastic_system[0].metadata[0].name}
spec:
  version: "8.16.1"
  count: 1
  elasticsearchRef:
    name: order-service-es
  podTemplate:
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
      - name: kibana
        resources:
          requests:
            memory: "${var.kibana_memory}"
            cpu: "${var.kibana_cpu}"
          limits:
            memory: "1Gi"
            cpu: "500m"
        env:
        - name: NODE_OPTIONS
          value: "--max-old-space-size=384"
  config:
    telemetry.enabled: false
    telemetry.optIn: false
    logging.root.level: warn
KIBANA_YAML
kubectl apply -f /tmp/tf-kibana-cr.yaml
kubectl wait --for=jsonpath='{.status.health}'=green kibana/order-service-kibana -n ${kubernetes_namespace.elastic_system[0].metadata[0].name} --timeout=300s || true
rm -f /tmp/tf-kibana-cr.yaml
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = "kubectl delete kibana order-service-kibana -n elastic-system --ignore-not-found"
  }

  depends_on = [kubernetes_manifest.elasticsearch_cluster]
}

# Index Lifecycle Management (ILM) Policy
# Automatically delete logs older than retention period
resource "kubernetes_manifest" "ilm_policy" {
  count = var.deploy_logging_stack ? 1 : 0

  manifest = {
    apiVersion = "v1"
    kind       = "ConfigMap"
    metadata = {
      name      = "elasticsearch-ilm-policy"
      namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    }
    data = {
      "ilm-policy.json" = jsonencode({
        policy = {
          phases = {
            hot = {
              actions = {
                rollover = {
                  max_age  = "1d"
                  max_size = "1gb"
                }
              }
            }
            delete = {
              min_age = "${var.log_retention_days}d"
              actions = {
                delete = {}
              }
            }
          }
        }
      })
    }
  }

  depends_on = [kubernetes_manifest.elasticsearch_cluster]
}

# Index Template for order-service logs
# Defines field mappings and settings for log indices
resource "kubernetes_manifest" "index_template" {
  count = var.deploy_logging_stack ? 1 : 0

  manifest = {
    apiVersion = "v1"
    kind       = "ConfigMap"
    metadata = {
      name      = "elasticsearch-index-template"
      namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    }
    data = {
      "index-template.json" = jsonencode({
        index_patterns = ["order-service-*"]
        template = {
          settings = {
            number_of_shards   = 1  # Single node, single shard
            number_of_replicas = 0  # No replicas for single node
            "index.lifecycle.name" = "order-service-logs"
          }
          mappings = {
            properties = {
              # Standard timestamp fields
              "@timestamp" = { type = "date" }
              timestamp    = { type = "date" }
              
              # Core logging fields
              level        = { type = "keyword" }
              message      = { type = "text" }
              service_name = { type = "keyword" }
              environment  = { type = "keyword" }
              version      = { type = "keyword" }

              # ECS Distributed tracing fields
              trace = {
                properties = {
                  id = { type = "keyword" }
                }
              }
              span = {
                properties = {
                  id = { type = "keyword" }
                }
              }
              parent_span_id = { type = "keyword" }
              request_id     = { type = "keyword" }

              # ECS HTTP fields
              http = {
                properties = {
                  request = {
                    properties = {
                      method = { type = "keyword" }
                    }
                  }
                  response = {
                    properties = {
                      status_code = { type = "integer" }
                    }
                  }
                }
              }
              
              # ECS URL fields
              url = {
                properties = {
                  path  = { type = "keyword" }
                  query = { type = "keyword" }
                }
              }
              
              # ECS Event fields
              event = {
                properties = {
                  duration = { type = "long" }  # nanoseconds
                }
              }
              
              # Keep duration_ms for readability
              duration_ms = { type = "float" }

              # ECS Client fields
              client = {
                properties = {
                  ip = { type = "ip" }
                }
              }
              
              # ECS User agent fields
              user_agent = {
                properties = {
                  original = { type = "keyword" }
                }
              }

              # Error fields
              error_type    = { type = "keyword" }
              error_message = { type = "text" }
              exception     = { type = "text" }

              # Business domain fields
              order_id   = { type = "keyword" }
              user_id    = { type = "keyword" }
              event_id   = { type = "keyword" }
              event_type = { type = "keyword" }

              # Kubernetes metadata (added by Filebeat)
              kubernetes = {
                properties = {
                  namespace = { type = "keyword" }
                  pod = {
                    properties = {
                      name = { type = "keyword" }
                    }
                  }
                  container = {
                    properties = {
                      name = { type = "keyword" }
                    }
                  }
                }
              }
            }
          }
        }
      })
    }
  }

  depends_on = [kubernetes_manifest.elasticsearch_cluster]
}

# Outputs
output "elasticsearch_endpoint" {
  value = var.deploy_logging_stack ? "kubectl port-forward -n ${kubernetes_namespace.elastic_system[0].metadata[0].name} svc/order-service-es-es-http 9200:9200" : "Logging stack not deployed"
}

output "kibana_endpoint" {
  value = var.deploy_logging_stack ? "kubectl port-forward -n ${kubernetes_namespace.elastic_system[0].metadata[0].name} svc/order-service-kibana-kb-http 5601:5601" : "Logging stack not deployed"
}

output "elasticsearch_password_command" {
  value = var.deploy_logging_stack ? "kubectl get secret order-service-es-es-elastic-user -n ${kubernetes_namespace.elastic_system[0].metadata[0].name} -o=jsonpath='{.data.elastic}' | base64 --decode" : "Logging stack not deployed"
}

output "kibana_url" {
  value = var.deploy_logging_stack ? "https://localhost:5601 (username: elastic, password: see elasticsearch_password_command)" : "Logging stack not deployed"
}
