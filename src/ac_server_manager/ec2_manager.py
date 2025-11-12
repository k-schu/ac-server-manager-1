"""EC2 operations for AC Server Manager."""

import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .config import (
    AC_SERVER_HTTP_PORT,
    AC_SERVER_TCP_PORT,
    AC_SERVER_UDP_PORT,
    AC_SERVER_WRAPPER_PORT,
)

logger = logging.getLogger(__name__)


class EC2Manager:
    """Manages EC2 operations for AC server deployment."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize EC2 manager.

        Args:
            region: AWS region
        """
        self.region = region
        self.ec2_client = boto3.client("ec2", region_name=region)
        self.ec2_resource = boto3.resource("ec2", region_name=region)

    def create_security_group(
        self, group_name: str, description: str, wrapper_port: Optional[int] = None
    ) -> Optional[str]:
        """Create security group with rules for AC server.

        Args:
            group_name: Name of the security group
            description: Description of the security group
            wrapper_port: Custom wrapper port (uses default if None)

        Returns:
            Security group ID, or None if creation failed
        """
        try:
            # Check if security group already exists
            response = self.ec2_client.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [group_name]}]
            )

            if response["SecurityGroups"]:
                group_id = response["SecurityGroups"][0]["GroupId"]
                logger.info(f"Security group {group_name} already exists: {group_id}")
                return group_id

            # Create security group
            create_response = self.ec2_client.create_security_group(
                GroupName=group_name, Description=description
            )
            group_id = create_response["GroupId"]
            logger.info(f"Created security group {group_name}: {group_id}")

            # Use the provided wrapper port or fall back to default
            effective_wrapper_port = (
                wrapper_port if wrapper_port is not None else AC_SERVER_WRAPPER_PORT
            )

            # Add ingress rules for AC server
            self.ec2_client.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH"}],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 80,
                        "ToPort": 80,
                        "IpRanges": [
                            {"CidrIp": "0.0.0.0/0", "Description": "AC Server Wrapper (HTTP)"}
                        ],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": AC_SERVER_HTTP_PORT,
                        "ToPort": AC_SERVER_HTTP_PORT,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "AC HTTP"}],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": AC_SERVER_TCP_PORT,
                        "ToPort": AC_SERVER_TCP_PORT,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "AC TCP"}],
                    },
                    {
                        "IpProtocol": "udp",
                        "FromPort": AC_SERVER_UDP_PORT,
                        "ToPort": AC_SERVER_UDP_PORT,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "AC UDP"}],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": effective_wrapper_port,
                        "ToPort": effective_wrapper_port,
                        "IpRanges": [
                            {"CidrIp": "0.0.0.0/0", "Description": "AC Server Wrapper (Alt)"}
                        ],
                    },
                ],
            )
            logger.info(f"Added ingress rules to security group {group_id}")

            return group_id
        except ClientError as e:
            logger.error(f"Error creating security group: {e}")
            return None

    def get_ubuntu_ami(self) -> Optional[str]:
        """Get the latest Ubuntu 22.04 LTS AMI ID.

        Returns:
            AMI ID, or None if not found
        """
        try:
            # Get latest Ubuntu 22.04 LTS AMI
            response = self.ec2_client.describe_images(
                Filters=[
                    {
                        "Name": "name",
                        "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
                    },
                    {"Name": "state", "Values": ["available"]},
                    {"Name": "architecture", "Values": ["x86_64"]},
                ],
                Owners=["099720109477"],  # Canonical
            )

            if not response["Images"]:
                logger.error("No Ubuntu AMI found")
                return None

            # Sort by creation date and get the latest
            images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
            ami_id: str = images[0]["ImageId"]
            logger.info(f"Found Ubuntu AMI: {ami_id}")
            return ami_id
        except ClientError as e:
            logger.error(f"Error getting AMI: {e}")
            return None

    def create_user_data_script(
        self, s3_bucket: str, s3_key: str, wrapper_port: Optional[int] = None
    ) -> str:
        """Create user data script for instance initialization.

        Args:
            s3_bucket: S3 bucket containing the pack file
            s3_key: S3 key of the pack file
            wrapper_port: Custom wrapper port (uses default if None)

        Returns:
            User data script as string
        """
        effective_wrapper_port = (
            wrapper_port if wrapper_port is not None else AC_SERVER_WRAPPER_PORT
        )
        script = f"""#!/bin/bash
set -euo pipefail

# Configuration
DEPLOY_LOG="/var/log/acserver-deploy.log"
STATUS_FILE="/opt/acserver/deploy-status.json"
VALIDATION_TIMEOUT=120
AC_SERVER_TCP_PORT={AC_SERVER_TCP_PORT}
AC_SERVER_UDP_PORT={AC_SERVER_UDP_PORT}
AC_SERVER_HTTP_PORT={AC_SERVER_HTTP_PORT}
AC_SERVER_WRAPPER_PORT={effective_wrapper_port}

# Logging function - logs to both file and cloud-init output
log_message() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DEPLOY_LOG"
}}

# Error tracking
declare -a ERROR_MESSAGES=()

add_error() {{
    ERROR_MESSAGES+=("$1")
    log_message "✗ ERROR: $1"
}}

# Write status JSON
write_status() {{
    local success=$1
    local public_ip=$2
    local has_wrapper=${{3:-false}}
    local timestamp=$(date -Iseconds)
    
    cat > "$STATUS_FILE" << STATUSEOF
{{
  "success": $success,
  "timestamp": "$timestamp",
  "public_ip": "$public_ip",
  "ports": {{
    "tcp": $AC_SERVER_TCP_PORT,
    "udp": $AC_SERVER_UDP_PORT,
    "http": $AC_SERVER_HTTP_PORT,
    "wrapper": $AC_SERVER_WRAPPER_PORT
  }},
  "wrapper_enabled": $has_wrapper,
  "error_messages": [
    $(printf '"%s"' "${{ERROR_MESSAGES[@]}}" | paste -sd, -)
  ]
}}
STATUSEOF
    log_message "Status written to $STATUS_FILE"
}}

# Main deployment script
log_message "===== Starting AC Server Deployment ====="

# Update system and install required packages
log_message "Installing required packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq awscli unzip wget tar jq file iproute2 net-tools lib32gcc-s1 lib32stdc++6 2>&1 | tee -a "$DEPLOY_LOG"

# Create directory for AC server
log_message "Creating server directory..."
mkdir -p /opt/acserver
cd /opt/acserver

# Download pack from S3 with retries
log_message "Downloading server pack from S3..."
MAX_RETRIES=3
RETRY_DELAY=5
for attempt in $(seq 1 $MAX_RETRIES); do
    if aws s3 cp s3://{s3_bucket}/{s3_key} ./server-pack.tar.gz 2>&1 | tee -a "$DEPLOY_LOG"; then
        log_message "✓ Download successful"
        break
    else
        if [ $attempt -eq $MAX_RETRIES ]; then
            add_error "Failed to download pack from S3 after $MAX_RETRIES attempts"
            PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
            write_status false "$PUBLIC_IP"
            exit 1
        fi
        log_message "Download attempt $attempt failed, retrying in $RETRY_DELAY seconds..."
        sleep $RETRY_DELAY
        RETRY_DELAY=$((RETRY_DELAY * 2))
    fi
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
    FOUND_BINARIES=$(find /opt/acserver -maxdepth 3 -type f \\( -name "acServer*" -o -name "acserver*" \\) 2>/dev/null || true)
    
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

if echo "$BINARY_TYPE" | grep -q "PE32\\|MS Windows"; then
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
        # Normalize file paths to be relative to the preset directory
        # The wrapper serves files from $PRESET_DIR, and content files are in $PRESET_DIR/cm_content/
        # Strategy: Remove absolute path prefixes and ensure paths start with cm_content/
        
        # Use Python for more reliable JSON path normalization
        python3 << 'EOFPYTHON'
import json
import os
import re

content_json_path = "/opt/acserver/preset/content.json"

try:
    with open(content_json_path, 'r') as f:
        data = json.load(f)
    
    # Helper function to normalize a path
    def normalize_path(path):
        if not isinstance(path, str):
            return path
        
        # Remove Windows drive letters and convert backslashes
        # C:\\\\path\\\\to\\\\file -> path\\\\to\\\\file
        path = re.sub(r'^[A-Za-z]:[/\\\\\\\\]', '', path)
        
        # Convert all backslashes to forward slashes
        path = path.replace('\\\\\\\\', '/')
        
        # Remove leading slashes
        path = path.lstrip('/')
        
        # If path doesn't start with cm_content/, prepend it
        if not path.startswith('cm_content/'):
            # Extract just the filename if it's a full path
            filename = os.path.basename(path)
            path = 'cm_content/' + filename
        
        return path
    
    # Recursively process all string values in the JSON
    def process_value(obj):
        if isinstance(obj, dict):
            result = {{}}
            for k in obj:
                result[k] = process_value(obj[k])
            return result
        elif isinstance(obj, list):
            return [process_value(item) for item in obj]
        elif isinstance(obj, str):
            # Only normalize if it looks like a file path (contains / or \\\\\\\\ or has file extension)
            if '/' in obj or '\\\\\\\\' in obj or re.search(r'\\\\.\\[a-zA-Z0-9]+$', obj):
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
    
    [ -n "$WRAPPER_PARAMS" ] && cp "$WRAPPER_PARAMS" "$PRESET_DIR/cm_wrapper_params.json" || echo "{{\\"port\\":$AC_SERVER_WRAPPER_PORT,\\"enabled\\":true}}" > "$PRESET_DIR/cm_wrapper_params.json"
    
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
log_message "Waiting for server to initialize (timeout: ${{VALIDATION_TIMEOUT}}s)..."
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
    add_error "acServer process is not running after ${{VALIDATION_TIMEOUT}}s"
    validation_failed=true
    log_message "Systemd service status:"
    systemctl status acserver 2>&1 | tee -a "$DEPLOY_LOG" || true
    log_message "Service logs:"
    journalctl -u acserver -n 50 --no-pager 2>&1 | tee -a "$DEPLOY_LOG" || true
fi

# Check if ports are listening
log_message "Checking if required ports are listening..."
sleep 5  # Give server time to bind ports

check_port_listening() {{
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
}}

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
            if grep -qi "track not found\\|content not found\\|missing track\\|missing car" "$log_file" 2>/dev/null; then
                add_error "Missing content detected in server logs"
                grep -i "track not found\\|content not found\\|missing track\\|missing car" "$log_file" 2>/dev/null | tail -3 | while read line; do
                    log_message "  $line"
                done
                validation_failed=true
            fi
            
            if grep -qi "failed to bind\\|port.*in use\\|address already in use" "$log_file" 2>/dev/null; then
                add_error "Port binding errors detected in server logs"
                grep -i "failed to bind\\|port.*in use\\|address already in use" "$log_file" 2>/dev/null | tail -3 | while read line; do
                    log_message "  $line"
                done
                validation_failed=true
            fi
            
            if grep -qi "permission denied\\|segmentation fault\\|core dumped" "$log_file" 2>/dev/null; then
                add_error "Critical errors detected in server logs"
                grep -i "permission denied\\|segmentation fault\\|core dumped" "$log_file" 2>/dev/null | tail -3 | while read line; do
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
"""
        return script

    def launch_instance(
        self,
        ami_id: str,
        instance_type: str,
        security_group_id: str,
        user_data: str,
        instance_name: str,
        key_name: Optional[str] = None,
        iam_instance_profile: Optional[str] = None,
    ) -> Optional[str]:
        """Launch EC2 instance for AC server.

        Args:
            ami_id: AMI ID to use
            instance_type: EC2 instance type
            security_group_id: Security group ID
            user_data: User data script
            instance_name: Name tag for the instance
            key_name: SSH key pair name (optional)
            iam_instance_profile: IAM instance profile name or ARN (optional)

        Returns:
            Instance ID, or None if launch failed
        """
        try:
            from typing import Any, Dict

            launch_params: Dict[str, Any] = {
                "ImageId": ami_id,
                "InstanceType": instance_type,
                "SecurityGroupIds": [security_group_id],
                "UserData": user_data,
                "MinCount": 1,
                "MaxCount": 1,
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": instance_name},
                            {"Key": "Application", "Value": "ac-server"},
                        ],
                    }
                ],
            }

            if key_name:
                launch_params["KeyName"] = key_name

            if iam_instance_profile:
                # Support both Name and Arn formats
                if iam_instance_profile.startswith("arn:aws:iam::"):
                    launch_params["IamInstanceProfile"] = {"Arn": iam_instance_profile}
                else:
                    launch_params["IamInstanceProfile"] = {"Name": iam_instance_profile}
                logger.debug(f"Using IAM instance profile: {iam_instance_profile}")

            response = self.ec2_client.run_instances(**launch_params)  # type: ignore[arg-type]
            instance_id = response["Instances"][0]["InstanceId"]
            logger.info(f"Launched instance {instance_id}")

            # Wait for instance to be running
            waiter = self.ec2_client.get_waiter("instance_running")
            waiter.wait(InstanceIds=[instance_id])
            logger.info(f"Instance {instance_id} is running")

            return instance_id
        except ClientError as e:
            logger.error(f"Error launching instance: {e}")
            return None

    def get_instance_public_ip(self, instance_id: str) -> Optional[str]:
        """Get public IP address of an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Public IP address, or None if not found
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            if not response["Reservations"]:
                return None

            instance = response["Reservations"][0]["Instances"][0]
            return instance.get("PublicIpAddress")
        except ClientError as e:
            logger.error(f"Error getting instance IP: {e}")
            return None

    def stop_instance(self, instance_id: str) -> bool:
        """Stop an EC2 instance.

        Args:
            instance_id: Instance ID

        Returns:
            True if stop succeeded, False otherwise
        """
        try:
            self.ec2_client.stop_instances(InstanceIds=[instance_id])
            logger.info(f"Stopped instance {instance_id}")
            return True
        except ClientError as e:
            logger.error(f"Error stopping instance: {e}")
            return False

    def start_instance(self, instance_id: str) -> bool:
        """Start an EC2 instance.

        Args:
            instance_id: Instance ID

        Returns:
            True if start succeeded, False otherwise
        """
        try:
            self.ec2_client.start_instances(InstanceIds=[instance_id])
            logger.info(f"Started instance {instance_id}")
            return True
        except ClientError as e:
            logger.error(f"Error starting instance: {e}")
            return False

    def terminate_instance(self, instance_id: str) -> bool:
        """Terminate an EC2 instance.

        Args:
            instance_id: Instance ID

        Returns:
            True if termination succeeded, False otherwise
        """
        try:
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Terminated instance {instance_id}")
            return True
        except ClientError as e:
            logger.error(f"Error terminating instance: {e}")
            return False

    def terminate_instance_and_wait(self, instance_id: str, dry_run: bool = False) -> bool:
        """Terminate an EC2 instance and wait for termination to complete.

        Args:
            instance_id: Instance ID to terminate
            dry_run: If True, only log what would be done without actually terminating

        Returns:
            True if termination succeeded, False otherwise
        """
        try:
            # Check if instance exists
            try:
                response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
                if not response["Reservations"]:
                    logger.warning(f"Instance {instance_id} not found")
                    return True  # Already gone

                instance_state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
                if instance_state == "terminated":
                    logger.info(f"Instance {instance_id} is already terminated")
                    return True

            except ClientError as e:
                if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                    logger.info(f"Instance {instance_id} not found, already terminated")
                    return True
                raise

            if dry_run:
                logger.info(f"[DRY RUN] Would terminate instance: {instance_id}")
                return True

            # Terminate the instance
            logger.info(f"Terminating instance {instance_id}...")
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Termination initiated for instance {instance_id}")

            # Wait for instance to terminate
            logger.info(f"Waiting for instance {instance_id} to terminate...")
            waiter = self.ec2_client.get_waiter("instance_terminated")
            waiter.wait(
                InstanceIds=[instance_id],
                WaiterConfig={
                    "Delay": 15,  # Check every 15 seconds
                    "MaxAttempts": 40,  # Wait up to 10 minutes
                },
            )
            logger.info(f"Instance {instance_id} has been terminated")
            return True

        except ClientError as e:
            logger.error(f"Error terminating instance {instance_id}: {e}")
            return False

    def find_instances_by_name(self, instance_name: str) -> list[str]:
        """Find instances by name tag.

        Args:
            instance_name: Instance name to search for

        Returns:
            List of instance IDs
        """
        try:
            response = self.ec2_client.describe_instances(
                Filters=[
                    {"Name": "tag:Name", "Values": [instance_name]},
                    {
                        "Name": "instance-state-name",
                        "Values": ["pending", "running", "stopping", "stopped"],
                    },
                ]
            )

            instance_ids = []
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_ids.append(instance["InstanceId"])

            return instance_ids
        except ClientError as e:
            logger.error(f"Error finding instances: {e}")
            return []

    def get_instance_details(self, instance_id: str) -> Optional[dict]:
        """Get detailed information about an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Dictionary with instance details, or None if not found
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            if not response["Reservations"]:
                return None

            instance = response["Reservations"][0]["Instances"][0]

            # Extract relevant information
            details = {
                "instance_id": instance["InstanceId"],
                "state": instance["State"]["Name"],
                "instance_type": instance["InstanceType"],
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "launch_time": instance["LaunchTime"],
            }

            # Extract name tag
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    details["name"] = tag["Value"]
                    break

            return details
        except ClientError as e:
            logger.error(f"Error getting instance details: {e}")
            return None
