"""Deployment orchestration for AC Server Manager."""

import logging
from pathlib import Path
from typing import Optional

from .config import ServerConfig
from .ec2_manager import EC2Manager
from .iam_manager import IAMManager
from .s3_manager import S3Manager

logger = logging.getLogger(__name__)


class Deployer:
    """Orchestrates deployment of AC server on AWS."""

    def __init__(self, config: ServerConfig):
        """Initialize deployer.

        Args:
            config: Server configuration
        """
        self.config = config
        self.s3_manager = S3Manager(config.s3_bucket_name, config.aws_region)
        self.ec2_manager = EC2Manager(config.aws_region)

    def deploy(self, pack_file_path: Path) -> Optional[str]:
        """Deploy AC server to AWS.

        Args:
            pack_file_path: Path to the server pack file

        Returns:
            Instance ID if deployment succeeded, None otherwise
        """
        logger.info("Starting AC server deployment")

        # Step 1: Create S3 bucket if needed
        if not self.s3_manager.create_bucket():
            logger.error("Failed to create S3 bucket")
            return None

        # Step 2: Upload pack to S3
        s3_key = self.s3_manager.upload_pack(pack_file_path)
        if not s3_key:
            logger.error("Failed to upload pack to S3")
            return None

        # Step 3: Determine IAM instance profile to use
        iam_profile_to_use = None
        if self.config.iam_instance_profile:
            # User provided an explicit instance profile - use it
            iam_profile_to_use = self.config.iam_instance_profile
            logger.info(f"Using existing IAM instance profile: {iam_profile_to_use}")
        elif self.config.auto_create_iam:
            # Auto-create IAM role and instance profile
            logger.info("Auto-creating IAM role and instance profile for S3 access")
            try:
                iam_manager = IAMManager(self.config.aws_region)
                role_name = self.config.iam_role_name or "ac-server-role"
                profile_name = self.config.iam_instance_profile_name or "ac-server-instance-profile"

                iam_profile_to_use = iam_manager.ensure_role_and_instance_profile(
                    role_name, profile_name, self.config.s3_bucket_name
                )
                logger.info(f"IAM resources configured successfully: {iam_profile_to_use}")
            except Exception as e:
                logger.error(f"Failed to create IAM resources: {e}")
                logger.error(
                    "Deployment cannot continue without IAM instance profile for S3 access"
                )
                return None

        # Step 4: Create security group
        extra_ports = [self.config.wrapper_port] if self.config.enable_wrapper else None
        security_group_id = self.ec2_manager.create_security_group(
            self.config.security_group_name,
            "Security group for Assetto Corsa server",
            extra_ports=extra_ports,
        )
        if not security_group_id:
            logger.error("Failed to create security group")
            return None

        # Step 5: Get Ubuntu AMI
        ami_id = self.ec2_manager.get_ubuntu_ami()
        if not ami_id:
            logger.error("Failed to get Ubuntu AMI")
            return None

        # Step 6: Create full bootstrap script
        bootstrap_script = self.ec2_manager.create_user_data_script(
            self.config.s3_bucket_name,
            s3_key,
            enable_wrapper=self.config.enable_wrapper,
            wrapper_port=self.config.wrapper_port,
        )

        # Step 7: Upload bootstrap script to S3 and get presigned URL
        upload_result = self.ec2_manager.upload_bootstrap_to_s3(self.s3_manager, bootstrap_script)
        if not upload_result:
            logger.error("Failed to upload bootstrap script to S3")
            return None

        bootstrap_key, presigned_url = upload_result
        logger.info(f"Bootstrap script uploaded to S3: {bootstrap_key}")

        # Step 8: Create minimal user data that downloads and executes bootstrap
        user_data = self.ec2_manager.create_minimal_user_data_with_presigned_url(presigned_url)
        user_data_size = len(user_data.encode("utf-8"))
        logger.info(f"User data size: {user_data_size} bytes ({user_data_size/1024:.2f} KB)")

        if user_data_size >= 16384:
            logger.error(
                f"User data size ({user_data_size} bytes) exceeds 16KB limit. "
                "This should not happen with presigned URL approach."
            )
            return None

        # Step 9: Launch instance
        instance_id = self.ec2_manager.launch_instance(
            ami_id=ami_id,
            instance_type=self.config.instance_type,
            security_group_id=security_group_id,
            user_data=user_data,
            instance_name=self.config.instance_name,
            key_name=self.config.key_name,
            iam_instance_profile=iam_profile_to_use,
        )

        if not instance_id:
            logger.error("Failed to launch instance")
            return None

        # Step 8: Get public IP
        public_ip = self.ec2_manager.get_instance_public_ip(instance_id)
        if public_ip:
            logger.info("AC server deployed successfully!")
            logger.info(f"Instance ID: {instance_id}")
            logger.info(f"Public IP: {public_ip}")
            logger.info(f"Server will be available at {public_ip}:9600 (UDP/TCP)")
            logger.info("")
            logger.info("Post-deployment validation is running on the instance...")
            logger.info("This may take 2-3 minutes. To check deployment status:")
            logger.info(f"  1. SSH to instance: ssh -i <key>.pem ubuntu@{public_ip}")
            logger.info("  2. Check status: cat /opt/acserver/deploy-status.json")
            logger.info("  3. Check logs: cat /var/log/acserver-deploy.log")
            logger.info("  4. Check service: systemctl status acserver")
            logger.info("")
            logger.info("If validation fails, check the logs above for troubleshooting.")

        return instance_id

    def stop(self, instance_id: Optional[str] = None) -> bool:
        """Stop AC server instance.

        Args:
            instance_id: Instance ID to stop (if None, stops instance by name)

        Returns:
            True if stop succeeded, False otherwise
        """
        if instance_id is None:
            instances = self.ec2_manager.find_instances_by_name(self.config.instance_name)
            if not instances:
                logger.error(f"No instances found with name {self.config.instance_name}")
                return False
            instance_id = instances[0]

        return self.ec2_manager.stop_instance(instance_id)

    def start(self, instance_id: Optional[str] = None) -> bool:
        """Start AC server instance.

        Args:
            instance_id: Instance ID to start (if None, starts instance by name)

        Returns:
            True if start succeeded, False otherwise
        """
        if instance_id is None:
            instances = self.ec2_manager.find_instances_by_name(self.config.instance_name)
            if not instances:
                logger.error(f"No instances found with name {self.config.instance_name}")
                return False
            instance_id = instances[0]

        return self.ec2_manager.start_instance(instance_id)

    def terminate(self, instance_id: Optional[str] = None) -> bool:
        """Terminate AC server instance.

        Args:
            instance_id: Instance ID to terminate (if None, terminates instance by name)

        Returns:
            True if termination succeeded, False otherwise
        """
        if instance_id is None:
            instances = self.ec2_manager.find_instances_by_name(self.config.instance_name)
            if not instances:
                logger.error(f"No instances found with name {self.config.instance_name}")
                return False
            instance_id = instances[0]

        return self.ec2_manager.terminate_instance(instance_id)

    def redeploy(self, pack_file_path: Path, instance_id: Optional[str] = None) -> Optional[str]:
        """Terminate existing instance and deploy with new pack.

        Args:
            pack_file_path: Path to the new server pack file
            instance_id: Instance ID to replace (if None, uses instance by name)

        Returns:
            New instance ID if redeployment succeeded, None otherwise
        """
        logger.info("Starting redeployment")

        # Terminate existing instance
        if not self.terminate(instance_id):
            logger.warning("Failed to terminate existing instance, continuing anyway")

        # Deploy new instance
        return self.deploy(pack_file_path)

    def get_status(self, instance_id: Optional[str] = None) -> Optional[dict]:
        """Get status of AC server instance.

        Args:
            instance_id: Instance ID to check (if None, finds instance by name)

        Returns:
            Dictionary with instance details, or None if not found
        """
        if instance_id is None:
            instances = self.ec2_manager.find_instances_by_name(self.config.instance_name)
            if not instances:
                logger.error(f"No instances found with name {self.config.instance_name}")
                return None
            instance_id = instances[0]

        return self.ec2_manager.get_instance_details(instance_id)
