#!/bin/bash
set -euo pipefail

# S3 Bootstrap Script for AC Server Manager
# Minimal script that downloads and executes the full installer from S3
# Template variables will be substituted by the deployer

DEPLOY_LOG="/var/log/acserver-deploy.log"
INSTALLER_SCRIPT="/opt/acserver/installer.sh"

log_message() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DEPLOY_LOG"
}}

log_message "===== AC Server Bootstrap ====="

# Install minimal packages needed for download
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq {install_cmd} 2>&1 | tee -a "$DEPLOY_LOG"

mkdir -p /opt/acserver

# Download installer script
log_message "Downloading installer..."
{download_cmd}

chmod +x "$INSTALLER_SCRIPT"

# Set environment variables for installer
export AC_SERVER_TCP_PORT={tcp_port}
export AC_SERVER_UDP_PORT={udp_port}
export AC_SERVER_HTTP_PORT={http_port}
export AC_SERVER_WRAPPER_PORT={wrapper_port}
{env_exports}

# Execute installer
log_message "Running installer..."
exec "$INSTALLER_SCRIPT"
