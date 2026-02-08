/**
 * Grafana k6 Load Test for Order Service
 * 
 * Tests all scenarios:
 * 1. Create orders with valid users (cache hit)
 * 2. Create orders with new users (cache miss)
 * 3. Create orders with invalid users (404)
 * 4. Create orders with inactive users (potential 404)
 * 5. Read orders with pagination
 * 
 * NOTE: Load levels are reduced for K8s port-forwarding limitations.
 * For higher load, use a LoadBalancer/Ingress or NodePort instead of port-forward.
 * 
 * Run options:
 * - Use the quick-test.sh script: ./load-tests/quick-test.sh smoke
 * - Direct: k6 run -e SCENARIO=smoke load-tests/order-service-load-test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomIntBetween, randomItem } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// =============================================================================
// CONFIGURATION
// =============================================================================

const BASE_URL = __ENV.BASE_URL || 'http://[::1]:8080';
const API_PREFIX = '/api/v1';
const SCENARIO = __ENV.SCENARIO || 'smoke';

// =============================================================================
// CUSTOM METRICS
// =============================================================================

const orderCreationSuccessRate = new Rate('order_creation_success_rate');
const orderCreationFailureRate = new Rate('order_creation_failure_rate');
const orderReadSuccessRate = new Rate('order_read_success_rate');
const userValidationErrors = new Counter('user_validation_errors');
const cacheHitOrders = new Counter('cache_hit_orders');
const cacheMissOrders = new Counter('cache_miss_orders');
const orderCreationDuration = new Trend('order_creation_duration');
const orderReadDuration = new Trend('order_read_duration');

// =============================================================================
// TEST OPTIONS - DYNAMICALLY SET BASED ON SCENARIO
// =============================================================================

function getOptions() {
    const baseThresholds = {
        'http_req_failed': ['rate<0.05'],
        'http_req_duration': ['p(95)<500'],
        'order_creation_success_rate': ['rate>0.70'],
        'order_read_success_rate': ['rate>0.99'],
    };

    const scenarios = {
        smoke: {
            executor: 'constant-vus',
            vus: 1,  // Reduced from 2 for port-forward
            duration: '30s',
            tags: { test_type: 'smoke' },
        },
        load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 3 },   // Gentle ramp for port-forward
                { duration: '2m', target: 3 },
                { duration: '30s', target: 5 },
                { duration: '2m', target: 5 },
                { duration: '30s', target: 0 },
            ],
            tags: { test_type: 'load' },
        },
        stress: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 5 },
                { duration: '2m', target: 5 },
                { duration: '1m', target: 10 },
                { duration: '2m', target: 10 },
                { duration: '1m', target: 15 },
                { duration: '2m', target: 15 },
                { duration: '2m', target: 0 },
            ],
            tags: { test_type: 'stress' },
        },
        spike: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '10s', target: 2 },
                { duration: '10s', target: 10 },  // Reduced spike
                { duration: '1m', target: 10 },
                { duration: '10s', target: 2 },
                { duration: '30s', target: 0 },
            ],
            tags: { test_type: 'spike' },
        },
        soak: {
            executor: 'constant-vus',
            vus: 5,  // Reduced from 15 for port-forward
            duration: '10m',
            tags: { test_type: 'soak' },
        },
        comprehensive: {
            executor: 'constant-vus',
            vus: 2,  // Reduced from 5
            duration: '2m',
            tags: { test_type: 'comprehensive' },
        },
    };

    return {
        thresholds: baseThresholds,
        scenarios: {
            [SCENARIO]: scenarios[SCENARIO] || scenarios.smoke,
        },
    };
}

export const options = getOptions();

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Safely parse JSON response
 */
function safeParseJSON(response) {
    if (!response || !response.body) return null;
    try {
        return JSON.parse(response.body);
    } catch (e) {
        return null;
    }
}

/**
 * Generate test data for order creation
 */
