resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      name = "monitoring"
    }
  }
}

resource "helm_release" "kube_prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "81.4.3"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  # Wait for resources to be ready
  wait          = true
  wait_for_jobs = true
  timeout       = 600

  # Prometheus configuration
  # Global defaults (can be overridden per-ServiceMonitor)
  set {
    name  = "prometheus.prometheusSpec.scrapeInterval"
    value = "15s"  # Default scrape frequency
  }

  set {
    name  = "prometheus.prometheusSpec.evaluationInterval"
    value = "30s"  # How often to evaluate alert rules
  }

  set {
    name  = "prometheus.prometheusSpec.retention"
    value = var.prometheus_retention
  }

  set {
    name  = "prometheus.prometheusSpec.retentionSize"
    value = var.prometheus_retention_size
  }

  # Service Monitor selector - must match our ServiceMonitor labels
  set {
    name  = "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues"
    value = "false"
  }

  set {
    name  = "prometheus.prometheusSpec.serviceMonitorSelector.matchLabels.prometheus"
    value = "kube-prometheus"
  }

  # Allow ServiceMonitors in the Order Service namespace
  set {
    name  = "prometheus.prometheusSpec.serviceMonitorNamespaceSelector.matchNames[0]"
    value = var.order_service_namespace
  }

  # PodMonitor selector - must match our PodMonitor labels
  set {
    name  = "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues"
    value = "false"
  }

  set {
    name  = "prometheus.prometheusSpec.podMonitorSelector.matchLabels.prometheus"
    value = "kube-prometheus"
  }

  # Allow PodMonitors in the Order Service namespace
  set {
    name  = "prometheus.prometheusSpec.podMonitorNamespaceSelector.matchNames[0]"
    value = var.order_service_namespace
  }

  # PrometheusRule selector - must match our PrometheusRule labels
  set {
    name  = "prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues"
    value = "false"
  }

  set {
    name  = "prometheus.prometheusSpec.ruleSelector.matchLabels.prometheus"
    value = "kube-prometheus"
  }

  # Resource limits for Prometheus
  set {
    name  = "prometheus.prometheusSpec.resources.requests.memory"
    value = "2Gi"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.requests.cpu"
    value = "500m"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.limits.memory"
    value = "4Gi"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.limits.cpu"
    value = "2000m"
  }

  # Storage for Prometheus
  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]"
    value = "ReadWriteOnce"
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage"
    value = var.prometheus_storage_size
  }

  # Grafana configuration
  set {
    name  = "grafana.enabled"
    value = "true"
  }

  set_sensitive {
    name  = "grafana.adminPassword"
    value = var.grafana_admin_password
  }

  # Grafana resources
  set {
    name  = "grafana.resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "grafana.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "grafana.resources.limits.memory"
    value = "512Mi"
  }

  set {
    name  = "grafana.resources.limits.cpu"
    value = "500m"
  }

  # Grafana ingress (optional)
  set {
    name  = "grafana.ingress.enabled"
    value = var.grafana_ingress_enabled
  }

  dynamic "set" {
    for_each = var.grafana_ingress_enabled ? [1] : []
    content {
      name  = "grafana.ingress.ingressClassName"
      value = "nginx"
    }
  }

  dynamic "set" {
    for_each = var.grafana_ingress_enabled ? [1] : []
    content {
      name  = "grafana.ingress.hosts[0]"
      value = var.grafana_hostname
    }
  }

  # Alertmanager configuration
  set {
    name  = "alertmanager.enabled"
    value = "true"
  }

  # Node exporter
  set {
    name  = "nodeExporter.enabled"
    value = "true"
  }

  # Kube state metrics
  set {
    name  = "kubeStateMetrics.enabled"
    value = "true"
  }

  # Default rules
  set {
    name  = "defaultRules.create"
    value = "true"
  }

  # Custom values file for complex configurations
  values = [
    file("${path.module}/monitoring-values.yaml")
  ]

  depends_on = [kubernetes_namespace.monitoring]
}

