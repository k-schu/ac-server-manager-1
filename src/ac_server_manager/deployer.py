"""Deployment orchestration for AC Server Manager."""

import logging
from pathlib import Path
from typing import Optional

from .config import ServerConfig
from .ec2_manager import EC2Manager
from .iam_manager import IAMManager
from .pack_utils import extract_wrapper_port_from_pack
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

        # Step 1: Extract wrapper port from pack if present
        wrapper_port = extract_wrapper_port_from_pack(pack_file_path)
        if wrapper_port:
            logger.info(f"Using wrapper port from pack: {wrapper_port}")
        else:
            logger.info("No wrapper port found in pack, using default")

        # Step 2: Create S3 bucket if needed
        if not self.s3_manager.create_bucket():
            logger.error("Failed to create S3 bucket")
            return None

        # Step 3: Upload pack to S3
        s3_key = self.s3_manager.upload_pack(pack_file_path)
        if not s3_key:
            logger.error("Failed to upload pack to S3")
            return None

        # Step 4: Upload full installer script to S3
        from pathlib import Path as PathLib

        installer_template_path = (
            PathLib(__file__).parent / "user_data_templates" / "full_installer.sh"
        )
        with open(installer_template_path, "r") as f:
            installer_content = f.read()

        installer_s3_key = f"installers/full_installer_{pack_file_path.stem}.sh"
        if not self.s3_manager.upload_file_content(installer_content, installer_s3_key):
            logger.error("Failed to upload installer script to S3")
            return None

        logger.info(
            f"Uploaded installer script to s3://{self.config.s3_bucket_name}/{installer_s3_key}"
        )

        # Step 5: Determine IAM instance profile to use
        iam_profile_to_use = None
        use_presigned_url = True

        if self.config.iam_instance_profile:
            # User provided an explicit instance profile - use it
            iam_profile_to_use = self.config.iam_instance_profile
            use_presigned_url = False
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
                use_presigned_url = False
                logger.info(f"IAM resources configured successfully: {iam_profile_to_use}")
            except Exception as e:
                logger.error(f"Failed to create IAM resources: {e}")
                logger.warning("Will use presigned URLs instead of IAM instance profile")
                use_presigned_url = True

        # Step 6: Generate presigned URLs if needed
        presigned_url_installer = None
        presigned_url_pack = None
        if use_presigned_url:
            logger.info("Generating presigned URLs for installer and pack download")
            presigned_url_installer = self.s3_manager.generate_presigned_url(
                installer_s3_key, expiration=7200  # 2 hours
            )
            presigned_url_pack = self.s3_manager.generate_presigned_url(
                s3_key, expiration=7200  # 2 hours
            )
            if not presigned_url_installer or not presigned_url_pack:
                logger.error("Failed to generate presigned URLs")
                return None

        # Step 7: Create security group with wrapper port
        security_group_id = self.ec2_manager.create_security_group(
            self.config.security_group_name,
            "Security group for Assetto Corsa server",
            wrapper_port,
        )
        if not security_group_id:
            logger.error("Failed to create security group")
            return None

        # Step 8: Get Ubuntu AMI
        ami_id = self.ec2_manager.get_ubuntu_ami()
        if not ami_id:
            logger.error("Failed to get Ubuntu AMI")
            return None

        # Step 9: Create minimal user data script
        user_data = self.ec2_manager.create_minimal_user_data_script(
            self.config.s3_bucket_name,
            s3_key,
            installer_s3_key,
            presigned_url_installer,
            presigned_url_pack,
            wrapper_port,
        )

        # Step 10: Validate user-data size
        try:
            self.ec2_manager.validate_user_data_size(user_data)
        except RuntimeError as e:
            logger.error(str(e))
            return None

        # Step 11: Launch instance
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

        # Step 12: Get public IP
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
