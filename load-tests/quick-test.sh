#!/bin/bash

##
# Quick Load Test Runner for Order Service
#
# Usage:
#   ./quick-test.sh                    # Run smoke test
#   ./quick-test.sh smoke              # Run smoke test
#   ./quick-test.sh load               # Run load test
#   ./quick-test.sh stress             # Run stress test
#   ./quick-test.sh spike              # Run spike test
#   ./quick-test.sh soak               # Run soak test
#   ./quick-test.sh comprehensive      # Run comprehensive test
##

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
# NOTE: Using [::1] (IPv6 loopback) because K8s port-forward on Rancher Desktop
# only listens on IPv6. k6 resolves "localhost" to IPv4 (127.0.0.1) which fails.
BASE_URL="${BASE_URL:-http://[::1]:8080}"
TEST_SCRIPT="load-tests/order-service-load-test.js"
SCENARIO="${1:-smoke}"

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo -e "${RED}Error: k6 is not installed${NC}"
    echo "Install it with:"
    echo "  macOS: brew install k6"
    echo "  Linux: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if service is running (use curl which handles IPv6 properly)
echo -e "${BLUE}Checking if Order Service is running...${NC}"
if ! curl -s -f -o /dev/null "http://localhost:8080/api/v1/orders/"; then
    echo -e "${RED}Error: Order Service is not responding at ${BASE_URL}${NC}"
    echo "Make sure the service is running before running load tests"
    exit 1
fi
echo -e "${GREEN}✓ Service is running${NC}"
echo ""

# Display test info
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running k6 Load Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Scenario:  ${YELLOW}${SCENARIO}${NC}"
echo -e "Target:    ${YELLOW}${BASE_URL}${NC}"
echo -e "Script:    ${YELLOW}${TEST_SCRIPT}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Run the test
echo -e "${GREEN}Starting test...${NC}"
echo ""

k6 run \
    -e BASE_URL="${BASE_URL}" \
    -e SCENARIO="${SCENARIO}" \
    "${TEST_SCRIPT}"

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Load test completed successfully${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Load test failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
