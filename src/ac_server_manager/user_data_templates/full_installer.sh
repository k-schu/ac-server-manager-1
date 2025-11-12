#!/bin/bash
set -euo pipefail

# Full AC Server Installer Script
# This script is uploaded to S3 and downloaded by the bootstrap user-data
# Environment variables: S3_BUCKET, S3_KEY, PRESIGNED_URL, AC_SERVER_*_PORT

# Configuration
DEPLOY_LOG="/var/log/acserver-deploy.log"
STATUS_FILE="/opt/acserver/deploy-status.json"
VALIDATION_TIMEOUT=120
AC_SERVER_TCP_PORT=${AC_SERVER_TCP_PORT:-9600}
AC_SERVER_UDP_PORT=${AC_SERVER_UDP_PORT:-9600}
AC_SERVER_HTTP_PORT=${AC_SERVER_HTTP_PORT:-8081}
AC_SERVER_WRAPPER_PORT=${AC_SERVER_WRAPPER_PORT:-8080}

# Logging function
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DEPLOY_LOG"
}

# Error tracking
declare -a ERROR_MESSAGES=()

add_error() {
    ERROR_MESSAGES+=("$1")
    log_message "✗ ERROR: $1"
}

# Write status JSON
write_status() {
    local success=$1
    local public_ip=$2
    local has_wrapper=${3:-false}
    local timestamp=$(date -Iseconds)
    
    cat > "$STATUS_FILE" << STATUSEOF
{
  "success": $success,
  "timestamp": "$timestamp",
  "public_ip": "$public_ip",
  "ports": {
    "tcp": $AC_SERVER_TCP_PORT,
    "udp": $AC_SERVER_UDP_PORT,
    "http": $AC_SERVER_HTTP_PORT,
    "wrapper": $AC_SERVER_WRAPPER_PORT
  },
  "wrapper_enabled": $has_wrapper,
  "error_messages": [
    $(printf '"%s"' "${ERROR_MESSAGES[@]}" | paste -sd, -)
  ]
}
STATUSEOF
    log_message "Status written to $STATUS_FILE"
}

# Main deployment script
log_message "===== Starting AC Server Installation ====="

# Install remaining required packages
log_message "Installing additional packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq unzip wget tar jq file iproute2 net-tools lib32gcc-s1 lib32stdc++6 2>&1 | tee -a "$DEPLOY_LOG"

# Create directory for AC server
log_message "Creating server directory..."
mkdir -p /opt/acserver
cd /opt/acserver

# Download pack from S3 with retries
log_message "Downloading server pack from S3..."
MAX_RETRIES=3
RETRY_DELAY=5
for attempt in $(seq 1 $MAX_RETRIES); do
    if [ -n "${PRESIGNED_URL:-}" ]; then
        # Use presigned URL with curl
        if curl -fsSL "$PRESIGNED_URL" -o ./server-pack.tar.gz 2>&1 | tee -a "$DEPLOY_LOG"; then
            log_message "✓ Download successful via presigned URL"
            break
        fi
    else
        # Use AWS CLI with instance profile
        if aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" ./server-pack.tar.gz 2>&1 | tee -a "$DEPLOY_LOG"; then
            log_message "✓ Download successful via AWS CLI"
            break
        fi
    fi
    
    if [ $attempt -eq $MAX_RETRIES ]; then
        add_error "Failed to download pack from S3 after $MAX_RETRIES attempts"
        PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
        write_status false "$PUBLIC_IP"
        exit 1
    fi
    log_message "Download attempt $attempt failed, retrying in $RETRY_DELAY seconds..."
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
done

# Verify downloaded file
if [ ! -f "./server-pack.tar.gz" ] || [ ! -s "./server-pack.tar.gz" ]; then
    add_error "Downloaded file is missing or empty"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    write_status false "$PUBLIC_IP"
    exit 1
fi

# Extract pack
log_message "Extracting server pack..."
if tar -xzf server-pack.tar.gz 2>&1 | tee -a "$DEPLOY_LOG"; then
    log_message "✓ Extraction successful"
else
    add_error "Failed to extract server pack - file may be corrupted"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    write_status false "$PUBLIC_IP"
    exit 1
fi

# Locate the server executable
log_message "Locating acServer executable..."
ACSERVER_PATH=""

# Search for acServer binary - check common locations first
if [ -f "./acServer" ] && [ -x "./acServer" ]; then
    ACSERVER_PATH="./acServer"
elif [ -f "./acServer" ]; then
    ACSERVER_PATH="./acServer"
