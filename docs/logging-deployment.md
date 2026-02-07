# Deploying the Logging Stack

## Quick Start Guide

This guide walks you through deploying the complete logging infrastructure (Elasticsearch, Kibana, Filebeat) to your Rancher Desktop cluster.

---

## Prerequisites

- ✅ Rancher Desktop running on ARM Mac
- ✅ `kubectl` configured and connected to cluster
- ✅ Terraform installed (`brew install terraform`)
- ✅ Order service code with logging implementation (already done)

---

## Step 1: Deploy Infrastructure with Terraform (Two-Phase)

Because we're using CRDs (Custom Resource Definitions) from the ECK operator, we need to deploy in two phases:

### Phase 1: Install ECK Operator and Namespaces

```bash
cd terraform

# Initialize Terraform (first time only)
terraform init

# Phase 1: Deploy ECK operator (installs CRDs)
terraform apply \
  -target=kubernetes_namespace.elastic_system \
  -target=helm_release.eck_operator \
  -target=kubernetes_namespace.order_service \
  -auto-approve
```

**Wait ~30 seconds** for the ECK operator to install CRDs and become ready.

**Verify CRDs are installed:**
```bash
kubectl get crd | grep elastic
```

**Expected output:**
```
agents.agent.k8s.elastic.co
apmservers.apm.k8s.elastic.co
beats.beat.k8s.elastic.co
elasticmapsservers.maps.k8s.elastic.co
elasticsearches.elasticsearch.k8s.elastic.co  ← This one is needed
kibanas.kibana.k8s.elastic.co                 ← This one too
```

### Phase 2: Deploy Elasticsearch, Kibana, and Filebeat

```bash
# Phase 2: Deploy everything else (uses the CRDs)
terraform apply -auto-approve
```

**Expected output:**
```
Apply complete! Resources: 8 added, 0 changed, 0 destroyed.

Outputs:

elasticsearch_endpoint = "kubectl port-forward -n elastic-system svc/order-service-es-http 9200:9200"
elasticsearch_password_command = "kubectl get secret order-service-es-elastic-user -n elastic-system -o=jsonpath='{.data.elastic}' | base64 --decode"
kibana_endpoint = "kubectl port-forward -n elastic-system svc/order-service-kibana-kb-http 5601:5601"
kibana_url = "https://localhost:5601 (username: elastic, password: see elasticsearch_password_command)"
```

**Wait time:** ~3-5 minutes for Elasticsearch and Kibana to become ready

---

## Step 2: Verify Deployment

### Check Elasticsearch Status
```bash
kubectl get elasticsearch -n elastic-system
```

**Expected:**
```
NAME               HEALTH   NODES   VERSION   PHASE   AGE
order-service-es   green    1       8.16.1    Ready   3m
```

### Check Kibana Status
```bash
kubectl get kibana -n elastic-system
```

**Expected:**
```
NAME                     HEALTH   NODES   VERSION   AGE
order-service-kibana     green    1       8.16.1    3m
```

### Check Filebeat Status
```bash
kubectl get daemonset filebeat -n order-service
kubectl get pods -n order-service -l app=filebeat
```

**Expected:**
```
NAME       DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR            AGE
filebeat   1         1         1       1            1           kubernetes.io/arch=arm64   2m

NAME             READY   STATUS    RESTARTS   AGE
filebeat-xxxxx   1/1     Running   0          2m
```

---

## Step 3: Access Kibana

### Get Elasticsearch Password
```bash
kubectl get secret order-service-es-elastic-user -n elastic-system -o=jsonpath='{.data.elastic}' | base64 --decode && echo
```

**Save this password!** You'll need it to log into Kibana.

### Port-Forward to Kibana
```bash
kubectl port-forward -n elastic-system svc/order-service-kibana-kb-http 5601:5601
```

### Open Kibana in Browser
1. Navigate to: https://localhost:5601
2. Accept the self-signed certificate warning
3. Login:
   - Username: `elastic`
   - Password: (from previous step)

---

## Step 4: Create Index Pattern in Kibana

1. Click hamburger menu (☰) → **Stack Management**
2. Click **Index Patterns** (under Kibana section)
3. Click **Create index pattern**
4. Index pattern name: `order-service-*`
5. Click **Next step**
6. Time field: `@timestamp`
7. Click **Create index pattern**