function generateOrderData(userIdType = 'valid') {
    let userId;

    switch (userIdType) {
        case 'valid':
            // Valid user IDs that should exist in cache or be fetchable
            userId = `user_${randomIntBetween(1, 100)}`;
            break;
        case 'new':
            // New user IDs (cache miss, requires API call)
            userId = `user_new_${__VU}_${Date.now()}_${randomIntBetween(1000, 9999)}`;
            break;
        case 'invalid':
            // Invalid user IDs (don't match expected pattern)
            userId = `invalid_${randomIntBetween(1, 1000)}`;
            break;
        case 'inactive':
            // User IDs that may be inactive (hash-based in mock)
            userId = `user_inactive_${randomIntBetween(1, 50)}`;
            break;
        default:
            userId = `user_${randomIntBetween(1, 100)}`;
    }

    const products = ['prod_laptop', 'prod_phone', 'prod_tablet', 'prod_watch', 'prod_headphones'];
    const itemCount = randomIntBetween(1, 4);
    const items = [];

    for (let i = 0; i < itemCount; i++) {
        const price = parseFloat((randomIntBetween(10, 500) + Math.random()).toFixed(2));
        const quantity = randomIntBetween(1, 5);
        items.push({
            product_id: randomItem(products),
            quantity: quantity,
            price: price,
        });
    }

    const totalAmount = items.reduce((sum, item) => sum + (item.price * item.quantity), 0);

    return {
        user_id: userId,
        total_amount: parseFloat(totalAmount.toFixed(2)),
        currency: randomItem(['USD', 'EUR', 'GBP']),
        shipping_address: `${randomIntBetween(1, 9999)} Test St, Test City, TS ${randomIntBetween(10000, 99999)}`,
        items: items,
    };
}

/**
 * Create an order
 */
function createOrder(orderData) {
    const url = `${BASE_URL}${API_PREFIX}/orders/`;
    const params = {
        headers: {
            'Content-Type': 'application/json',
        },
        tags: { name: 'CreateOrder' },
    };

    const response = http.post(url, JSON.stringify(orderData), params);

    // Track duration
    orderCreationDuration.add(response.timings.duration);

    return response;
}

/**
 * Read orders with pagination
 */
function readOrders(skip = 0, limit = 20) {
    const url = `${BASE_URL}${API_PREFIX}/orders/?skip=${skip}&limit=${limit}`;
    const params = {
        tags: { name: 'ReadOrders' },
    };

    const response = http.get(url, params);

    // Track duration
    orderReadDuration.add(response.timings.duration);

    return response;
}

// =============================================================================
// TEST SCENARIOS
// =============================================================================

/**
 * Smoke Test: Basic functionality check
 */
export function smokeTest() {
    group('Smoke Test - Basic Health Check', () => {
        // Test 1: Read orders
        group('Read Orders', () => {
            const response = readOrders(0, 10);

            const success = check(response, {
                'status is 200': (r) => r.status === 200,
                'response has data': (r) => {
                    const body = safeParseJSON(r);
                    return body && body.data !== undefined;
                },
                'response has count': (r) => {
                    const body = safeParseJSON(r);
                    return body && body.count !== undefined;
                },
            });

            orderReadSuccessRate.add(success);
        });

        // Test 2: Create order with valid user
        group('Create Order - Valid User', () => {
            const orderData = generateOrderData('valid');
            const response = createOrder(orderData);

            const success = check(response, {
                'status is 200': (r) => r.status === 200,
                'has order_id': (r) => {
                    const body = safeParseJSON(r);
                    return body && body.id !== undefined;
                },
                'status is pending': (r) => {
                    const body = safeParseJSON(r);
                    return body && body.status === 'pending';
                },
            });

            orderCreationSuccessRate.add(success);
        });
    });

    sleep(2);  // Longer sleep for port-forward
}

/**
 * Load Test: Mixed realistic scenarios
 */
