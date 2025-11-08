"""EC2 operations for AC Server Manager."""

import logging
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

    def create_security_group(self, group_name: str, description: str) -> Optional[str]:
        """Create security group with rules for AC server.

        Args:
            group_name: Name of the security group
            description: Description of the security group

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

    def create_user_data_script(self, s3_bucket: str, s3_key: str) -> str:
        """Create user data script for instance initialization.

        Args:
            s3_bucket: S3 bucket containing the pack file
            s3_key: S3 key of the pack file

        Returns:
            User data script as string
        """
        script = f"""#!/bin/bash
set -e

VALIDATION_LOG="/var/log/acserver-validation.log"
DEPLOYMENT_LOG="/var/log/acserver-deployment.log"

# Logging function
log_message() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DEPLOYMENT_LOG"
}}

# Validation function: Check if process is running
check_process_running() {{
    log_message "Checking if acServer process is running..."
    
    # Wait up to 30 seconds for process to start
    for i in {{1..30}}; do
        if pgrep -x "acServer" > /dev/null; then
            log_message "✓ acServer process is running (PID: $(pgrep -x acServer))"
            return 0
        fi
        sleep 1
    done
    
    log_message "✗ FAILED: acServer process is not running after 30 seconds"
    return 1
}}

# Validation function: Check if ports are listening
check_ports_listening() {{
    log_message "Checking if required ports are listening..."
    local all_ports_ok=true
    
    # Check TCP port {AC_SERVER_TCP_PORT}
    if ss -tlnp | grep -q ":{AC_SERVER_TCP_PORT}"; then
        log_message "✓ TCP port {AC_SERVER_TCP_PORT} is listening"
    else
        log_message "✗ FAILED: TCP port {AC_SERVER_TCP_PORT} is not listening"
        all_ports_ok=false
    fi
    
    # Check UDP port {AC_SERVER_UDP_PORT}
    if ss -ulnp | grep -q ":{AC_SERVER_UDP_PORT}"; then
        log_message "✓ UDP port {AC_SERVER_UDP_PORT} is listening"
    else
        log_message "✗ FAILED: UDP port {AC_SERVER_UDP_PORT} is not listening"
        all_ports_ok=false
    fi
    
    # Check HTTP port {AC_SERVER_HTTP_PORT}
    if ss -tlnp | grep -q ":{AC_SERVER_HTTP_PORT}"; then
        log_message "✓ TCP port {AC_SERVER_HTTP_PORT} (HTTP) is listening"
    else
        log_message "✗ FAILED: TCP port {AC_SERVER_HTTP_PORT} (HTTP) is not listening"
        all_ports_ok=false
    fi
    
    if [ "$all_ports_ok" = true ]; then
        return 0
    else
        return 1
    fi
}}

# Validation function: Check server logs for errors
check_server_logs() {{
    log_message "Checking server logs for configuration errors..."
    
    local log_file="/opt/acserver/log/log.txt"
    
    # Wait for log file to be created
    for i in {{1..10}}; do
        if [ -f "$log_file" ]; then
            break
        fi
        sleep 1
    done
    
    if [ ! -f "$log_file" ]; then
        log_message "⚠ WARNING: Server log file not found at $log_file"
        return 0  # Not a critical failure
    fi
    
    # Check for common error patterns
    local errors_found=false
    
    if grep -qi "track not found\\|content not found\\|missing track\\|missing car" "$log_file"; then
        log_message "✗ FAILED: Missing content detected in server logs"
        grep -i "track not found\\|content not found\\|missing track\\|missing car" "$log_file" | tail -5 | while read line; do
            log_message "  Error: $line"
        done
        errors_found=true
    fi
    
    if grep -qi "invalid configuration\\|failed to load\\|error loading" "$log_file"; then
        log_message "✗ FAILED: Configuration errors detected in server logs"
        grep -i "invalid configuration\\|failed to load\\|error loading" "$log_file" | tail -5 | while read line; do
            log_message "  Error: $line"
        done
        errors_found=true
    fi
    
    if grep -qi "bind.*failed\\|port.*in use\\|address already in use" "$log_file"; then
        log_message "✗ FAILED: Port binding errors detected in server logs"
        grep -i "bind.*failed\\|port.*in use\\|address already in use" "$log_file" | tail -5 | while read line; do
            log_message "  Error: $line"
        done
        errors_found=true
    fi
    
    if [ "$errors_found" = false ]; then
        log_message "✓ No critical errors found in server logs"
        return 0
    else
        return 1
    fi
}}

# Main deployment script
log_message "Starting AC Server deployment..."

# Update system
log_message "Updating system packages..."
apt-get update
apt-get install -y awscli unzip wget

# Install required libraries for AC server
log_message "Installing AC server dependencies..."
apt-get install -y lib32gcc-s1 lib32stdc++6

# Create directory for AC server
log_message "Creating server directory..."
mkdir -p /opt/acserver
cd /opt/acserver

# Download pack from S3
log_message "Downloading server pack from S3..."
aws s3 cp s3://{s3_bucket}/{s3_key} ./server-pack.tar.gz

# Extract pack
log_message "Extracting server pack..."
tar -xzf server-pack.tar.gz

# Make acServer executable
log_message "Setting executable permissions..."
chmod +x acServer

# Create systemd service
log_message "Creating systemd service..."
cat > /etc/systemd/system/acserver.service << 'EOF'
[Unit]
Description=Assetto Corsa Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/acserver
ExecStart=/opt/acserver/acServer
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
log_message "Starting AC server service..."
systemctl daemon-reload
systemctl enable acserver
systemctl start acserver

# Give the server time to start
log_message "Waiting for server to initialize..."
sleep 5

# Run validation checks
log_message "===== Starting Post-Boot Validation ====="
validation_failed=false

if ! check_process_running; then
    validation_failed=true
fi

if ! check_ports_listening; then
    validation_failed=true
fi

if ! check_server_logs; then
    validation_failed=true
fi

# Final validation result
if [ "$validation_failed" = true ]; then
    log_message "===== VALIDATION FAILED ====="
    log_message "Deployment completed with errors. Server may not be fully functional."
    log_message "Check systemd status: systemctl status acserver"
    log_message "Check server logs: journalctl -u acserver -n 50"
    
    # Copy validation results
    cp "$DEPLOYMENT_LOG" "$VALIDATION_LOG"
    
    # Exit with error to signal deployment failure
    exit 1
else
    log_message "===== VALIDATION PASSED ====="
    log_message "AC Server deployment and validation completed successfully at $(date)"
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
    ) -> Optional[str]:
        """Launch EC2 instance for AC server.

        Args:
            ami_id: AMI ID to use
            instance_type: EC2 instance type
            security_group_id: Security group ID
            user_data: User data script
            instance_name: Name tag for the instance
            key_name: SSH key pair name (optional)

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
