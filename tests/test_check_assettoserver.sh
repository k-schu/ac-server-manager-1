#!/bin/bash
# Test suite for check_assettoserver_instance.sh
# This test validates the health check script's functionality

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_CHECK_SCRIPT="${SCRIPT_DIR}/../tools/check_assettoserver_instance.sh"
TEST_FAILURES=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_test() {
    echo -e "${GREEN}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}  ✓${NC} $1"
}

log_fail() {
    echo -e "${RED}  ✗${NC} $1"
    TEST_FAILURES=$((TEST_FAILURES + 1))
}

log_skip() {
    echo -e "${YELLOW}  ⊘${NC} $1"
}

echo "========================================"
echo "Health Check Script Test Suite"
echo "========================================"
echo ""

# Test 1: Script exists and is executable
log_test "Checking if health check script exists and is executable"
if [ -f "$HEALTH_CHECK_SCRIPT" ]; then
    log_pass "Script exists at $HEALTH_CHECK_SCRIPT"
else
    log_fail "Script not found at $HEALTH_CHECK_SCRIPT"
    exit 1
fi

if [ -x "$HEALTH_CHECK_SCRIPT" ]; then
    log_pass "Script is executable"
else
    log_fail "Script is not executable"
fi
echo ""

# Test 2: Script has proper shebang
log_test "Checking script format"
if head -n 1 "$HEALTH_CHECK_SCRIPT" | grep -q "^#!/bin/bash"; then
    log_pass "Has valid bash shebang"
else
    log_fail "Missing or invalid shebang"
fi
echo ""

# Test 3: Script syntax is valid
log_test "Validating bash syntax"
if bash -n "$HEALTH_CHECK_SCRIPT" 2>/dev/null; then
    log_pass "Bash syntax is valid"
else
    log_fail "Bash syntax errors detected"
    bash -n "$HEALTH_CHECK_SCRIPT" 2>&1 | sed 's/^/    /'
fi
echo ""

# Test 4: Script contains required checks
log_test "Verifying required functionality"

required_checks=(
    "docker ps"           # Docker container check
    "ss -ulnp"            # UDP port check with ss
    "netstat -ulnp"       # UDP port check with netstat
    "ss -tlnp"            # TCP port check with ss
    "netstat -tlnp"       # TCP port check with netstat
    "curl"                # HTTP check with curl
    "wget"                # HTTP check with wget
    "docker logs"         # Container logs
)

# Check that at least one of the required checks exists
udp_check_found=false
tcp_check_found=false
http_check_found=false
docker_ps_found=false
docker_logs_found=false

if grep -q "docker ps" "$HEALTH_CHECK_SCRIPT"; then
    docker_ps_found=true
    log_pass "Contains check for: docker ps"
fi

if grep -q "docker logs" "$HEALTH_CHECK_SCRIPT"; then
    docker_logs_found=true
    log_pass "Contains check for: docker logs"
fi

if grep -qE "ss.*-ulnp|netstat.*-ulnp" "$HEALTH_CHECK_SCRIPT"; then
    udp_check_found=true
    log_pass "Contains UDP port check (ss or netstat)"
fi

if grep -qE "ss.*-tlnp|netstat.*-tlnp" "$HEALTH_CHECK_SCRIPT"; then
    tcp_check_found=true
    log_pass "Contains TCP port check (ss or netstat)"
fi

if grep -qE "curl|wget" "$HEALTH_CHECK_SCRIPT"; then
    http_check_found=true
    log_pass "Contains HTTP endpoint check (curl or wget)"
fi

if ! $docker_ps_found; then
    log_fail "Missing docker ps check"
fi

if ! $docker_logs_found; then
    log_fail "Missing docker logs check"
fi

if ! $udp_check_found; then
    log_fail "Missing UDP port check"
fi

if ! $tcp_check_found; then
    log_fail "Missing TCP port check"
fi

