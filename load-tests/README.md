# Load Testing with Grafana k6

This directory contains load tests for the Order Service using Grafana k6.

## Important: K8s Port-Forward Limitations ⚠️

The load tests are **optimized for K8s port-forwarding** (e.g., `kubectl port-forward`). Port-forward has connection limits and can't handle high concurrency well.

**Current settings:**
- Smoke test: 1 VU (virtual user)
- Load test: 3-5 VUs
- Stress test: 5-15 VUs

**For higher load testing**, use one of these instead:
```bash
# Option 1: Use NodePort (if available)
BASE_URL=http://<node-ip>:30080 ./load-tests/quick-test.sh load

# Option 2: Use Ingress (if configured)
BASE_URL=https://api.example.com ./load-tests/quick-test.sh load

# Option 3: Run k6 inside the cluster
kubectl run k6 --rm -it --image=grafana/k6 -- run -e BASE_URL=http://rest-api-service /scripts/test.js
```

## Prerequisites

k6 is already installed ✅

If you need to reinstall:
```bash
# macOS
brew install k6

# Linux (Debian/Ubuntu)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

## Test Scenarios

### 1. Smoke Test
**Purpose**: Quick validation that the service is working  
**Duration**: 30 seconds  
**VUs**: 2

```bash
./load-tests/quick-test.sh smoke
# or
k6 run load-tests/order-service-load-test.js --scenario smoke
```

### 2. Load Test
**Purpose**: Test under normal expected load  
**Duration**: 9 minutes  
**VUs**: Ramps from 0 → 10 → 20 → 0
./load-tests/quick-test.sh load
```

### 3. Stress Test
**Purpose**: Push the system beyond normal load  
**Duration**: 11 minutes  
**VUs**: Ramps from 0 → 20 → 50 → 100 → 0

```bash
./load-tests/quick-test.sh stress
```

### 4. Spike Test
**Purpose**: Test sudden traffic surge  
**Duration**: 2 minutes  
**Pattern**: 5 VUs → sudden spike to 100 VUs → back to 5

```bash
./load-tests/quick-test.sh spike
```

### 5. Soak Test
**Purpose**: Test stability over extended period  
**Duration**: 10 minutes  
**VUs**: Constant 15

```bash
./load-tests/quick-test.sh soak
```

### 6. Comprehensive Test
**Purpose**: Test all scenarios sequentially  