# Order Service ServiceMonitor
resource "kubernetes_manifest" "order_service_servicemonitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "order-service-api"
      namespace = var.order_service_namespace
      labels = {
        app        = "order-service"
        component  = "api"
        prometheus = "kube-prometheus"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          app       = "order-service"
          component = "api"
        }
      }
      namespaceSelector = {
        matchNames = [var.order_service_namespace]
      }
      endpoints = [
        {
          port          = "http"
          path          = "/metrics"
          interval      = "15s"
          scrapeTimeout = "10s"
          relabelings = [
            {
              sourceLabels = ["__meta_kubernetes_pod_name"]
              targetLabel  = "pod"
            },
            {
              sourceLabels = ["__meta_kubernetes_namespace"]
              targetLabel  = "namespace"
            },
            {
              targetLabel = "service"
              replacement = "order-service"
            },
            {
              targetLabel = "component"
              replacement = "api"
            }
          ]
        }
      ]
    }
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Outbox Worker ServiceMonitor
resource "kubernetes_manifest" "order_service_outbox_worker_servicemonitor" {
  count = var.deploy_outbox_worker_monitor ? 1 : 0

  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "order-service-outbox-worker"
      namespace = var.order_service_namespace
      labels = {
        app        = "order-service"
        component  = "outbox-worker"
        prometheus = "kube-prometheus"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          app       = "order-service"
          component = "outbox-worker"
        }
      }
      namespaceSelector = {
        matchNames = [var.order_service_namespace]
      }
      endpoints = [
        {
          port          = "http"
          path          = "/metrics"
          interval      = "15s"
          scrapeTimeout = "10s"
          relabelings = [
            {
              sourceLabels = ["__meta_kubernetes_pod_name"]
              targetLabel  = "pod"
            },
            {
              sourceLabels = ["__meta_kubernetes_namespace"]
              targetLabel  = "namespace"
            },
            {
              targetLabel = "service"
              replacement = "order-service"
            },
            {
              targetLabel = "component"
              replacement = "outbox-worker"
            }
          ]
        }
      ]
    }
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Postgres ServiceMonitor
resource "kubernetes_manifest" "postgres_servicemonitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "postgres-postgresql"
      namespace = var.order_service_namespace
      labels = {
        prometheus = "kube-prometheus"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          "app.kubernetes.io/instance" = "${helm_release.postgresql.name}"
        }
      }
      namespaceSelector = {
        matchNames = [var.order_service_namespace]
      }
      endpoints = [
        {
          port          = "http-metrics"   # use actual port name or number
          path          = "/metrics"
          interval      = "15s"
          scrapeTimeout = "10s"
        }
      ]
    }
  }

  depends_on = [helm_release.kube_prometheus_stack, helm_release.postgresql]
}

# Strimzi Kafka PodMonitor (metrics reporter exposes metrics on pod ports)
resource "kubernetes_manifest" "strimzi_kafka_podmonitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "PodMonitor"
    metadata = {
      name      = "strimzi-kafka"
      namespace = var.order_service_namespace
      labels = {
        prometheus = "kube-prometheus"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          "strimzi.io/cluster" = "${var.app_name}-kafka"
          "strimzi.io/kind"    = "Kafka"
          "strimzi.io/name"    = "${var.app_name}-kafka-kafka"
        }
      }
      namespaceSelector = {
        matchNames = [var.order_service_namespace]
      }
      podMetricsEndpoints = [
        {
          port          = "tcp-prometheus"
          path          = "/metrics"
          interval      = "15s"
          scrapeTimeout = "10s"
          relabelings = [
            {
              sourceLabels = ["__meta_kubernetes_pod_name"]
              targetLabel  = "kubernetes_pod_name"
            },
            {
              sourceLabels = ["__meta_kubernetes_pod_name"]
              targetLabel  = "pod"
            },
            {
              sourceLabels = ["__meta_kubernetes_namespace"]
              targetLabel  = "namespace"
            },
            {
              sourceLabels = ["__meta_kubernetes_pod_label_strimzi_io_cluster"]
              targetLabel  = "strimzi_io_cluster"
            },
            {
              sourceLabels = ["__meta_kubernetes_pod_label_strimzi_io_name"]
              targetLabel  = "strimzi_io_name"
            }
          ]
        }
      ]
    }
  }

  depends_on = [helm_release.kube_prometheus_stack, kubernetes_manifest.kafka_cluster]
}

