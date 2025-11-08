"""EC2 operations for managing Assetto Corsa server instances."""

import base64
import logging
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .config import ServerConfig

logger = logging.getLogger(__name__)


class EC2Manager:
    """Manages EC2 instances for AC servers."""

    def __init__(
        self,
        region: str = "us-east-1",
        profile: Optional[str] = None
    ):
        """Initialize EC2 manager.

        Args:
            region: AWS region
            profile: AWS profile name (optional)
        """
        session = boto3.Session(profile_name=profile, region_name=region)
        self.ec2_client = session.client("ec2")
        self.ec2_resource = session.resource("ec2")
        self.ssm_client = session.client("ssm")
        self.region = region

    def get_windows_ami(self) -> str:
        """Get the latest Windows Server AMI ID.

        Returns:
            AMI ID for Windows Server
        """
        try:
            # Get latest Windows Server 2022 AMI
            response = self.ec2_client.describe_images(
                Filters=[
                    {"Name": "name", "Values": ["Windows_Server-2022-English-Full-Base-*"]},
                    {"Name": "state", "Values": ["available"]},
                ],
                Owners=["amazon"]
            )
            
            if not response["Images"]:
                raise RuntimeError("No Windows Server AMI found")
            
            # Sort by creation date and get the latest
            images = sorted(
                response["Images"],
                key=lambda x: x["CreationDate"],
                reverse=True
            )
            ami_id = images[0]["ImageId"]
            logger.info(f"Using Windows AMI: {ami_id}")
            return ami_id
        except ClientError as e:
            logger.error(f"Failed to get Windows AMI: {e}")
            raise

    def create_security_group(
        self,
        group_name: str,
        config: ServerConfig
    ) -> str:
        """Create or get security group for AC server.

        Args:
            group_name: Name of the security group
            config: Server configuration with port settings

        Returns:
            Security group ID
        """
        try:
            # Check if security group already exists
            response = self.ec2_client.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [group_name]}]
            )
            
            if response["SecurityGroups"]:
                group_id = response["SecurityGroups"][0]["GroupId"]
                logger.info(f"Using existing security group: {group_id}")
                return group_id
            
            # Create new security group
            vpc_response = self.ec2_client.describe_vpcs(
                Filters=[{"Name": "is-default", "Values": ["true"]}]
            )
            vpc_id = vpc_response["Vpcs"][0]["VpcId"]
            
            response = self.ec2_client.create_security_group(
                GroupName=group_name,
                Description="Security group for Assetto Corsa server",
                VpcId=vpc_id
            )
            group_id = response["GroupId"]
            logger.info(f"Created security group: {group_id}")
            
            # Add ingress rules
            self.ec2_client.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": config.tcp_port,
                        "ToPort": config.tcp_port,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    },
                    {
                        "IpProtocol": "udp",
                        "FromPort": config.udp_port,
                        "ToPort": config.udp_port,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": config.http_port,
                        "ToPort": config.http_port,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    },
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 3389,  # RDP for management
                        "ToPort": 3389,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    },
                ]
            )
            logger.info("Added ingress rules to security group")
            
            return group_id
        except ClientError as e:
            logger.error(f"Failed to create security group: {e}")
            raise

    def create_user_data_script(self, download_url: str, http_port: int, tcp_port: int) -> str:
        """Create PowerShell user data script for instance initialization.

        Args:
            download_url: Presigned S3 URL for the pack file
            http_port: HTTP port for the server
            tcp_port: TCP port for the server

        Returns:
            User data script
        """
        # Note: We create a comprehensive script that:
        # 1. Downloads and extracts the pack
        # 2. Starts the AC server
        # 3. Monitors logs for the acstuff.ru link
        # 4. Outputs the link to a file accessible via SSM
        script = f"""<powershell>
# Set error handling
$ErrorActionPreference = "Continue"

# Create log file
$logFile = "C:\\ac-deployment.log"
function Log {{
    param([string]$message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $message" | Out-File -FilePath $logFile -Append
    Write-Host $message
}}

Log "Starting AC server deployment..."

# Download AC server pack
$downloadUrl = "{download_url}"
$packPath = "C:\\ac-server-pack.zip"
$extractPath = "C:\\acserver"

try {{
    Log "Downloading AC server pack from S3..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($downloadUrl, $packPath)
    Log "Download complete"
}} catch {{
    Log "ERROR downloading pack: $_"
    exit 1
}}

# Extract the pack
try {{
    Log "Extracting server pack to $extractPath..."
    Expand-Archive -Path $packPath -DestinationPath $extractPath -Force
    Log "Extraction complete"
}} catch {{
    Log "ERROR extracting pack: $_"
    exit 1
}}

# Find acServer.exe
$acServerPath = Get-ChildItem -Path $extractPath -Filter "acServer.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $acServerPath) {{
    Log "ERROR: acServer.exe not found in the pack!"
    
    # List directory structure for debugging
    Log "Directory structure of $extractPath:"
    Get-ChildItem -Path $extractPath -Recurse | ForEach-Object {{
        Log "  $($_.FullName)"
    }}
    
    exit 1
}}

$serverDir = $acServerPath.DirectoryName
Log "Found acServer.exe in: $serverDir"

# Create output directory for server info
$outputDir = "C:\\ac-server-info"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

# Create a script to start the server and capture output
$monitorScript = @"
`$serverDir = "$serverDir"
`$logFile = "C:\\ac-server-log.txt"
`$infoFile = "C:\\ac-server-info\\server-info.txt"

Set-Location `$serverDir

# Start the server process and capture output
Write-Host "Starting acServer.exe..."
`$process = Start-Process -FilePath "`$serverDir\\acServer.exe" -WorkingDirectory `$serverDir -PassThru -RedirectStandardOutput `$logFile -RedirectStandardError "C:\\ac-server-error.txt" -NoNewWindow

# Monitor the log file for the acstuff.ru link
`$maxAttempts = 60
`$attempt = 0
`$linkFound = `$false

while (`$attempt -lt `$maxAttempts -and -not `$linkFound) {{
    Start-Sleep -Seconds 2
    `$attempt++
    
    if (Test-Path `$logFile) {{
        `$content = Get-Content `$logFile -ErrorAction SilentlyContinue
        
        # Look for acstuff.ru or acstuff.com links in the output
        `$links = `$content | Select-String -Pattern "(http://acstuff\\.(ru|com)/[^\\s]+)" -AllMatches
        
        if (`$links) {{
            foreach (`$match in `$links.Matches) {{
                `$link = `$match.Value
                Write-Host "Found AC server link: `$link"
                "AC_SERVER_LINK=`$link" | Out-File -FilePath `$infoFile -Append
                `$linkFound = `$true
            }}
        }}
        
        # Also check for "PAGE URL:" which is another format
        `$pageUrls = `$content | Select-String -Pattern "PAGE URL:\\s*(.+)" -AllMatches
        if (`$pageUrls) {{
            foreach (`$match in `$pageUrls.Matches) {{
                `$link = `$match.Groups[1].Value.Trim()
                Write-Host "Found AC server page URL: `$link"
                "AC_SERVER_LINK=`$link" | Out-File -FilePath `$infoFile -Append
                `$linkFound = `$true
            }}
        }}
    }}
}}

# Output process status
if (`$process.HasExited) {{
    "SERVER_STATUS=EXITED" | Out-File -FilePath `$infoFile -Append
    "EXIT_CODE=`$(`$process.ExitCode)" | Out-File -FilePath `$infoFile -Append
    Write-Host "ERROR: Server process exited with code `$(`$process.ExitCode)"
}} else {{
    "SERVER_STATUS=RUNNING" | Out-File -FilePath `$infoFile -Append
    "PROCESS_ID=`$(`$process.Id)" | Out-File -FilePath `$infoFile -Append
    Write-Host "Server is running with PID `$(`$process.Id)"
}}

# Include public IP
try {{
    `$publicIp = (Invoke-WebRequest -Uri "http://169.254.169.254/latest/meta-data/public-ipv4" -UseBasicParsing).Content
    "PUBLIC_IP=`$publicIp" | Out-File -FilePath `$infoFile -Append
    Write-Host "Public IP: `$publicIp"
}} catch {{
    Write-Host "Could not retrieve public IP"
}}

# Add port information
"HTTP_PORT={http_port}" | Out-File -FilePath `$infoFile -Append
"TCP_PORT={tcp_port}" | Out-File -FilePath `$infoFile -Append

Write-Host "Server info written to `$infoFile"
"@

$monitorScript | Out-File -FilePath "C:\\monitor-server.ps1" -Encoding ASCII

# Create startup task to run the monitor script
Log "Creating scheduled task to start server..."
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File C:\\monitor-server.ps1"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "StartACServer" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

# Start the task immediately
Log "Starting AC server task..."
Start-ScheduledTask -TaskName "StartACServer"

# Wait a bit for the task to start
Start-Sleep -Seconds 10

# Check if task is running
$task = Get-ScheduledTask -TaskName "StartACServer"
Log "Task state: $($task.State)"

Log "AC server deployment script complete. Server should be starting..."
Log "Check C:\\ac-server-info\\server-info.txt for server details including the acstuff.ru link"

</powershell>
"""
        return script

    def launch_instance(
        self,
        instance_name: str,
        config: ServerConfig,
        security_group_id: str,
        pack_download_url: str
    ) -> str:
        """Launch an EC2 instance for AC server.

        Args:
            instance_name: Name tag for the instance
            config: Server configuration
            security_group_id: Security group ID
            pack_download_url: Presigned S3 URL for the server pack

        Returns:
            Instance ID
        """
        try:
            ami_id = config.ami_id or self.get_windows_ami()
            user_data = self.create_user_data_script(
                pack_download_url,
                config.http_port,
                config.tcp_port
            )
            
            logger.info(f"Launching instance {instance_name}...")
            
            # Create IAM instance profile for SSM (if not exists)
            iam_instance_profile = self._get_or_create_ssm_instance_profile()
            
            launch_params = {
                "ImageId": ami_id,
                "InstanceType": config.instance_type,
                "MinCount": 1,
                "MaxCount": 1,
                "SecurityGroupIds": [security_group_id],
                "UserData": user_data,
                "IamInstanceProfile": {"Name": iam_instance_profile},
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": instance_name},
                            {"Key": "Application", "Value": "AssettoCorsaServer"},
                        ],
                    }
                ],
            }
            
            if config.key_name:
                launch_params["KeyName"] = config.key_name
            
            response = self.ec2_client.run_instances(**launch_params)
            instance_id = response["Instances"][0]["InstanceId"]
            
            logger.info(f"Launched instance: {instance_id}")
            logger.info("Waiting for instance to be running...")
            
            # Wait for instance to be running
            waiter = self.ec2_client.get_waiter("instance_running")
            waiter.wait(InstanceIds=[instance_id])
            
            logger.info(f"Instance {instance_id} is now running")
            return instance_id
        except ClientError as e:
            logger.error(f"Failed to launch instance: {e}")
            raise

    def _get_or_create_ssm_instance_profile(self) -> str:
        """Get or create IAM instance profile for SSM access.

        Returns:
            Instance profile name
        """
        profile_name = "AC-Server-SSM-Profile"
        role_name = "AC-Server-SSM-Role"
        
        try:
            import boto3
            iam_client = boto3.client("iam")
            
            # Check if role exists
            try:
                iam_client.get_role(RoleName=role_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    # Create role
                    trust_policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "ec2.amazonaws.com"},
                                "Action": "sts:AssumeRole"
                            }
                        ]
                    }
                    
                    iam_client.create_role(
                        RoleName=role_name,
                        AssumeRolePolicyDocument=str(trust_policy),
                        Description="Role for AC server with SSM access"
                    )
                    
                    # Attach SSM policy
                    iam_client.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
                    )
            
            # Check if instance profile exists
            try:
                iam_client.get_instance_profile(InstanceProfileName=profile_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    # Create instance profile
                    iam_client.create_instance_profile(InstanceProfileName=profile_name)
                    
                    # Add role to profile
                    iam_client.add_role_to_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=role_name
                    )
                    
                    # Wait a bit for the profile to be ready
                    time.sleep(10)
            
            return profile_name
        except Exception as e:
            logger.warning(f"Could not create SSM instance profile: {e}")
            # Return empty dict to skip IAM profile
            return ""

    def get_instance_info(self, instance_id: str) -> dict:
        """Get information about an instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            Dictionary with instance information
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = response["Reservations"][0]["Instances"][0]
            
            info = {
                "instance_id": instance_id,
                "state": instance["State"]["Name"],
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "instance_type": instance["InstanceType"],
                "launch_time": instance["LaunchTime"],
            }
            
            # Try to get server info from the instance
            if instance["State"]["Name"] == "running":
                server_info = self.get_server_info(instance_id)
                if server_info:
                    info["server_info"] = server_info
            
            return info
        except ClientError as e:
            logger.error(f"Failed to get instance info: {e}")
            raise

    def get_server_info(self, instance_id: str, max_attempts: int = 30) -> Optional[dict]:
        """Get server information including the acstuff.ru link.

        Args:
            instance_id: EC2 instance ID
            max_attempts: Maximum number of attempts to retrieve info

        Returns:
            Dictionary with server information or None if not available
        """
        logger.info("Waiting for server to start and generate info...")
        
        for attempt in range(max_attempts):
            try:
                # Try to run a command via SSM to read the server info file
                response = self.ssm_client.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunPowerShellScript",
                    Parameters={
                        "commands": [
                            "if (Test-Path C:\\ac-server-info\\server-info.txt) { Get-Content C:\\ac-server-info\\server-info.txt } else { Write-Output 'INFO_NOT_READY' }"
                        ]
                    }
                )
                
                command_id = response["Command"]["CommandId"]
                
                # Wait for command to complete
                time.sleep(5)
                
                output_response = self.ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )
                
                if output_response["Status"] == "Success":
                    output = output_response["StandardOutputContent"]
                    
                    if "INFO_NOT_READY" not in output:
                        # Parse the output
                        server_info = {}
                        for line in output.strip().split("\n"):
                            if "=" in line:
                                key, value = line.split("=", 1)
                                server_info[key.strip()] = value.strip()
                        
                        if server_info:
                            logger.info(f"Retrieved server info: {server_info}")
                            return server_info
                
                logger.info(f"Attempt {attempt + 1}/{max_attempts}: Server info not ready yet...")
                time.sleep(10)
                
            except ClientError as e:
                logger.debug(f"Attempt {attempt + 1}/{max_attempts}: {e}")
                time.sleep(10)
        
        logger.warning("Could not retrieve server info after maximum attempts")
        return None

    def stop_instance(self, instance_id: str) -> bool:
        """Stop an instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Stopping instance {instance_id}...")
            self.ec2_client.stop_instances(InstanceIds=[instance_id])
            logger.info(f"Instance {instance_id} is stopping")
            return True
        except ClientError as e:
            logger.error(f"Failed to stop instance: {e}")
            return False

    def start_instance(self, instance_id: str) -> bool:
        """Start a stopped instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Starting instance {instance_id}...")
            self.ec2_client.start_instances(InstanceIds=[instance_id])
            logger.info(f"Instance {instance_id} is starting")
            return True
        except ClientError as e:
            logger.error(f"Failed to start instance: {e}")
            return False

    def terminate_instance(self, instance_id: str) -> bool:
        """Terminate an instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Terminating instance {instance_id}...")
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Instance {instance_id} is terminating")
            return True
        except ClientError as e:
            logger.error(f"Failed to terminate instance: {e}")
            return False

    def find_instances_by_tag(self, tag_key: str, tag_value: str) -> list[str]:
        """Find instances by tag.

        Args:
            tag_key: Tag key to search for
            tag_value: Tag value to search for

        Returns:
            List of instance IDs
        """
        try:
            response = self.ec2_client.describe_instances(
                Filters=[
                    {"Name": f"tag:{tag_key}", "Values": [tag_value]},
                    {"Name": "instance-state-name", "Values": ["running", "stopped"]},
                ]
            )
            
            instance_ids = []
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_ids.append(instance["InstanceId"])
            
            return instance_ids
        except ClientError as e:
            logger.error(f"Failed to find instances: {e}")
            return []
