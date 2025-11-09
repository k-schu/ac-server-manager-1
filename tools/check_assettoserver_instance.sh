#!/bin/bash
# Health check script for AssettoServer Docker deployments
# Verifies container status, network ports, and HTTP endpoints
# Exit code: 0 = healthy, 1 = unhealthy

set -eo pipefail

# Configuration
CONTAINER_NAME="assettoserver"
GAME_PORT_UDP=9600
GAME_PORT_TCP=9600
HTTP_PORT=8081
FILE_SERVER_PORT=8080

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall health
HEALTH_ISSUES=0

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    HEALTH_ISSUES=$((HEALTH_ISSUES + 1))
}

echo "======================================"
echo "AssettoServer Health Check"
echo "======================================"
echo ""

# Check 1: Docker daemon running
echo "[1/6] Checking Docker daemon..."
if ! command -v docker &>/dev/null; then
    log_error "Docker is not installed"
    exit 1
fi

if ! docker info &>/dev/null; then
    log_error "Docker daemon is not running"
    exit 1
fi
log_info "Docker daemon is running"
echo ""

# Check 2: Container status
echo "[2/6] Checking container status..."
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_info "Container '${CONTAINER_NAME}' is running"
    
    # Show container details
    echo "  Container details:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | tail -n +2 | sed 's/^/    /'
else
    log_error "Container '${CONTAINER_NAME}' is not running"
    
    # Check if container exists but is stopped
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "Container exists but is stopped. Status:"
        docker ps -a --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}" | tail -n +2 | sed 's/^/    /'
    else
        log_warn "Container does not exist"
    fi
fi
echo ""

# Check 3: Listening sockets
echo "[3/6] Checking listening sockets..."

check_listening_port() {
    local port=$1
    local proto=$2
    local description=$3
    
    if command -v ss &>/dev/null; then
        if [ "$proto" = "udp" ]; then
            if ss -ulnp 2>/dev/null | grep -q ":${port} "; then
                log_info "${description} (${proto}/${port}) is listening"
                return 0
            fi
        else
            if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
                log_info "${description} (${proto}/${port}) is listening"
                return 0
            fi
        fi
    elif command -v netstat &>/dev/null; then
        if [ "$proto" = "udp" ]; then
            if netstat -ulnp 2>/dev/null | grep -q ":${port} "; then
                log_info "${description} (${proto}/${port}) is listening"
                return 0
            fi
        else
            if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
                log_info "${description} (${proto}/${port}) is listening"
                return 0
            fi
        fi
    else
        log_warn "Neither ss nor netstat available, skipping port check"
        return 0
    fi
    
    log_error "${description} (${proto}/${port}) is NOT listening"
    return 1
}

check_listening_port "$GAME_PORT_UDP" "udp" "Game port"
check_listening_port "$GAME_PORT_TCP" "tcp" "Game port"
check_listening_port "$HTTP_PORT" "tcp" "HTTP port"
check_listening_port "$FILE_SERVER_PORT" "tcp" "File server"

# Show all listening UDP and TCP ports
echo "  All listening sockets:"
if command -v ss &>/dev/null; then
    echo "    TCP:"
    ss -tlnp 2>/dev/null | grep LISTEN | sed 's/^/      /' | head -20 || echo "      (none)"
    echo "    UDP:"
    ss -ulnp 2>/dev/null | sed 's/^/      /' | head -20 || echo "      (none)"
elif command -v netstat &>/dev/null; then
    echo "    TCP:"
    netstat -tlnp 2>/dev/null | grep LISTEN | sed 's/^/      /' | head -20 || echo "      (none)"
    echo "    UDP:"
    netstat -ulnp 2>/dev/null | sed 's/^/      /' | head -20 || echo "      (none)"
fi
echo ""

# Check 4: HTTP endpoint
echo "[4/6] Checking HTTP endpoints..."

check_http_endpoint() {
    local port=$1
    local description=$2
    local timeout=${3:-5}
    
    if command -v curl &>/dev/null; then
        if curl -sS --max-time "$timeout" "http://127.0.0.1:${port}/" &>/dev/null; then
            log_info "${description} (http://127.0.0.1:${port}/) is responding"
            return 0
        fi
    elif command -v wget &>/dev/null; then
        if wget -q --timeout="$timeout" --spider "http://127.0.0.1:${port}/" &>/dev/null; then
            log_info "${description} (http://127.0.0.1:${port}/) is responding"
            return 0
        fi
    else
        log_warn "Neither curl nor wget available, skipping HTTP check"
        return 0
    fi
    
    log_warn "${description} (http://127.0.0.1:${port}/) is not responding (may be normal if not configured)"
    return 0  # Don't count as error since some endpoints may not respond
}

check_http_endpoint "$HTTP_PORT" "Main HTTP endpoint"
check_http_endpoint "$FILE_SERVER_PORT" "File server endpoint"
echo ""

# Check 5: Container logs (last 200 lines)
echo "[5/6] Recent container logs..."
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "  Last 50 log lines (errors highlighted):"
    docker logs --tail 200 "$CONTAINER_NAME" 2>&1 | tail -50 | while IFS= read -r line; do
        if echo "$line" | grep -iE "error|exception|fatal|fail" &>/dev/null; then
            echo -e "    ${RED}${line}${NC}"
        else
            echo "    $line"
        fi
    done
else
    log_warn "Container not running, cannot show logs"
fi
echo ""

# Check 6: Deployment status file
echo "[6/6] Checking deployment status..."
STATUS_FILE="/opt/assettoserver/deploy-status.json"
if [ -f "$STATUS_FILE" ]; then
    log_info "Deployment status file exists:"
    cat "$STATUS_FILE" | sed 's/^/    /'
    
    # Parse status
    if command -v jq &>/dev/null; then
        STATUS=$(jq -r '.status' "$STATUS_FILE" 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "started" ]; then
            log_info "Deployment status: started"
        elif [ "$STATUS" = "failed" ]; then
            log_error "Deployment status: failed"
            DETAIL=$(jq -r '.detail' "$STATUS_FILE" 2>/dev/null || echo "No details")
            log_error "Failure detail: $DETAIL"
        else
            log_warn "Deployment status: $STATUS"
        fi
    fi
else
    log_warn "Deployment status file not found at $STATUS_FILE"
fi
echo ""

# Summary
echo "======================================"
echo "Health Check Summary"
echo "======================================"
if [ $HEALTH_ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed - server appears healthy${NC}"
    exit 0
else
    echo -e "${RED}✗ Found $HEALTH_ISSUES issue(s) - server may not be functioning correctly${NC}"
    echo ""
    echo "Troubleshooting tips:"
    echo "  1. Check deployment logs: cat /var/log/assettoserver-deploy.log"
    echo "  2. Review container logs: docker logs $CONTAINER_NAME"
    echo "  3. Check docker compose: cd /opt/assettoserver && docker compose ps"
    echo "  4. Restart container: cd /opt/assettoserver && docker compose restart"
    echo "  5. Check security group allows UDP/TCP ports: 9600/udp, 9600/tcp, 8081/tcp, 8080/tcp"
    exit 1
fi