export function loadTest() {
    // Realistic mix of operations
    const scenario = randomIntBetween(1, 100);

    if (scenario <= 60) {
        // 60% - Create order with valid user (cache hit)
        group('Create Order - Valid User (Cache Hit)', () => {
            const orderData = generateOrderData('valid');
            const response = createOrder(orderData);

            const success = check(response, {
                'status is 200': (r) => r.status === 200,
                'has order_id': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.id !== undefined;
                },
                'user validated': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.user_id === orderData.user_id;
                },
            });

            if (success) {
                orderCreationSuccessRate.add(1);
                cacheHitOrders.add(1);
            } else {
                orderCreationFailureRate.add(1);
            }
        });
    } else if (scenario <= 75) {
        // 15% - Create order with new user (cache miss, API call)
        group('Create Order - New User (Cache Miss)', () => {
            const orderData = generateOrderData('new');
            const response = createOrder(orderData);

            const success = check(response, {
                'status is 200': (r) => r.status === 200,
                'has order_id': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.id !== undefined;
                },
            });

            if (success) {
                orderCreationSuccessRate.add(1);
                cacheMissOrders.add(1);
            } else {
                orderCreationFailureRate.add(1);
            }
        });
    } else if (scenario <= 85) {
        // 10% - Create order with invalid user (should fail)
        group('Create Order - Invalid User', () => {
            const orderData = generateOrderData('invalid');
            const response = createOrder(orderData);

            const expectedFailure = check(response, {
                'status is 404': (r) => r.status === 404,
                'error message present': (r) => r.status === 404 && r.body.includes('User not found'),
            });

            if (expectedFailure) {
                userValidationErrors.add(1);
            }
        });
    } else {
        // 15% - Read orders
        group('Read Orders', () => {
            const skip = randomIntBetween(0, 100);
            const limit = randomItem([10, 20, 50, 100]);
            const response = readOrders(skip, limit);

            const success = check(response, {
                'status is 200': (r) => r.status === 200,
                'has data array': (r) => {
                    const body = safeParseJSON(r);
                    return body && Array.isArray(body.data);
                },
                'has count': (r) => {
                    const body = safeParseJSON(r);
                    return body && typeof body.count === 'number';
                },
                'response time < 200ms': (r) => r.timings.duration < 200,
            });

            orderReadSuccessRate.add(success);
        });
    }

    sleep(randomIntBetween(1, 3));
}

/**
 * Stress Test: High load scenarios
 */
export function stressTest() {
    // More aggressive, less sleep time
    const scenario = randomIntBetween(1, 100);

    if (scenario <= 70) {
        // Mostly creates
        const userType = randomItem(['valid', 'valid', 'valid', 'new', 'invalid']);
        const orderData = generateOrderData(userType);
        const response = createOrder(orderData);

        if (response.status === 200) {
            orderCreationSuccessRate.add(1);
        } else {
            orderCreationFailureRate.add(1);
        }
    } else {
        // Some reads
        const response = readOrders(randomIntBetween(0, 500), 50);
        orderReadSuccessRate.add(response.status === 200);
    }

    sleep(randomIntBetween(0.1, 0.5));
}

/**
 * Spike Test: Sudden traffic surge
 */
export function spikeTest() {
    // Rapid fire requests
    const orderData = generateOrderData('valid');
    const response = createOrder(orderData);

    check(response, {
        'not rate limited': (r) => r.status !== 429,
        'not server error': (r) => r.status < 500,
    });

    sleep(0.1);
}

/**
 * Soak Test: Extended duration testing
 */
export function soakTest() {
    // Realistic mix for extended period
    const operations = [
        () => {
            const orderData = generateOrderData('valid');
            return createOrder(orderData);
        },
        () => {
            const orderData = generateOrderData('new');
            return createOrder(orderData);
        },
        () => readOrders(randomIntBetween(0, 200), 20),
    ];

    const operation = randomItem(operations);
    const response = operation();

    check(response, {
        'no memory leak indicators': (r) => r.timings.duration < 5000,
        'successful or expected failure': (r) => r.status === 200 || r.status === 404,
    });

    sleep(randomIntBetween(1, 2));
}

