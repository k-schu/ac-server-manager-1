"""EC2 operations for AC Server Manager."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .config import AC_SERVER_HTTP_PORT, AC_SERVER_TCP_PORT, AC_SERVER_UDP_PORT

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
        self, group_name: str, description: str, extra_ports: Optional[list[int]] = None
    ) -> Optional[str]:
        """Create security group with rules for AC server.

        Args:
            group_name: Name of the security group
            description: Description of the security group
            extra_ports: Optional list of additional TCP ports to open (e.g., wrapper port)

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

            # Add ingress rules for AC server
            ip_permissions = [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH"}],
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
            ]

            # Add extra ports if specified
            if extra_ports:
                for port in extra_ports:
                    ip_permissions.append(
                        {
                            "IpProtocol": "tcp",
                            "FromPort": port,
                            "ToPort": port,
                            "IpRanges": [
                                {"CidrIp": "0.0.0.0/0", "Description": f"Extra TCP {port}"}
                            ],
                        }
                    )

            self.ec2_client.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=ip_permissions,  # type: ignore[arg-type]
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
        self, s3_bucket: str, s3_key: str, enable_wrapper: bool = True, wrapper_port: int = 8082
    ) -> str:
        """Create user data script for instance initialization.

        Args:
            s3_bucket: S3 bucket containing the pack file
            s3_key: S3 key of the pack file
            enable_wrapper: Whether to install and run ac-server-wrapper (default: True)
            wrapper_port: Port for ac-server-wrapper (default: 8082, must differ from AC HTTP port 8081)

        Returns:
            User data script as string
        """
        # Build wrapper installation script separately to avoid nested f-strings
        wrapper_script = ""
        if enable_wrapper:
            # Minimal bootstrap that downloads and runs a more complete script
            wrapper_script = f"""
# Install ac-server-wrapper in background (non-blocking)
log_message "Scheduling wrapper installation..."
cat > /opt/acserver/install-wrapper.sh << 'EOF'
#!/bin/bash
L="/var/log/acserver-wrapper-install.log"
P={wrapper_port}
log() {{ echo "[$(date '+%H:%M:%S')] $1" | tee -a "$L"; }}
log "Starting wrapper install"
sleep 15
log "Installing Node.js"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >> "$L" 2>&1 && apt-get install -y nodejs >> "$L" 2>&1 || {{ log "Node.js install failed"; exit 1; }}
W="/opt/acserver/wrapper"
D="/opt/acserver/preset"
if [ -d "/opt/acserver/ac-server-wrapper" ]; then mv /opt/acserver/ac-server-wrapper "$W"
elif [ -f "/opt/acserver/ac-server-wrapper.js" ]; then mkdir -p "$W" && mv /opt/acserver/ac-server-wrapper.js "$W/" && mv /opt/acserver/package*.json "$W/" 2>/dev/null || true
else
  mkdir -p "$W" && cd "$W"
  if ! command -v git &>/dev/null; then apt-get install -y git >> "$L" 2>&1; fi
  timeout 60 git clone --depth 1 https://github.com/gro-ove/ac-server-wrapper.git . >> "$L" 2>&1 || {{ log "Clone failed"; exit 1; }}
fi
mkdir -p "$D" "$D/cm_content"
[ -d "$WORKING_DIR/cfg" ] && [ ! -d "$D/cfg" ] && cp -r "$WORKING_DIR"/* "$D/" 2>/dev/null || true
cd "$W"
[ -f "package.json" ] && {{ export NODE_ENV=production; timeout 300 npm ci --production >> "$L" 2>&1 || timeout 300 npm install --production >> "$L" 2>&1 || {{ log "npm failed"; exit 1; }}; }}
chown -R root:root "$W" 2>/dev/null; chmod +x "$W"/*.js 2>/dev/null || true
cat > /etc/systemd/system/acserver-wrapper.service << SVC
[Unit]
Description=AC Server Wrapper
After=network.target acserver.service
Wants=acserver.service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/acserver/wrapper
ExecStart=/usr/bin/node /opt/acserver/wrapper/ac-server-wrapper.js --preset /opt/acserver/preset --port $P
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/acserver-wrapper-stdout.log
StandardError=append:/var/log/acserver-wrapper-stderr.log
[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload && systemctl enable acserver-wrapper >> "$L" 2>&1 && systemctl start acserver-wrapper >> "$L" 2>&1 && log "Wrapper started" || log "Wrapper start failed"
EOF
chmod +x /opt/acserver/install-wrapper.sh
nohup /opt/acserver/install-wrapper.sh &>/dev/null &
log_message "✓ Wrapper install scheduled"
"""

        # Derive PACK_ID from S3 key (sanitized basename)
        import re

        pack_id = re.sub(
            r"[^a-zA-Z0-9-_]", "_", s3_key.split("/")[-1].replace(".tar.gz", "").replace(".zip", "")
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

# Pack ID for content.json patching
export PACK_ID="{pack_id}"

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
    local timestamp=$(date -Iseconds)
    
    cat > "$STATUS_FILE" << STATUSEOF
{{
  "success": $success,
  "timestamp": "$timestamp",
  "public_ip": "$public_ip",
  "ports": {{
    "tcp": $AC_SERVER_TCP_PORT,
    "udp": $AC_SERVER_UDP_PORT,
    "http": $AC_SERVER_HTTP_PORT
  }},
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
apt-get install -y -qq awscli unzip wget tar jq file iproute2 net-tools lib32gcc-s1 lib32stdc++6 python3 2>&1 | tee -a "$DEPLOY_LOG"

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

# PATCH_CONTENT_JSON: Fix Windows absolute paths in content.json files for ac-server-wrapper
log_message "Patching content.json files to work with ac-server-wrapper..."
python3 << 'PYTHON_CONTENT_PATCHER'
import json
import os
import re
import sys
import shutil
from pathlib import Path

def is_windows_absolute_path(s):
    # Check if string looks like a Windows absolute path
    if not isinstance(s, str):
        return False
    # Match drive letter paths: C:\\ or C:/
    if re.match(r'^[a-zA-Z]:[/\\\\]', s):
        return True
    # Match UNC paths: \\\\server\\share
    if re.match(r'^\\\\\\\\[^\\\\]+\\\\[^\\\\]+', s):
        return True
    return False

def normalize_path(path):
    # Normalize backslashes to forward slashes
    return path.replace('\\\\', '/')

def find_file_in_pack(basename, pack_root):
    # Search for file by basename in the pack directory
    for root, dirs, files in os.walk(pack_root):
        for file in files:
            if file.lower() == basename.lower():
                return os.path.join(root, file)
        for dir in dirs:
            if dir.lower() == basename.lower():
                return os.path.join(root, dir)
    return None

def copy_file_to_cm_content(source_path, cm_content_dir, basename, copied_cache):
    # Copy file to cm_content directory and return relative path
    try:
        # Ensure cm_content directory exists
        os.makedirs(cm_content_dir, exist_ok=True)
        
        # Check if already copied
        if basename in copied_cache:
            return copied_cache[basename]
        
        # Destination path in cm_content
        dest_path = os.path.join(cm_content_dir, basename)
        
        # Copy file if source is a file
        if os.path.isfile(source_path):
            shutil.copy2(source_path, dest_path)
            print(f"Copied {{basename}} to cm_content/")
            copied_cache[basename] = basename
            return basename
        elif os.path.isdir(source_path):
            # For directories, copy the entire directory
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(source_path, dest_path)
            print(f"Copied directory {{basename}} to cm_content/")
            copied_cache[basename] = basename
            return basename
        else:
            print(f"Warning: Source path {{source_path}} is neither file nor directory", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Warning: Failed to copy {{basename}}: {{e}}", file=sys.stderr)
        return None

def fix_windows_path_local(path, pack_root, cm_content_dir, copied_cache):
    # Convert Windows absolute path to relative basename by copying to cm_content
    # Normalize backslashes
    normalized = normalize_path(path)
    
    # Split into parts and get basename
    parts = [p for p in normalized.split('/') if p and p != '.']
    
    # Remove drive letter if present
    if parts and re.match(r'^[a-zA-Z]:$', parts[0]):
        parts = parts[1:]
    
    if not parts:
        return path  # Can't process empty path
    
    basename = parts[-1]
    
    # Check if already copied
    if basename in copied_cache:
        return copied_cache[basename]
    
    # Find the actual file in the pack
    local_file_path = find_file_in_pack(basename, pack_root)
    
    if not local_file_path:
        print(f"Warning: File not found for basename '{{basename}}' from path '{{path}}'", file=sys.stderr)
        return path  # Return original if not found
    
    # Copy to cm_content and get relative path
    relative_path = copy_file_to_cm_content(local_file_path, cm_content_dir, basename, copied_cache)
    
    if relative_path:
        return relative_path
    else:
        return path  # Return original if copy failed

def fix_value(value, pack_root, cm_content_dir, copied_cache, key=None):
    # Recursively fix Windows paths in value. Only process 'file' fields, not 'url' fields.
    if isinstance(value, str):
        # Only process if this is a 'file' field (not 'url')
        if key == 'file' and is_windows_absolute_path(value):
            return fix_windows_path_local(value, pack_root, cm_content_dir, copied_cache)
        return value
    elif isinstance(value, dict):
        return {{k: fix_value(v, pack_root, cm_content_dir, copied_cache, k) for k, v in value.items()}}
    elif isinstance(value, list):
        return [fix_value(item, pack_root, cm_content_dir, copied_cache, None) for item in value]
    else:
        return value

def patch_content_json_file(filepath, pack_root, cm_content_dir, copied_cache):
    # Patch Windows paths in a single content.json file with local cm_content paths
    try:
        # Create backup
        backup_path = filepath + '.bak'
        shutil.copy2(filepath, backup_path)
        print(f"Created backup: {{backup_path}}")
        
        # Read and parse
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Fix Windows paths
        patched_data = fix_value(data, pack_root, cm_content_dir, copied_cache)
        
        # Write patched data
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(patched_data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Warning: Failed to process {{filepath}}: {{e}}", file=sys.stderr)
        return False

def adjust_wrapper_port():
    # Adjust cm_wrapper_params.json port from 80 to 8050 if running as non-root
    try:
        wrapper_params_path = '/opt/acserver/preset/cm_wrapper_params.json'
        if not os.path.exists(wrapper_params_path):
            return
        
        with open(wrapper_params_path, 'r', encoding='utf-8') as f:
            params = json.load(f)
        
        # Check if port is 80 and we're not root
        if params.get('port') == 80 and os.geteuid() != 0:
            params['port'] = 8050
            with open(wrapper_params_path, 'w', encoding='utf-8') as f:
                json.dump(params, f, indent=2, ensure_ascii=False)
            print(f"Adjusted wrapper port from 80 to 8050 (non-root user)")
    except Exception as e:
        print(f"Warning: Failed to adjust wrapper port: {{e}}", file=sys.stderr)

def main():
    # Get configuration from environment
    pack_id = os.environ.get('PACK_ID')
    
    if not pack_id:
        print("Error: PACK_ID environment variable must be set", file=sys.stderr)
        sys.exit(1)
    
    pack_root = '/opt/acserver'
    preset_dir = '/opt/acserver/preset'
    cm_content_dir = os.path.join(preset_dir, 'cm_content')
    
    # Ensure preset and cm_content directories exist
    os.makedirs(cm_content_dir, exist_ok=True)
    print(f"Using cm_content directory: {{cm_content_dir}}")
    
    # Cache for copied files (basename -> relative path)
    copied_cache = {{}}
    
    patched_count = 0
    
    # Find all content.json files
    for root, dirs, files in os.walk(pack_root):
        for file in files:
            if file == 'content.json':
                filepath = os.path.join(root, file)
                print(f"Processing {{filepath}}...")
                if patch_content_json_file(filepath, pack_root, cm_content_dir, copied_cache):
                    patched_count += 1
    
    print(f"Patched {{patched_count}} content.json file(s) with {{len(copied_cache)}} files copied to cm_content")
    
    # Adjust wrapper port if necessary
    adjust_wrapper_port()

if __name__ == '__main__':
    main()
PYTHON_CONTENT_PATCHER

if [ $? -eq 0 ]; then
    log_message "✓ Content.json patching completed"
else
    log_message "⚠ Warning: content.json patching encountered issues (may be expected if no content.json files)"
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

{wrapper_script}

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
    
    write_status false "$PUBLIC_IP"
    exit 1
else
    log_message "===== VALIDATION PASSED ====="
    log_message "AC Server deployment and validation completed successfully"
    log_message "Server is accessible at: $PUBLIC_IP:$AC_SERVER_TCP_PORT"
    log_message "acstuff join link: $ACSTUFF_URL"
    
    write_status true "$PUBLIC_IP"
    exit 0
fi
"""
        return script

    def upload_bootstrap_to_s3(
        self, s3_manager, bootstrap_script: str
    ) -> Optional[tuple[str, str]]:
        """Upload bootstrap script to S3 and return the key and presigned URL.

        Args:
            s3_manager: S3Manager instance for uploading
            bootstrap_script: Bootstrap script content as string

        Returns:
            Tuple of (s3_key, presigned_url) or None if upload failed
        """
        # Generate unique key with timestamp and UUID
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        s3_key = f"bootstrap/bootstrap-{timestamp}-{unique_id}.sh"

        # Upload to S3
        bootstrap_bytes = bootstrap_script.encode("utf-8")
        if not s3_manager.upload_bytes(s3_key, bootstrap_bytes):
            logger.error("Failed to upload bootstrap script to S3")
            return None

        # Generate presigned URL (1 hour expiration)
        presigned_url = s3_manager.generate_presigned_url(s3_key, expiration_secs=3600)
        if not presigned_url:
            logger.error("Failed to generate presigned URL for bootstrap script")
            return None

        logger.info(f"Uploaded bootstrap script to s3://{s3_manager.bucket_name}/{s3_key}")
        return s3_key, presigned_url

    def create_minimal_user_data_with_presigned_url(self, presigned_url: str) -> str:
        """Create minimal user data script that downloads and executes bootstrap from S3.

        Args:
            presigned_url: Presigned S3 URL to download bootstrap script

        Returns:
            Minimal user data script as string
        """
        script = f"""#!/bin/bash
set -e

# Download bootstrap script from S3
BOOTSTRAP_PATH="/tmp/bootstrap.sh"
echo "Downloading bootstrap script..."

# Try curl first, then wget
if command -v curl &>/dev/null; then
    curl -fsSL -o "$BOOTSTRAP_PATH" '{presigned_url}'
elif command -v wget &>/dev/null; then
    wget -q -O "$BOOTSTRAP_PATH" '{presigned_url}'
else
    echo "Error: Neither curl nor wget available"
    exit 1
fi

# Verify download
if [ ! -f "$BOOTSTRAP_PATH" ] || [ ! -s "$BOOTSTRAP_PATH" ]; then
    echo "Error: Failed to download bootstrap script"
    exit 1
fi

# Make executable and run
chmod +x "$BOOTSTRAP_PATH"
echo "Executing bootstrap script..."
exec "$BOOTSTRAP_PATH"
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

    def create_assettoserver_user_data_script(
        self, s3_bucket: str, s3_key: str, assettoserver_version: str = "v0.0.54"
    ) -> str:
        """Create user data script for AssettoServer Docker deployment.

        Args:
            s3_bucket: S3 bucket containing the pack file
            s3_key: S3 key of the pack file
            assettoserver_version: AssettoServer Docker image version

        Returns:
            User data script as string
        """
        import re

        pack_id = re.sub(
            r"[^a-zA-Z0-9-_]", "_", s3_key.split("/")[-1].replace(".tar.gz", "").replace(".zip", "")
        )

        script = f"""#!/bin/bash
set -euo pipefail

# Logging setup
DEPLOY_LOG="/var/log/assettoserver-deploy.log"
STATUS_FILE="/opt/assettoserver/deploy-status.json"
exec > >(tee -a "$DEPLOY_LOG") 2>&1

log_message() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}}

write_status() {{
    local status=$1
    local detail=${{2:-""}}
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local public_ip=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    
    cat > "$STATUS_FILE" << STATUSEOF
{{
  "status": "$status",
  "detail": "$detail",
  "timestamp": "$timestamp",
  "server_ip": "$public_ip",
  "server_port": {AC_SERVER_UDP_PORT},
  "tcp_port": {AC_SERVER_TCP_PORT},
  "http_port": {AC_SERVER_HTTP_PORT},
  "assettoserver_version": "{assettoserver_version}",
  "pack_id": "{pack_id}"
}}
STATUSEOF
}}

log_message "=== AssettoServer Deployment Started ==="
log_message "Pack: {s3_key}"
log_message "AssettoServer Version: {assettoserver_version}"

# Install Docker and dependencies
log_message "Installing Docker and dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg awscli python3 ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

log_message "✓ Docker and dependencies installed"

# Create AssettoServer data directory
ASSETTOSERVER_DIR="/opt/assettoserver"
DATA_DIR="$ASSETTOSERVER_DIR/data"
mkdir -p "$DATA_DIR"
cd "$ASSETTOSERVER_DIR"

# Download server pack from S3 with retries
log_message "Downloading server pack from S3..."
MAX_RETRIES=3
RETRY_DELAY=5
for attempt in $(seq 1 $MAX_RETRIES); do
    if aws s3 cp s3://{s3_bucket}/{s3_key} ./server-pack.tar.gz; then
        log_message "✓ Download successful"
        break
    else
        if [ $attempt -eq $MAX_RETRIES ]; then
            log_message "ERROR: Failed to download pack from S3 after $MAX_RETRIES attempts"
            write_status "failed" "Failed to download pack from S3"
            exit 1
        fi
        log_message "Download attempt $attempt failed, retrying in $RETRY_DELAY seconds..."
        sleep $RETRY_DELAY
        RETRY_DELAY=$((RETRY_DELAY * 2))
    fi
done

# Download the preparation tool
log_message "Downloading AssettoServer preparation tool..."
if ! aws s3 cp s3://{s3_bucket}/tools/assetto_server_prepare.py ./assetto_server_prepare.py; then
    log_message "ERROR: Failed to download preparation tool"
    write_status "failed" "Failed to download preparation tool"
    exit 1
fi
chmod +x ./assetto_server_prepare.py

# Prepare AssettoServer data
log_message "Preparing AssettoServer data structure..."
if ! python3 ./assetto_server_prepare.py ./server-pack.tar.gz "$DATA_DIR"; then
    log_message "ERROR: Failed to prepare AssettoServer data"
    write_status "failed" "Failed to prepare AssettoServer data structure"
    exit 1
fi

log_message "✓ Server data prepared"

# Create docker-compose.yml with explicit UDP port mapping
log_message "Creating Docker Compose configuration..."
cat > docker-compose.yml << 'EOF'
version: "3.9"

services:
  assettoserver:
    image: compujuckel/assettoserver:{assettoserver_version}
    container_name: assettoserver
    ports:
      - "{AC_SERVER_UDP_PORT}:{AC_SERVER_UDP_PORT}/udp"
      - "{AC_SERVER_TCP_PORT}:{AC_SERVER_TCP_PORT}/tcp"
      - "{AC_SERVER_HTTP_PORT}:{AC_SERVER_HTTP_PORT}/tcp"
      - "8080:8080/tcp"
    volumes:
      - ./data:/data
    environment:
      - TZ=UTC
    restart: unless-stopped
    network_mode: bridge
EOF

log_message "✓ Docker Compose configuration created"

# Configure host firewall (ufw) if available
log_message "Configuring host firewall..."
if command -v ufw &>/dev/null; then
    # Allow SSH first
    ufw allow 22/tcp || true
    # Allow game ports
    ufw allow {AC_SERVER_UDP_PORT}/udp || true
    ufw allow {AC_SERVER_TCP_PORT}/tcp || true
    # Allow HTTP ports
    ufw allow {AC_SERVER_HTTP_PORT}/tcp || true
    ufw allow 8080/tcp || true
    # Enable ufw with defaults (non-interactive)
    echo "y" | ufw enable || true
    ufw status | tee -a "$DEPLOY_LOG"
    log_message "✓ Firewall configured"
else
    log_message "⚠ ufw not available, skipping firewall configuration"
fi

# Pull AssettoServer image
log_message "Pulling AssettoServer Docker image..."
if ! docker compose pull; then
    log_message "ERROR: Failed to pull AssettoServer image"
    write_status "failed" "Failed to pull Docker image"
    exit 1
fi

# Start AssettoServer
log_message "Starting AssettoServer container..."
if docker compose up -d; then
    log_message "✓ AssettoServer started successfully"
    
    # Wait for container to be healthy
    log_message "Waiting for container to start..."
    sleep 10
    
    # Check if container is running
    if docker ps | grep -q assettoserver; then
        log_message "✓ Container is running"
        write_status "started" "AssettoServer deployment successful"
    else
        log_message "ERROR: Container failed to start"
        log_message "Container logs:"
        docker logs assettoserver 2>&1 | tail -50 | tee -a "$DEPLOY_LOG"
        write_status "failed" "Container failed to start"
        exit 1
    fi
    
    log_message "=== Deployment Complete ==="
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "unknown")
    log_message "Server available at $PUBLIC_IP:{AC_SERVER_UDP_PORT} (UDP)"
    log_message "HTTP interface at http://$PUBLIC_IP:{AC_SERVER_HTTP_PORT}"
    log_message "File server at http://$PUBLIC_IP:8080"
    log_message "Status file: $STATUS_FILE"
else
    log_message "ERROR: Failed to start AssettoServer"
    write_status "failed" "docker compose up failed"
    exit 1
fi
"""
        return script