```bash
./load-tests/quick-test.sh
```bash
k6 run load-tests/order-service-load-test.js --scenario comprehensive
```

## Custom Runs

### Quick test with custom parameters
```bash
k6 run --vus 10 --duration 30s load-tests/order-service-load-test.js
```

### Test against different environment
```bash
k6 run -e BASE_URL=http://staging.example.com load-tests/order-service-load-test.js
```

### Run with specific scenario
```bash
k6 run load-tests/order-service-load-test.js --scenario smoke
```

## Test Coverage

The load test covers all scenarios:

### ✅ Create Order Scenarios
- **Valid User (Cache Hit)**: ~60% of requests
  - User exists in Redis cache (from Kafka events)
  - Fast validation (<10ms)
  
- **New User (Cache Miss)**: ~15% of requests
  - User not in cache, requires User Service API call
  - Slower validation (50-200ms due to mock latency)
  
- **Invalid User**: ~10% of requests
  - User ID doesn't match `user_*` pattern
  - Expected 404 response
  
- **Inactive User**: Implicit in valid/new users
  - 30% chance based on hash in mock
  - Expected 404 response

### ✅ Read Order Scenarios
- **Default Pagination**: 15% of requests
- **Custom Pagination**: Various skip/limit combinations
- **Large Offset**: Tests performance with pagination

## Metrics Tracked

### Built-in k6 Metrics
- `http_req_duration`: Request duration
- `http_req_failed`: Failed requests rate
- `http_reqs`: Request rate
- `iterations`: Total iterations
- `vus`: Virtual users

### Custom Metrics
- `order_creation_success_rate`: Successful order creations
- `order_creation_failure_rate`: Failed order creations
- `order_read_success_rate`: Successful order reads
- `user_validation_errors`: User validation failures
- `cache_hit_orders`: Orders created with cache hit
- `cache_miss_orders`: Orders created with cache miss
- `order_creation_duration`: Order creation latency
- `order_read_duration`: Order read latency

## Thresholds

The test defines the following success criteria:

- **HTTP Errors**: < 5% (excluding expected validation failures)
- **95th Percentile**: < 500ms
- **Order Creation Success**: > 70% (accounting for invalid users)
- **Order Read Success**: > 99%

## Output Formats

### Console output (default)
```bash
k6 run load-tests/order-service-load-test.js
```

### JSON output
```bash
k6 run --out json=results.json load-tests/order-service-load-test.js
```

### InfluxDB output (for Grafana dashboards)
```bash
k6 run --out influxdb=http://localhost:8086/k6 load-tests/order-service-load-test.js
```

### Cloud output (Grafana Cloud k6)
```bash
k6 cloud login
k6 cloud load-tests/order-service-load-test.js
```

## Interpreting Results

### Good Performance Indicators
- ✅ p(95) < 500ms
- ✅ Order creation success rate > 70%
- ✅ Order read success rate > 99%
- ✅ No 5xx errors
- ✅ Cache hit ratio > 80%

### Warning Signs
- ⚠️ p(95) > 1000ms
- ⚠️ Increasing error rate over time
- ⚠️ Memory leaks (response times increasing during soak test)
- ⚠️ High CPU usage

### Critical Issues
- 🔴 p(95) > 5000ms
- 🔴 Error rate > 10%
- 🔴 5xx errors appearing
- 🔴 Service crashes

## Integration with Monitoring

### View metrics during test
1. Open Grafana: http://localhost:3000
2. Navigate to "Order Service Dashboard"
3. Run load test in another terminal
4. Observe:
   - Request rate
   - Response times (p50, p95, p99)
   - Error rate
   - Cache hit/miss ratio
   - User validation metrics
   - Database connection pool usage

### Prometheus metrics
```bash
# During test, check metrics
curl http://localhost:8000/metrics | grep user_validation
curl http://localhost:8000/metrics | grep order_creation
curl http://localhost:8000/metrics | grep http_request
```

## Best Practices

1. **Start small**: Run smoke test first
2. **Monitor resources**: Watch CPU, memory, database connections
3. **Check logs**: Look for errors and warnings during test
4. **Compare baselines**: Track performance over time
5. **Test in isolation**: Ensure other processes aren't affecting results
6. **Warm up caches**: Run a small test first to populate caches
7. **Analyze percentiles**: Don't just look at averages

## Troubleshooting

### Service not responding
```bash
# Check if service is running
curl http://localhost:8000/api/v1/orders/

# Check logs
docker logs order-service

# Check dependencies
docker ps | grep -E "(postgres|redis|kafka)"
```

### High error rates
- Check database connection pool exhaustion
- Verify Redis is responding
- Check for rate limiting
- Review application logs

### Slow response times
- Check if caches are populated
- Verify database indexes
- Monitor database query performance
- Check for N+1 queries

## Examples

### Smoke test before deployment
```bash
#!/bin/bash
echo "Running smoke test..."
k6 run --scenario smoke load-tests/order-service-load-test.js
if [ $? -eq 0 ]; then
    echo "✅ Smoke test passed"
    exit 0
else
    echo "❌ Smoke test failed"
    exit 1
fi
```

### CI/CD integration
```yaml
# .github/workflows/load-test.yml
- name: Run k6 load test
  run: |
    k6 run --scenario smoke load-tests/order-service-load-test.js \
      -e BASE_URL=${{ secrets.STAGING_URL }} \
      --out json=results.json
```

## Next Steps

1. Run smoke test to verify setup
2. Review metrics in Grafana during test
3. Run load test to establish baseline
4. Schedule regular soak tests
5. Integrate into CI/CD pipeline
6. Set up alerts for threshold violations
