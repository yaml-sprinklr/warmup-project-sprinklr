# Terraform TODO — Dead Code & Cleanup Items

## 1. ILM Policy ConfigMap (logging.tf) — Dead Code

**Resource:** `kubernetes_manifest.ilm_policy`

Creates a ConfigMap `elasticsearch-ilm-policy` in `elastic-system` with ILM policy JSON, but **nothing applies it to Elasticsearch**. A ConfigMap is just K8s storage — configuring an ES ILM policy requires a `PUT _ilm/policy/<name>` API call.

Currently, `filebeat setup --index-management` (in the filebeat-setup Job) creates Filebeat's default ILM policy automatically. The ConfigMap is never consumed.

**To make functional:** Replace with a `terraform_data` resource that runs:
```bash
curl -sk -u elastic:$ES_PASSWORD -XPUT \
  "https://order-service-es-es-http.elastic-system.svc:9200/_ilm/policy/order-service-logs" \
  -H 'Content-Type: application/json' \
  -d @ilm-policy.json
```

---

## 2. Index Template ConfigMap (logging.tf) — Dead Code

**Resource:** `kubernetes_manifest.index_template`

Creates a ConfigMap `elasticsearch-index-template` with explicit field mappings (e.g., `order_id: keyword`, `duration_ms: float`, `trace_id: keyword`). **Nothing reads or applies this to Elasticsearch.**

This is the most impactful dead code — without these explicit mappings, Elasticsearch uses dynamic mapping, which means:
- `duration_ms` may be mapped as `long` instead of `float`
- `trace_id` could be mapped as `text` instead of `keyword` (breaks exact-match filters in Kibana)
- No control over shard count or replica settings

**To make functional:** Replace with a `terraform_data` resource or a K8s Job that applies the index template via:
```bash
curl -sk -u elastic:$ES_PASSWORD -XPUT \
  "https://order-service-es-es-http.elastic-system.svc:9200/_index_template/order-service" \
  -H 'Content-Type: application/json' \
  -d @index-template.json
```

---

## 3. Kibana Saved Search ConfigMaps (kibana-saved-searches.tf) — Dead Code

**Resources:**
- `kubernetes_config_map.kibana_saved_search_errors`
- `kubernetes_config_map.kibana_saved_search_slow_requests`
- `kubernetes_config_map.kibana_saved_search_trace_lookup`

Three ConfigMaps containing NDJSON saved search definitions for Kibana. **Nothing imports them into Kibana.** The file comments acknowledge this: _"To import them into Kibana, you can either use the UI or API."_

The saved searches defined:
1. **All ERROR logs (last 1h)** — `level:ERROR` query
2. **Slow requests (>1000ms)** — `duration_ms:>1000` query
3. **Trace ID lookup** — Template for `trace_id:"..."` query

**To make functional:** Add a K8s Job that waits for Kibana readiness, then imports via:
```bash
curl -sk -u elastic:$ES_PASSWORD -XPOST \
  "https://order-service-kibana-kb-http.elastic-system.svc:5601/api/saved_objects/_import" \
  -H 'kbn-xsrf: true' \
  --form file=@saved-searches.ndjson
```

---

## 4. Duplicate Namespace Variable (monitoring-variables.tf)

`var.order_service_namespace` (default: `"order-service"`) duplicates `var.namespace` (default: `"order-service"`). Used in `monitoring.tf` for ServiceMonitor/PodMonitor namespace selectors.

**Risk:** If someone changes `var.namespace` but not `var.order_service_namespace`, monitoring breaks silently.

**Decision:** Keeping separate for now. Consider consolidating if this causes issues.