if ! $http_check_found; then
    log_fail "Missing HTTP endpoint check"
fi
echo ""

# Test 5: Script defines correct port numbers
log_test "Checking port number definitions"

expected_ports=(
    "9600"  # Game port UDP/TCP
    "8081"  # HTTP port
    "8080"  # File server
)

for port in "${expected_ports[@]}"; do
    if grep -q "$port" "$HEALTH_CHECK_SCRIPT"; then
        log_pass "References port $port"
    else
        log_fail "Does not reference port $port"
    fi
done
echo ""

# Test 6: Script has proper exit code handling
log_test "Checking exit code handling"

if grep -q "exit 0" "$HEALTH_CHECK_SCRIPT" && grep -q "exit 1" "$HEALTH_CHECK_SCRIPT"; then
    log_pass "Has proper exit codes (0 for success, 1 for failure)"
else
    log_fail "Missing proper exit code handling"
fi
echo ""

# Test 7: Script can run without Docker (graceful failure)
log_test "Testing behavior when Docker is not available"

if ! command -v docker &>/dev/null; then
    log_skip "Docker not installed, testing error handling"
    
    # Run script and expect it to fail gracefully
    if ! "$HEALTH_CHECK_SCRIPT" &>/dev/null; then
        log_pass "Script exits with non-zero when Docker is not available"
    else
        log_fail "Script should exit with error when Docker is not available"
    fi
else
    log_skip "Docker is installed, skipping no-Docker test"
fi
echo ""

# Test 8: Script handles missing container gracefully
log_test "Testing behavior when container is not running"

if command -v docker &>/dev/null && docker info &>/dev/null; then
    # Check if AssettoServer container exists
    if ! docker ps --format '{{.Names}}' | grep -q "^assettoserver$"; then
        log_skip "AssettoServer container not running (expected for test environment)"
        
        # Script should run but report unhealthy
        if ! "$HEALTH_CHECK_SCRIPT" &>/dev/null; then
            log_pass "Script exits with non-zero when container is missing"
        else
            log_fail "Script should report unhealthy when container is missing"
        fi
    else
        log_skip "AssettoServer container is running, skipping missing container test"
    fi
else
    log_skip "Docker not available, skipping container test"
fi
echo ""

# Test 9: Script output contains expected sections
log_test "Checking output structure"

if command -v docker &>/dev/null; then
    output=$("$HEALTH_CHECK_SCRIPT" 2>&1 || true)
    
    # Core sections that should always appear
    core_sections=(
        "Health Check"
        "Docker"
        "container"
        "status"
    )
    
    for section in "${core_sections[@]}"; do
        if echo "$output" | grep -qi "$section"; then
            log_pass "Output contains reference to: $section"
        else
            log_fail "Output missing reference to: $section"
        fi
    done
    
    # Optional sections that may not appear if container is not running
    optional_sections=(
        "socket\|port"
        "endpoint\|HTTP"
        "log"
        "Summary"
    )
    
    for section in "${optional_sections[@]}"; do
        if echo "$output" | grep -qiE "$section"; then
            log_pass "Output contains reference to: $(echo $section | sed 's/\\|/ or /')"
        else
            log_skip "Output missing optional reference to: $(echo $section | sed 's/\\|/ or /') (may not appear without running container)"
        fi
    done
else
    log_skip "Docker not available, skipping output test"
fi
echo ""

# Test 10: Script checks for status file
log_test "Verifying deployment status file check"

if grep -q "/opt/assettoserver/deploy-status.json" "$HEALTH_CHECK_SCRIPT"; then
    log_pass "Checks for deployment status file"
else
    log_fail "Does not check for deployment status file"
fi
echo ""

# Summary
echo "========================================"
echo "Test Summary"
echo "========================================"

if [ $TEST_FAILURES -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
    exit 0
else
    echo -e "${RED}✗ $TEST_FAILURES test(s) failed${NC}"
    exit 1
fi