else
    # Search in subdirectories
    FOUND_BINARIES=$(find /opt/acserver -maxdepth 3 -type f \( -name "acServer*" -o -name "acserver*" \) 2>/dev/null || true)
    
    if [ -n "$FOUND_BINARIES" ]; then
        # Prefer executables
        for binary in $FOUND_BINARIES; do
            if [ -x "$binary" ]; then
                ACSERVER_PATH="$binary"
                break
            fi
        done
        
        # If no executable found, take first match
        if [ -z "$ACSERVER_PATH" ]; then
            ACSERVER_PATH=$(echo "$FOUND_BINARIES" | head -1)
        fi
    fi
fi

if [ -z "$ACSERVER_PATH" ]; then
    add_error "No acServer binary found in extracted pack"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    write_status false "$PUBLIC_IP"
    exit 1
fi

log_message "Found binary at: $ACSERVER_PATH"

# Convert to absolute path
ACSERVER_PATH=$(readlink -f "$ACSERVER_PATH")
log_message "Absolute path: $ACSERVER_PATH"

# Verify binary is Linux-compatible
log_message "Verifying binary compatibility..."
BINARY_TYPE=$(file "$ACSERVER_PATH")
log_message "Binary type: $BINARY_TYPE"

if echo "$BINARY_TYPE" | grep -q "PE32\|MS Windows"; then
    add_error "Windows PE binary detected - pack must contain Linux acServer binary or use Wine/Proton"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    write_status false "$PUBLIC_IP"
    exit 1
fi

if ! echo "$BINARY_TYPE" | grep -q "ELF"; then
    add_error "Binary is not a Linux ELF executable: $BINARY_TYPE"
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    write_status false "$PUBLIC_IP"
    exit 1
fi

log_message "✓ Binary is a Linux ELF executable"

# Check library dependencies
log_message "Checking library dependencies..."
ldd "$ACSERVER_PATH" 2>&1 | tee -a "$DEPLOY_LOG" || log_message "⚠ Warning: ldd check had issues (may be expected for some binaries)"

# Ensure binary is executable and owned by root
chmod +x "$ACSERVER_PATH"
chown root:root "$ACSERVER_PATH"
log_message "✓ Binary permissions set"

# Get working directory (directory containing the binary)
WORKING_DIR=$(dirname "$ACSERVER_PATH")
log_message "Working directory: $WORKING_DIR"

# Create systemd service
log_message "Creating systemd service..."
cat > /etc/systemd/system/acserver.service << EOFSERVICE
[Unit]
Description=Assetto Corsa Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$WORKING_DIR
ExecStart=$ACSERVER_PATH
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/acserver-stdout.log
StandardError=append:/var/log/acserver-stderr.log

[Install]
WantedBy=multi-user.target
EOFSERVICE

log_message "✓ Systemd service created"

# Enable and start service
log_message "Starting AC server service..."
systemctl daemon-reload
systemctl enable acserver
systemctl start acserver

# Detect and configure acServerWrapper if present
log_message "Checking for acServerWrapper binary..."
WRAPPER_PATH=""
for location in "$WORKING_DIR" "$WORKING_DIR/bin" "$WORKING_DIR/build"; do
    if [ -f "$location/acServerWrapper" ]; then
        WRAPPER_PATH="$location/acServerWrapper"
        log_message "Found acServerWrapper at: $WRAPPER_PATH"
        break
    fi
done

if [ -n "$WRAPPER_PATH" ]; then
    log_message "Setting up acServerWrapper service..."
    
    chmod +x "$WRAPPER_PATH"
    chown root:root "$WRAPPER_PATH"
    
    PRESET_DIR="/opt/acserver/preset"
    mkdir -p "$PRESET_DIR/cm_content"
    log_message "Setup preset: $PRESET_DIR"
    
    [ -d "$WORKING_DIR/cm_content" ] && cp -r "$WORKING_DIR/cm_content" "$PRESET_DIR/" || [ -d "/opt/acserver/cm_content" ] && cp -r /opt/acserver/cm_content "$PRESET_DIR/" || true
    
    CONTENT_JSON=""
    [ -f "$WORKING_DIR/content.json" ] && CONTENT_JSON="$WORKING_DIR/content.json" || [ -f "/opt/acserver/content.json" ] && CONTENT_JSON="/opt/acserver/content.json" || [ -f "$PRESET_DIR/cm_content/content.json" ] && CONTENT_JSON="$PRESET_DIR/cm_content/content.json" || true
    
    if [ -n "$CONTENT_JSON" ]; then
        cp "$CONTENT_JSON" "$PRESET_DIR/content.json"
        log_message "Fixing content.json paths..."
        
        # Use Python for JSON path normalization
        python3 << 'EOFPYTHON'
import json
import os
import re

content_json_path = "/opt/acserver/preset/content.json"

