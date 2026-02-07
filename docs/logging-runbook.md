# Order Service Logging Runbook

## Quick Start

### Accessing Kibana

1. **Port-forward to Kibana:**
   ```bash
   kubectl port-forward -n elastic-system svc/order-service-kibana-kb-http 5601:5601
   ```

2. **Get Elasticsearch password:**
   ```bash
   kubectl get secret order-service-es-elastic-user -n elastic-system -o=jsonpath='{.data.elastic}' | base64 --decode
   ```

3. **Open Kibana:**
   - URL: https://localhost:5601
   - Username: `elastic`
   - Password: (from step 2)
   - Accept the self-signed certificate warning

4. **Navigate to Discover:**
   - Click hamburger menu (☰) → Analytics → Discover
   - Select index pattern: `order-service-*`

---

## Finding Problems

### 1. View All Errors (Last Hour)

**Kibana Query:**
```
level:ERROR
```

**Time Range:** Last 1 hour

**Useful Fields to Display:**
- `timestamp`
- `message`
- `trace_id`
- `error_type`
- `error_message`
- `service_name`

**Use Case:** Quick health check, identify recent failures

---

### 2. Find Slow Requests

**Kibana Query:**
```
duration_ms:>1000
```

**Time Range:** Last 24 hours

**Useful Fields:**
- `timestamp`
- `http_method`
- `http_path`
- `duration_ms`
- `http_status_code`
- `trace_id`

**Use Case:** Performance troubleshooting, identify bottlenecks

---

### 3. Trace a User Action End-to-End

**Step 1:** Get trace_id from API response header
```bash
curl -i http://localhost:8000/api/v1/orders | grep X-Trace-Id
# X-Trace-Id: 4bf92f3577b34da6a3ce929d0e0e4736
```

**Step 2:** Query Kibana for all logs with that trace_id
```
trace_id:"4bf92f3577b34da6a3ce929d0e0e4736"
```

**Time Range:** Last 7 days (or adjust based on when request was made)

**Expected Log Sequence:**
1. `order_creation_started` (API)
2. `outbox_event_created` (Outbox Service)
3. `order_created` (API)
4. `kafka_event_processed` (Outbox Worker)
5. `order_confirmed` (Order Processor - after delay)
6. `order_shipped` (Order Processor - after delay)

**Use Case:** Debug user-reported issues, verify end-to-end flow

---

### 4. Debug Background Workers

**Kafka Consumer Issues:**
```
message:"kafka_event_*" AND level:ERROR
```

**Order Processor Issues:**
```
message:"order_processor_error" OR message:"order_confirmation_failed" OR message:"order_shipping_failed"
```

**Outbox Worker Issues:**
```
message:"outbox_*" AND level:ERROR
```

**Use Case:** Troubleshoot async processing failures

---

## Common Queries

### Order Creation Failures
```
message:"order_creation_failed" OR (message:"order_created" AND level:ERROR)
```

### All Logs for a Specific User
```
user_id:"usr_12345"
```

### All Logs for a Specific Order
```
order_id:"ord_abc123"
```

### HTTP 5xx Errors
```
http_status_code:>=500
```

### HTTP 4xx Errors (Client Errors)
```
http_status_code:>=400 AND http_status_code:<500
```

### Kafka Consumer Lag/Duplicates
```
message:"kafka_event_duplicate" OR message:"kafka_consumer_lag"
```

### Database Errors
```
error_type:"DatabaseError" OR error_message:*database* OR error_message:*postgres*
```

### Redis Errors
```
error_type:"RedisError" OR error_message:*redis*
```

### Cache Misses
```
message:"cache_miss"
```

---

## Advanced Techniques

### 1. Filter by Environment
```
environment:"production" AND level:ERROR
```

### 2. Filter by Service Version
```
version:"v1.2.3" AND message:"order_created"
```

### 3. Aggregate Error Counts

**Kibana Lens Visualization:**
1. Navigate to Analytics → Lens
2. Choose "Bar chart"
3. X-axis: `error_type.keyword` (Top 10)
4. Y-axis: Count
5. Time range: Last 24 hours

**Use Case:** Identify most common error types

---

### 4. Build Request Duration Histogram

**Kibana Lens Visualization:**
1. Choose "Histogram"
2. X-axis: `duration_ms` (Histogram, interval: 100)
3. Y-axis: Count
4. Filter: `duration_ms:*` (exclude null values)

**Use Case:** Understand latency distribution

---

### 5. Export Logs for Support

1. Run query in Discover
2. Click "Share" → "CSV Reports"
3. Generate and download
4. Attach to support ticket

---

## Saved Searches

Pre-configured searches available in Kibana → Discover → Saved:

1. **All ERROR logs (last 1h)** - Quick error overview
2. **Slow requests** - Performance issues
3. **Trace ID lookup** - Template for trace investigation

To use: Click "Open" → Select saved search → Modify as needed

---

## Alerting Thresholds

### Critical Alerts (Page On-Call)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| ERROR rate | > 10/min | Page on-call engineer |
| HTTP 5xx rate | > 5% of requests | Page on-call engineer |
| Kafka consumer lag | > 1000 messages | Page on-call engineer |
| Outbox backlog | > 5000 events | Page on-call engineer |
| Background task down | Any task stopped | Page on-call engineer |

