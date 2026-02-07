# Kibana Saved Searches Configuration
# These are imported into Kibana via the UI or API

# Saved Search 1: All ERROR logs (last 1h)
resource "kubernetes_config_map" "kibana_saved_search_errors" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "kibana-saved-search-errors"
    namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    labels = {
      app = "kibana-config"
    }
  }

  data = {
    "errors-last-1h.ndjson" = <<-EOT
      {"attributes":{"title":"All ERROR logs (last 1h)","description":"Quick overview of all errors in the last hour","hits":0,"columns":["timestamp","message","trace.id","error_type","error_message","service_name"],"sort":[["timestamp","desc"]],"version":1,"kibanaSavedObjectMeta":{"searchSourceJSON":"{\"query\":{\"query\":\"level:ERROR\",\"language\":\"kuery\"},\"filter\":[],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"}},"references":[{"name":"kibanaSavedObjectMeta.searchSourceJSON.index","type":"index-pattern","id":"order-service-*"}],"migrationVersion":{"search":"7.9.3"},"type":"search"}
    EOT
  }

  depends_on = [terraform_data.kibana_instance]
}

# Saved Search 2: Slow requests
resource "kubernetes_config_map" "kibana_saved_search_slow_requests" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "kibana-saved-search-slow-requests"
    namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    labels = {
      app = "kibana-config"
    }
  }

  data = {
    "slow-requests.ndjson" = <<-EOT
      {"attributes":{"title":"Slow requests (>1000ms)","description":"Find requests taking longer than 1 second","hits":0,"columns":["timestamp","http.request.method","url.path","duration_ms","http.response.status_code","trace.id"],"sort":[["duration_ms","desc"]],"version":1,"kibanaSavedObjectMeta":{"searchSourceJSON":"{\"query\":{\"query\":\"duration_ms:>1000\",\"language\":\"kuery\"},\"filter\":[],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"}},"references":[{"name":"kibanaSavedObjectMeta.searchSourceJSON.index","type":"index-pattern","id":"order-service-*"}],"migrationVersion":{"search":"7.9.3"},"type":"search"}
    EOT
  }

  depends_on = [terraform_data.kibana_instance]
}

# Saved Search 3: Trace ID lookup template
resource "kubernetes_config_map" "kibana_saved_search_trace_lookup" {
  count = var.deploy_logging_stack ? 1 : 0

  metadata {
    name      = "kibana-saved-search-trace-lookup"
    namespace = kubernetes_namespace.elastic_system[0].metadata[0].name
    labels = {
      app = "kibana-config"
    }
  }

  data = {
    "trace-lookup.ndjson" = <<-EOT
      {"attributes":{"title":"Trace ID lookup","description":"Template for looking up all logs for a specific trace.id. Replace the trace.id value with your actual trace ID.","hits":0,"columns":["timestamp","service_name","message","span.id","parent_span_id","http.request.method","url.path","order_id","user_id"],"sort":[["timestamp","asc"]],"version":1,"kibanaSavedObjectMeta":{"searchSourceJSON":"{\"query\":{\"query\":\"trace.id:\\\"REPLACE_WITH_ACTUAL_TRACE_ID\\\"\",\"language\":\"kuery\"},\"filter\":[],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"}},"references":[{"name":"kibanaSavedObjectMeta.searchSourceJSON.index","type":"index-pattern","id":"order-service-*"}],"migrationVersion":{"search":"7.9.3"},"type":"search"}
    EOT
  }

  depends_on = [terraform_data.kibana_instance]
}

# Note: These ConfigMaps contain the saved search definitions
# To import them into Kibana, you can either:
# 1. Use Kibana's UI: Stack Management → Saved Objects → Import
# 2. Use Kibana API (requires scripting)
# 3. Manually recreate them using the queries in the logging runbook

# For automated import, you would need a Job that runs after Kibana is ready
# and uses the Kibana API to import these saved objects