try:
    with open(content_json_path, 'r') as f:
        data = json.load(f)
    
    def normalize_path(path):
        if not isinstance(path, str):
            return path
        path = re.sub(r'^[A-Za-z]:[/\\]', '', path)
        path = path.replace('\\', '/')
        path = path.lstrip('/')
        if not path.startswith('cm_content/'):
            filename = os.path.basename(path)
            path = 'cm_content/' + filename
        return path
    
    def process_value(obj):
        if isinstance(obj, dict):
            result = {}
            for k in obj:
                result[k] = process_value(obj[k])
            return result
        elif isinstance(obj, list):
            return [process_value(item) for item in obj]
        elif isinstance(obj, str):
            if '/' in obj or '\\' in obj or re.search(r'\.[a-zA-Z0-9]+$', obj):
                return normalize_path(obj)
            return obj
        else:
            return obj
    
    normalized_data = process_value(data)
    
    with open(content_json_path, 'w') as f:
        json.dump(normalized_data, f, indent=2)
    
    print("✓ content.json normalized successfully")
except Exception as e:
    print("⚠ Warning: Failed to normalize content.json: " + str(e))
EOFPYTHON
        
        log_message "✓ content.json fixed"
    else
        log_message "⚠ No content.json found"
    fi
    
    # Look for existing cm_wrapper_params.json in the pack
    WRAPPER_PARAMS=""
    if [ -f "$WORKING_DIR/cm_wrapper_params.json" ]; then
        WRAPPER_PARAMS="$WORKING_DIR/cm_wrapper_params.json"
    elif [ -f "/opt/acserver/cm_wrapper_params.json" ]; then
        WRAPPER_PARAMS="/opt/acserver/cm_wrapper_params.json"
    fi
    
    [ -n "$WRAPPER_PARAMS" ] && cp "$WRAPPER_PARAMS" "$PRESET_DIR/cm_wrapper_params.json" || echo "{\"port\":$AC_SERVER_WRAPPER_PORT,\"enabled\":true}" > "$PRESET_DIR/cm_wrapper_params.json"
    
    chown -R root:root "$PRESET_DIR"
    chmod -R 755 "$PRESET_DIR"
    
    cat > /etc/systemd/system/acserver-wrapper.service << EOFWRAPPER
[Unit]
Description=AC Server Wrapper (Content Manager file server)
After=network.target acserver.service
Requires=acserver.service

[Service]
Type=simple
User=root
WorkingDirectory=$PRESET_DIR
ExecStart=$WRAPPER_PATH $PRESET_DIR
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/acserver-wrapper-stdout.log
StandardError=append:/var/log/acserver-wrapper-stderr.log

[Install]
WantedBy=multi-user.target
EOFWRAPPER
    
    log_message "✓ acServerWrapper systemd service created"
    log_message "Preset directory: $PRESET_DIR"
    
    # Enable and start wrapper service
    systemctl daemon-reload
    systemctl enable acserver-wrapper
    systemctl start acserver-wrapper
    log_message "✓ acServerWrapper service started"
else
    log_message "ℹ acServerWrapper not found - skipping wrapper setup"
fi

# Wait for server to start
log_message "Waiting for server to initialize (timeout: ${VALIDATION_TIMEOUT}s)..."
sleep 10

# Run validation checks
log_message "===== Starting Post-Boot Validation ====="
validation_failed=false

# Get public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
log_message "Public IP: $PUBLIC_IP"

# Check if process is running
log_message "Checking if acServer process is running..."
PROCESS_NAME=$(basename "$ACSERVER_PATH")
elapsed=0
process_running=false

while [ $elapsed -lt $VALIDATION_TIMEOUT ]; do
    if pgrep -f "$ACSERVER_PATH" > /dev/null || pgrep -x "$PROCESS_NAME" > /dev/null; then
        PROCESS_PID=$(pgrep -f "$ACSERVER_PATH" | head -1)
        log_message "✓ acServer process is running (PID: $PROCESS_PID)"
        process_running=true
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ "$process_running" = false ]; then
    add_error "acServer process is not running after ${VALIDATION_TIMEOUT}s"
    validation_failed=true
    log_message "Systemd service status:"
    systemctl status acserver 2>&1 | tee -a "$DEPLOY_LOG" || true
    log_message "Service logs:"
    journalctl -u acserver -n 50 --no-pager 2>&1 | tee -a "$DEPLOY_LOG" || true
fi

# Check if ports are listening
log_message "Checking if required ports are listening..."
sleep 5

check_port_listening() {
    local proto=$1
    local port=$2
    local port_type=$3
    
    if [ "$proto" = "tcp" ]; then
        if ss -tlnp 2>/dev/null | grep -q ":$port " || netstat -tlnp 2>/dev/null | grep -q ":$port "; then
            log_message "✓ TCP port $port ($port_type) is listening"
            return 0
        else
            add_error "TCP port $port ($port_type) is not listening"
            return 1
        fi
    else
        if ss -ulnp 2>/dev/null | grep -q ":$port " || netstat -ulnp 2>/dev/null | grep -q ":$port "; then
            log_message "✓ UDP port $port ($port_type) is listening"
            return 0
        else
            add_error "UDP port $port ($port_type) is not listening"
            return 1
        fi
    fi
}