# Custom alert rules
resource "kubernetes_manifest" "order_service_alerts" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "PrometheusRule"
    metadata = {
      name      = "order-service-alerts"
      namespace = kubernetes_namespace.monitoring.metadata[0].name
      labels = {
        prometheus = "kube-prometheus"
        role       = "alert-rules"
      }
    }
    spec = {
      groups = [
        {
          name     = "order-service"
          interval = "30s"
          rules = [
            # High error rate
            {
              alert = "OrderServiceHighErrorRate"
              expr  = <<-EOT
                (sum(rate(http_requests_total{service="order-service",status_code=~"5xx"}[5m])) 
                / sum(rate(http_requests_total{service="order-service"}[5m]))) * 100 > 5
              EOT
              for   = "2m"
              labels = {
                severity = "critical"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service has high error rate"
                description = "Error rate is {{ $value }}% (threshold: 5%)"
              }
            },
            # High latency
            {
              alert = "OrderServiceHighLatency"
              expr  = <<-EOT
                histogram_quantile(0.95, 
                  sum(rate(http_request_duration_seconds_bucket{service="order-service"}[5m])) by (le)
                ) > 1
              EOT
              for   = "5m"
              labels = {
                severity = "warning"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service has high latency"
                description = "P95 latency is {{ $value }}s (threshold: 1s)"
              }
            },
            # Consumer lag critical
            {
              alert = "OrderServiceConsumerLagCritical"
              expr  = "kafka_consumer_lag_messages{service=\"order-service\"} > 10000"
              for   = "5m"
              labels = {
                severity = "critical"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service consumer lag is critical"
                description = "Consumer lag is {{ $value }} messages (threshold: 10000)"
              }
            },
            # Outbox backlog
            {
              alert = "OrderServiceOutboxBacklog"
              expr  = "outbox_events_pending{service=\"order-service\"} > 5000"
              for   = "10m"
              labels = {
                severity = "critical"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service outbox has large backlog"
                description = "{{ $value }} events pending in outbox (threshold: 5000)"
              }
            },
            # Database connection pool exhausted
            {
              alert = "OrderServiceDBPoolExhausted"
              expr  = "db_pool_waiters{service=\"order-service\"} > 0"
              for   = "2m"
              labels = {
                severity = "critical"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service database connection pool exhausted"
                description = "{{ $value }} threads waiting for DB connections"
              }
            },
            # Background task down
            {
              alert = "OrderServiceBackgroundTaskDown"
              expr  = "background_tasks_running{service=\"order-service\"} == 0"
              for   = "1m"
              labels = {
                severity = "critical"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service background task is down"
                description = "Task {{ $labels.task_name }} is not running"
              }
            },
            # Redis errors
            {
              alert = "OrderServiceRedisErrors"
              expr  = "rate(redis_errors_total{service=\"order-service\"}[5m]) > 0"
              for   = "2m"
              labels = {
                severity = "warning"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service experiencing Redis errors"
                description = "Redis error rate: {{ $value }}/sec"
              }
            },
            # Low cache hit rate
            {
              alert = "OrderServiceLowCacheHitRate"
              expr  = <<-EOT
                (sum(rate(cache_hits_total{service="order-service"}[5m])) 
                / (sum(rate(cache_hits_total{service="order-service"}[5m])) 
                  + sum(rate(cache_misses_total{service="order-service"}[5m])))) * 100 < 50
              EOT
              for   = "10m"
              labels = {
                severity = "warning"
                service  = "order-service"
              }
              annotations = {
                summary     = "Order Service cache hit rate is low"
                description = "Cache hit rate is {{ $value }}% (threshold: 50%)"
              }
            }
          ]
        }
      ]
    }
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Grafana Dashboard ConfigMap
resource "kubernetes_config_map" "grafana_dashboard" {
  metadata {
    name      = "order-service-dashboard"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels = {
      grafana_dashboard = "1"
    }
  }

  data = {
    "order-service-dashboard.json" = file("${path.module}/grafana/dashboards/order-service-dashboard.json")
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Grafana Dashboard ConfigMap (Postgres)
resource "kubernetes_config_map" "grafana_postgres_dashboard" {
  metadata {
    name      = "postgres-dashboard"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels = {
      grafana_dashboard = "1"
    }
  }

  data = {
    "postgres-dashboard.json" = file("${path.module}/grafana/dashboards/postgres-dashboard.json")
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Grafana Dashboard ConfigMap (Strimzi Kafka)
resource "kubernetes_config_map" "grafana_strimzi_kafka_dashboard" {
  metadata {
    name      = "strimzi-kafka-dashboard"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels = {
      grafana_dashboard = "1"
    }
  }

  data = {
    "strimzi-kafka-dashboard.json" = file("${path.module}/grafana/dashboards/strimzi-kafka-dashboard.json")
  }

  depends_on = [helm_release.kube_prometheus_stack]
}

# Outputs
output "grafana_admin_password" {
  value     = var.grafana_admin_password
  sensitive = true
}

output "prometheus_endpoint" {
  value = "kubectl port-forward -n ${kubernetes_namespace.monitoring.metadata[0].name} svc/kube-prometheus-stack-prometheus 9090:9090"
}

output "grafana_endpoint" {
  value = "kubectl port-forward -n ${kubernetes_namespace.monitoring.metadata[0].name} svc/kube-prometheus-stack-grafana 3000:80"
}

output "alertmanager_endpoint" {
  value = "kubectl port-forward -n ${kubernetes_namespace.monitoring.metadata[0].name} svc/kube-prometheus-stack-alertmanager 9093:9093"
}
