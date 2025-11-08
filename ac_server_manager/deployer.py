"""Main deployment manager for Assetto Corsa servers."""

import logging
from pathlib import Path
from typing import Optional

from .config import DeploymentConfig
from .ec2 import EC2Manager
from .s3 import S3Manager

logger = logging.getLogger(__name__)


class ACServerDeployer:
    """Main class for deploying and managing AC servers on AWS."""

    def __init__(self, config: Optional[DeploymentConfig] = None):
        """Initialize the deployer.

        Args:
            config: Deployment configuration (uses defaults if not provided)
        """
        self.config = config or DeploymentConfig()
        
        self.s3_manager = S3Manager(
            bucket_name=self.config.s3_bucket,
            region=self.config.aws.region,
            profile=self.config.aws.profile
        )
        
        self.ec2_manager = EC2Manager(
            region=self.config.aws.region,
            profile=self.config.aws.profile
        )

    def deploy(
        self,
        pack_path: Path,
        instance_name: Optional[str] = None
    ) -> dict:
        """Deploy a new AC server.

        Args:
            pack_path: Path to the server pack ZIP file
            instance_name: Custom name for the instance (auto-generated if not provided)

        Returns:
            Dictionary with deployment information including instance ID and server details
        """
        logger.info("Starting AC server deployment...")
        
        # Step 1: Create S3 bucket if needed
        logger.info("Ensuring S3 bucket exists...")
        if not self.s3_manager.create_bucket():
            raise RuntimeError("Failed to create or access S3 bucket")
        
        # Step 2: Upload pack to S3
        logger.info("Uploading server pack to S3...")
        pack_key = self.s3_manager.upload_pack(pack_path)
        
        # Step 3: Generate presigned URL (valid for 1 hour)
        download_url = self.s3_manager.get_pack_url(pack_key, expiration=3600)
        
        # Step 4: Create security group
        logger.info("Setting up security group...")
        security_group_id = self.ec2_manager.create_security_group(
            self.config.server.security_group_name,
            self.config.server
        )
        
        # Step 5: Launch instance
        if not instance_name:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            instance_name = f"{self.config.instance_name_prefix}-{timestamp}"
        
        logger.info(f"Launching EC2 instance: {instance_name}")
        instance_id = self.ec2_manager.launch_instance(
            instance_name,
            self.config.server,
            security_group_id,
            download_url
        )
        
        # Step 6: Get instance info
        logger.info("Retrieving instance information...")
        instance_info = self.ec2_manager.get_instance_info(instance_id)
        
        # Step 7: Wait for and retrieve server info (including acstuff.ru link)
        logger.info("Waiting for AC server to start (this may take several minutes)...")
        server_info = self.ec2_manager.get_server_info(instance_id, max_attempts=60)
        
        result = {
            "instance_id": instance_id,
            "instance_name": instance_name,
            "public_ip": instance_info.get("public_ip"),
            "pack_key": pack_key,
            "security_group_id": security_group_id,
        }
        
        if server_info:
            result["server_info"] = server_info
            if "AC_SERVER_LINK" in server_info:
                result["acstuff_link"] = server_info["AC_SERVER_LINK"]
                logger.info(f"🎮 Server is ready! Connect via: {server_info['AC_SERVER_LINK']}")
            else:
                logger.warning("Server started but acstuff.ru link not found in logs")
        else:
            logger.warning(
                "Could not retrieve server info automatically. "
                "Check the instance logs or connect via RDP to verify server status."
            )
        
        logger.info("✅ Deployment complete!")
        return result

    def stop_server(self, instance_id: str) -> bool:
        """Stop a running server instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Stopping server instance {instance_id}...")
        return self.ec2_manager.stop_instance(instance_id)

    def start_server(self, instance_id: str) -> bool:
        """Start a stopped server instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Starting server instance {instance_id}...")
        return self.ec2_manager.start_instance(instance_id)

    def terminate_server(self, instance_id: str, delete_pack: bool = False) -> bool:
        """Terminate a server instance and optionally delete its pack.

        Args:
            instance_id: EC2 instance ID
            delete_pack: Whether to delete the associated pack from S3

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Terminating server instance {instance_id}...")
        
        if delete_pack:
            # Try to find and delete the pack
            # This is best-effort as we may not have the pack key
            logger.info("Note: Pack deletion requires the pack key")
        
        return self.ec2_manager.terminate_instance(instance_id)

    def redeploy_server(
        self,
        instance_id: str,
        pack_path: Path,
        instance_name: Optional[str] = None
    ) -> dict:
        """Redeploy a server with a new pack file.

        Args:
            instance_id: EC2 instance ID to terminate
            pack_path: Path to the new server pack ZIP file
            instance_name: Custom name for the new instance

        Returns:
            Dictionary with new deployment information
        """
        logger.info(f"Redeploying server (terminating {instance_id})...")
        
        # Terminate old instance
        self.ec2_manager.terminate_instance(instance_id)
        
        # Deploy new instance
        return self.deploy(pack_path, instance_name)

    def get_server_status(self, instance_id: str) -> dict:
        """Get current status and information about a server.

        Args:
            instance_id: EC2 instance ID

        Returns:
            Dictionary with server status and information
        """
        return self.ec2_manager.get_instance_info(instance_id)

    def list_servers(self) -> list[dict]:
        """List all AC server instances.

        Returns:
            List of dictionaries with server information
        """
        instance_ids = self.ec2_manager.find_instances_by_tag(
            "Application",
            "AssettoCorsaServer"
        )
        
        servers = []
        for instance_id in instance_ids:
            try:
                info = self.ec2_manager.get_instance_info(instance_id)
                servers.append(info)
            except Exception as e:
                logger.error(f"Failed to get info for {instance_id}: {e}")
        
        return servers

    def delete_pack(self, pack_key: str) -> bool:
        """Delete a pack file from S3.

        Args:
            pack_key: S3 key of the pack to delete

        Returns:
            True if successful, False otherwise
        """
        return self.s3_manager.delete_pack(pack_key)

    def list_packs(self) -> list[str]:
        """List all available pack files in S3.

        Returns:
            List of pack file keys
        """
        return self.s3_manager.list_packs()