### Warning Alerts (Slack Notification)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Slow requests | > 100/min (>1s) | Notify #alerts channel |
| HTTP 4xx rate | > 10% of requests | Notify #alerts channel |
| Cache hit rate | < 50% | Notify #alerts channel |
| Redis errors | > 0/min | Notify #alerts channel |

---

## Troubleshooting Logging Infrastructure

### Logs Not Appearing in Kibana

**Check 1: Is Filebeat running?**
```bash
kubectl get daemonset filebeat -n order-service
kubectl get pods -n order-service -l app=filebeat
```

**Check 2: Check Filebeat logs**
```bash
kubectl logs -n order-service -l app=filebeat --tail=100
```

**Common Issues:**
- Elasticsearch password incorrect
- Elasticsearch not ready
- Insufficient permissions to read `/var/log/pods`

**Check 3: Is Elasticsearch healthy?**
```bash
kubectl get elasticsearch -n elastic-system
# Should show: HEALTH=green, PHASE=Ready
```

**Check 4: Verify index exists**
```bash
# Port-forward to Elasticsearch
kubectl port-forward -n elastic-system svc/order-service-es-http 9200:9200

# Get password
ES_PASSWORD=$(kubectl get secret order-service-es-elastic-user -n elastic-system -o=jsonpath='{.data.elastic}' | base64 --decode)

# List indices
curl -k -u "elastic:$ES_PASSWORD" https://localhost:9200/_cat/indices?v
```

Expected: Indices like `order-service-2026.02.07`

---

### Elasticsearch Disk Full

**Check disk usage:**
```bash
kubectl exec -n elastic-system order-service-es-default-0 -- df -h /usr/share/elasticsearch/data
```

**Solutions:**
1. **Reduce retention:** Edit `terraform/logging-variables.tf`, set `log_retention_days = 3`
2. **Increase storage:** Edit `terraform/logging-variables.tf`, set `elasticsearch_storage_size = "10Gi"`
3. **Manual cleanup:**
   ```bash
   # Delete old indices
   curl -k -u "elastic:$ES_PASSWORD" -X DELETE "https://localhost:9200/order-service-2026.01.*"
   ```

---

### Missing Fields in Kibana

**Cause:** Index pattern needs refresh after new fields added

**Solution:**
1. Navigate to Stack Management → Index Patterns
2. Click `order-service-*`
3. Click "Refresh field list" (🔄 icon)
4. Confirm new fields appear

---

## Log Format Reference

### Structured Log Entry Example

```json
{
  "@timestamp": "2026-02-07T14:23:45.123456Z",
  "timestamp": "2026-02-07T14:23:45.123456Z",
  "level": "INFO",
  "message": "order_created",
  "service_name": "order-service",
  "environment": "production",
  "version": "v1.0.0",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "parent_span_id": "a1b2c3d4e5f6g7h8",
  "request_id": "req_abc123",
  "order_id": "ord_xyz789",
  "user_id": "usr_456",
  "http_method": "POST",
  "http_path": "/api/v1/orders",
  "http_status_code": 201,
  "duration_ms": 145.67,
  "kubernetes": {
    "namespace": "order-service",
    "pod": {
      "name": "order-service-api-7d9f8b6c5-x4k2m"
    },
    "container": {
      "name": "order-service"
    }
  }
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `@timestamp` | date | Log timestamp (ISO 8601 UTC) |
| `level` | keyword | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `message` | text | Event name (structured, not free-form) |
| `trace_id` | keyword | 128-bit distributed trace ID (32 hex chars) |
| `span_id` | keyword | 64-bit span ID (16 hex chars) |
| `request_id` | keyword | Unique per HTTP request |
| `duration_ms` | float | Request duration in milliseconds |
| `error_type` | keyword | Exception class name |
| `error_message` | text | Error description |

---

## Best Practices

### 1. Always Use Trace IDs
When reporting issues, include the `trace_id` from the API response header. This allows engineers to see the complete request flow.

### 2. Time Ranges Matter
Adjust time range based on issue:
- Real-time debugging: Last 15 minutes
- Recent issues: Last 1 hour
- Historical analysis: Last 7 days

### 3. Combine with Metrics
Logs explain *what* happened, metrics show *how much*. Use Grafana dashboards alongside Kibana for complete picture.

### 4. Use Saved Searches
Save frequently-used queries to avoid retyping. Share with team via Kibana export/import.

### 5. Filter Noise
Exclude DEBUG logs in production:
```
level:(INFO OR WARNING OR ERROR OR CRITICAL)
```

---

## Getting Help

### Internal Resources
- **Runbook:** This document
- **Architecture Docs:** `docs/architecture.md`
- **Grafana Dashboards:** http://localhost:3000 (metrics)

### External Resources
- **Elasticsearch Query DSL:** https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html
- **Kibana Discover:** https://www.elastic.co/guide/en/kibana/current/discover.html
- **W3C Trace Context:** https://www.w3.org/TR/trace-context/

### On-Call Escalation
1. Check this runbook first
2. Search Slack #incidents for similar issues
3. Page on-call engineer if critical
4. Create incident ticket with trace_id and relevant logs