// =============================================================================
// COMPREHENSIVE TEST (Run with: k6 run --scenario comprehensive)
// =============================================================================

export function comprehensiveTest() {
    group('Comprehensive API Test Suite', () => {

        // Test 1: Create order with valid user (cache hit expected)
        group('Valid User - Cache Hit', () => {
            const orderData = generateOrderData('valid');
            const response = createOrder(orderData);

            check(response, {
                'status is 200': (r) => r.status === 200,
                'order created': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.id !== undefined;
                },
                'correct user_id': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.user_id === orderData.user_id;
                },
                'status is pending': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.status === 'pending';
                },
                'has items': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.items && body.items.length > 0;
                },
            });

            orderCreationSuccessRate.add(response.status === 200);
            if (response.status === 200) cacheHitOrders.add(1);
        });

        sleep(0.5);

        // Test 2: Create order with new user (cache miss, API lookup)
        group('New User - Cache Miss', () => {
            const orderData = generateOrderData('new');
            const response = createOrder(orderData);

            check(response, {
                'status is 200': (r) => r.status === 200,
                'order created': (r) => {
                    const body = safeParseJSON(r);
                    return r.status === 200 && body && body.id !== undefined;
                },
                'longer response time (API call)': (r) => r.timings.duration > 50, // Should take longer due to mock API latency
            });

            orderCreationSuccessRate.add(response.status === 200);
            if (response.status === 200) cacheMissOrders.add(1);
        });

        sleep(0.5);

        // Test 3: Create order with invalid user (should fail)
        group('Invalid User - Expected Failure', () => {
            const orderData = generateOrderData('invalid');
            const response = createOrder(orderData);

            check(response, {
                'status is 404': (r) => r.status === 404,
                'error message': (r) => r.body.includes('User not found'),
            });

            if (response.status === 404) {
                userValidationErrors.add(1);
            }
        });

        sleep(0.5);

        // Test 4: Read orders with default pagination
        group('Read Orders - Default Pagination', () => {
            const response = readOrders(0, 20);

            check(response, {
                'status is 200': (r) => r.status === 200,
                'has data array': (r) => {
                    const body = safeParseJSON(r);
                    return body && Array.isArray(body.data);
                },
                'has count': (r) => {
                    const body = safeParseJSON(r);
                    return body && typeof body.count === 'number';
                },
                'fast response': (r) => r.timings.duration < 500,
            });

            orderReadSuccessRate.add(response.status === 200);
        });

        sleep(0.5);

        // Test 5: Read orders with custom pagination
        group('Read Orders - Custom Pagination', () => {
            const response = readOrders(50, 10);

            check(response, {
                'status is 200': (r) => r.status === 200,
                'returns max 10 items': (r) => {
                    const body = safeParseJSON(r);
                    return body && body.data && body.data.length <= 10;
                },
            });

            orderReadSuccessRate.add(response.status === 200);
        });

        sleep(0.5);

        // Test 6: Create multiple orders rapidly (simulate burst)
        group('Burst Create - Multiple Orders', () => {
            for (let i = 0; i < 3; i++) {
                const orderData = generateOrderData('valid');
                const response = createOrder(orderData);
                orderCreationSuccessRate.add(response.status === 200);
            }
        });

    });

    sleep(2);
}

// =============================================================================
// DEFAULT EXPORT - Route to appropriate test based on SCENARIO env var
// =============================================================================

export default function () {
    const scenario = SCENARIO.toLowerCase();

    switch (scenario) {
        case 'smoke':
            smokeTest();
            break;
        case 'load':
            loadTest();
            break;
        case 'stress':
            stressTest();
            break;
        case 'spike':
            spikeTest();
            break;
        case 'soak':
            soakTest();
            break;
        case 'comprehensive':
            comprehensiveTest();
            break;
        default:
            console.log(`Unknown scenario: ${scenario}, running smoke test`);
            smokeTest();
    }
}