if ! check_port_listening tcp $AC_SERVER_TCP_PORT "game"; then
    validation_failed=true
fi

if ! check_port_listening udp $AC_SERVER_UDP_PORT "game"; then
    validation_failed=true
fi

if ! check_port_listening tcp $AC_SERVER_HTTP_PORT "HTTP"; then
    validation_failed=true
fi

# Check wrapper port if wrapper was configured
if [ -n "$WRAPPER_PATH" ]; then
    log_message "Checking acServerWrapper port..."
    if check_port_listening tcp $AC_SERVER_WRAPPER_PORT "wrapper"; then
        log_message "✓ acServerWrapper is listening on port $AC_SERVER_WRAPPER_PORT"
    else
        log_message "⚠ Warning: acServerWrapper port not listening (wrapper may still be starting)"
    fi
fi

# Check HTTP health endpoint
log_message "Checking HTTP endpoint..."
if curl -sS --max-time 5 http://127.0.0.1:$AC_SERVER_HTTP_PORT/ > /dev/null 2>&1; then
    log_message "✓ HTTP endpoint is responding"
else
    log_message "⚠ Warning: HTTP endpoint not responding (may be expected for some server configs)"
fi

# Construct and check acstuff join link
log_message "Checking acstuff join link..."
ACSTUFF_URL="http://acstuff.ru/s/q:race/online/join?ip=$PUBLIC_IP&httpPort=$AC_SERVER_HTTP_PORT"
log_message "acstuff URL: $ACSTUFF_URL"

if curl -sS --max-time 5 "$ACSTUFF_URL" > /dev/null 2>&1; then
    log_message "✓ acstuff join link is reachable"
else
    log_message "⚠ Warning: acstuff join link not reachable (may be due to external service)"
fi

# Check server logs for errors
log_message "Checking server logs for common errors..."
LOG_FILES=$(find /opt/acserver -type f -name "*.txt" -o -name "*.log" 2>/dev/null | head -5)

if [ -n "$LOG_FILES" ]; then
    for log_file in $LOG_FILES; do
        if [ -f "$log_file" ] && [ -r "$log_file" ]; then
            log_message "Checking log: $log_file"
            
            # Check for common error patterns
            if grep -qi "track not found\|content not found\|missing track\|missing car" "$log_file" 2>/dev/null; then
                add_error "Missing content detected in server logs"
                grep -i "track not found\|content not found\|missing track\|missing car" "$log_file" 2>/dev/null | tail -3 | while read line; do
                    log_message "  $line"
                done
                validation_failed=true
            fi
            
            if grep -qi "failed to bind\|port.*in use\|address already in use" "$log_file" 2>/dev/null; then
                add_error "Port binding errors detected in server logs"
                grep -i "failed to bind\|port.*in use\|address already in use" "$log_file" 2>/dev/null | tail -3 | while read line; do
                    log_message "  $line"
                done
                validation_failed=true
            fi
            
            if grep -qi "permission denied\|segmentation fault\|core dumped" "$log_file" 2>/dev/null; then
                add_error "Critical errors detected in server logs"
                grep -i "permission denied\|segmentation fault\|core dumped" "$log_file" 2>/dev/null | tail -3 | while read line; do
                    log_message "  $line"
                done
                validation_failed=true
            fi
        fi
    done
else
    log_message "⚠ Warning: No server log files found yet"
fi

# Final validation result
if [ "$validation_failed" = true ]; then
    log_message "===== VALIDATION FAILED ====="
    log_message "Deployment completed with errors. Server may not be fully functional."
    log_message "Check status file: $STATUS_FILE"
    log_message "Check deployment log: $DEPLOY_LOG"
    log_message "Check systemd status: systemctl status acserver"
    log_message "Check service logs: journalctl -u acserver -n 50"
    
    HAS_WRAPPER="false"
    if [ -n "$WRAPPER_PATH" ]; then
        HAS_WRAPPER="true"
    fi
    write_status false "$PUBLIC_IP" "$HAS_WRAPPER"
    exit 1
else
    log_message "===== VALIDATION PASSED ====="
    log_message "AC Server deployment and validation completed successfully"
    log_message "Server is accessible at: $PUBLIC_IP:$AC_SERVER_TCP_PORT"
    log_message "acstuff join link: $ACSTUFF_URL"
    
    HAS_WRAPPER="false"
    if [ -n "$WRAPPER_PATH" ]; then
        HAS_WRAPPER="true"
        log_message "acServerWrapper is running on port $AC_SERVER_WRAPPER_PORT"
    fi
    
    write_status true "$PUBLIC_IP" "$HAS_WRAPPER"
    exit 0
fi
