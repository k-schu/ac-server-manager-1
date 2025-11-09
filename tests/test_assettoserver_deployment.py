"""Tests for AssettoServer EC2 deployment functionality."""



from src.ac_server_manager.config import ServerConfig
from src.ac_server_manager.ec2_manager import EC2Manager


class TestAssettoServerDeployment:
    """Test cases for AssettoServer deployment functionality."""

    def test_create_assettoserver_user_data_script(self):
        """Test AssettoServer user data script creation."""
        ec2_manager = EC2Manager("us-east-1")
        script = ec2_manager.create_assettoserver_user_data_script(
            s3_bucket="test-bucket",
            s3_key="test-pack.tar.gz",
            assettoserver_version="v0.0.54",
        )

        # Verify script contains essential components
        assert "#!/bin/bash" in script
        assert "docker.com" in script
        assert "compujuckel/assettoserver:v0.0.54" in script
        assert "assetto_server_prepare.py" in script
        assert "docker-compose.yml" in script
        assert "docker compose up -d" in script

        # Verify S3 references
        assert "s3://test-bucket/test-pack.tar.gz" in script
        assert "s3://test-bucket/tools/assetto_server_prepare.py" in script

        # Verify logging
        assert "DEPLOY_LOG" in script
        assert "log_message" in script

    def test_assettoserver_script_contains_docker_install(self):
        """Test that AssettoServer script installs Docker."""
        ec2_manager = EC2Manager("us-east-1")
        script = ec2_manager.create_assettoserver_user_data_script("bucket", "key.tar.gz")

        assert "apt-get install" in script
        assert "docker-ce" in script
        assert "docker-compose-plugin" in script

    def test_assettoserver_script_creates_directory_structure(self):
        """Test that script creates proper directory structure."""
        ec2_manager = EC2Manager("us-east-1")
        script = ec2_manager.create_assettoserver_user_data_script("bucket", "key.tar.gz")

        assert "/opt/assettoserver" in script
        assert "DATA_DIR" in script

    def test_assettoserver_script_handles_custom_version(self):
        """Test that custom AssettoServer version is used."""
        ec2_manager = EC2Manager("us-east-1")
        script = ec2_manager.create_assettoserver_user_data_script(
            "bucket", "key.tar.gz", assettoserver_version="v1.0.0"
        )

        assert "compujuckel/assettoserver:v1.0.0" in script

    def test_assettoserver_script_creates_status_file(self):
        """Test that deployment status file is created."""
        ec2_manager = EC2Manager("us-east-1")
        script = ec2_manager.create_assettoserver_user_data_script("bucket", "key.tar.gz")

        assert "deploy-status.json" in script
        assert '"status": "success"' in script
        assert '"assettoserver_version"' in script

    def test_config_has_assettoserver_fields(self):
        """Test that ServerConfig has AssettoServer fields."""
        config = ServerConfig(use_assettoserver=True, assettoserver_version="v0.0.54")

        assert config.use_assettoserver is True
        assert config.assettoserver_version == "v0.0.54"

    def test_config_defaults_to_traditional_deployment(self):
        """Test that ServerConfig defaults to traditional AC server."""
        config = ServerConfig()

        assert config.use_assettoserver is False
        assert config.assettoserver_version == "v0.0.54"  # Default version still set