---

## Step 5: Generate Test Logs

### Deploy Order Service (if not already running)
```bash
cd ../helm/rest-api
helm upgrade --install order-service . --values values.yaml
```

### Create a Test Order
```bash
# Port-forward to order service
kubectl port-forward -n order-service svc/order-service 8000:8000 &

# Create an order
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "usr_test123",
    "total_amount": 99.99,
    "currency": "USD",
    "items": [
      {
        "product_id": "prod_abc",
        "quantity": 2,
        "price": 49.995
      }
    ]
  }'
```

**Save the trace_id from the response!**

---

## Step 6: View Logs in Kibana

1. Click hamburger menu (☰) → **Analytics** → **Discover**
2. Select index pattern: `order-service-*`
3. Adjust time range to "Last 15 minutes"
4. You should see logs appearing!

### Verify Trace Continuity

In the search bar, enter:
```
trace_id:"<YOUR_TRACE_ID_FROM_STEP_5>"
```

**Expected logs (in chronological order):**
1. `order_creation_started`
2. `outbox_event_created`
3. `order_created`
4. (Wait ~30 seconds for background processing)
5. `order_confirmed`
6. (Wait ~30 more seconds)
7. `order_shipped`

All should have the **same trace_id**! 🎉

---

## Step 7: Import Saved Searches (Optional)

The saved searches are defined in `terraform/kibana-saved-searches.tf` as ConfigMaps.

**Manual import:**
1. Navigate to **Stack Management** → **Saved Objects**
2. Click **Import**
3. Manually create the 3 saved searches using queries from `docs/logging-runbook.md`:
   - All ERROR logs (last 1h): `level:ERROR`
   - Slow requests: `duration_ms:>1000`
   - Trace ID lookup: `trace_id:"REPLACE_WITH_ACTUAL_TRACE_ID"`

---

## Troubleshooting

### Elasticsearch Pod Not Starting

**Check logs:**
```bash
kubectl logs -n elastic-system order-service-es-default-0
```

**Common issues:**
- Insufficient memory (increase `elasticsearch_memory` in `terraform/logging-variables.tf`)
- Storage class not available (check `kubectl get sc`)

### Filebeat Not Shipping Logs

**Check Filebeat logs:**
```bash
kubectl logs -n order-service -l app=filebeat --tail=50
```

**Common issues:**
- Elasticsearch password incorrect (secret not found)
- Elasticsearch not ready yet (wait a few minutes)
- No logs to ship (create test orders)

### No Logs in Kibana

1. **Check index exists:**
   ```bash
   # Port-forward to Elasticsearch
   kubectl port-forward -n elastic-system svc/order-service-es-http 9200:9200 &

   # Get password
   ES_PASSWORD=$(kubectl get secret order-service-es-elastic-user -n elastic-system -o=jsonpath='{.data.elastic}' | base64 --decode)

   # List indices
   curl -k -u "elastic:$ES_PASSWORD" https://localhost:9200/_cat/indices?v
   ```

   Expected: Indices like `order-service-2026.02.07`

2. **Refresh index pattern in Kibana:**
   - Stack Management → Index Patterns → `order-service-*` → Refresh (🔄)

3. **Check time range:**
   - Make sure time range in Discover includes when you created test orders

---

## Next Steps

1. **Read the logging runbook:** `docs/logging-runbook.md`
2. **Create Grafana dashboards** linking to Kibana (optional)
3. **Set up alerts** for ERROR rate thresholds (optional)
4. **Train your team** on log querying

---

## Cleanup (Optional)

To remove the logging stack:

```bash
cd terraform
terraform destroy -auto-approve
```

This will delete Elasticsearch, Kibana, and Filebeat, but **preserve your application logs** (they're still written to stdout and accessible via `kubectl logs`).

---

## Resource Usage

**Expected resource consumption on ARM Mac:**
- Elasticsearch: ~1GB RAM, ~5GB disk
- Kibana: ~512MB RAM
- Filebeat: ~100MB RAM per node
- ECK Operator: ~100MB RAM

**Total: ~1.7GB RAM, 5GB disk**

This is conservative and suitable for local development on Rancher Desktop.
