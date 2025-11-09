"""Unit tests for Deployer."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from ac_server_manager.config import ServerConfig
from ac_server_manager.deployer import Deployer


@pytest.fixture
def config() -> ServerConfig:
    """Create test configuration."""
    return ServerConfig(
        aws_region="us-east-1",
        instance_type="t3.small",
        s3_bucket_name="test-bucket",
        instance_name="test-instance",
    )


@pytest.fixture
def deployer(config: ServerConfig) -> Deployer:
    """Create Deployer instance for testing."""
    with (
        patch("ac_server_manager.deployer.S3Manager"),
        patch("ac_server_manager.deployer.EC2Manager"),
    ):
        return Deployer(config)


def test_deployer_init(deployer: Deployer, config: ServerConfig) -> None:
    """Test Deployer initialization."""
    assert deployer.config == config


def test_deploy_success(deployer: Deployer, tmp_path: Path) -> None:
    """Test successful deployment."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    # Mock all the required methods
    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value="packs/test-pack.tar.gz")
    deployer.ec2_manager.create_security_group = MagicMock(return_value="sg-12345")
    deployer.ec2_manager.get_ubuntu_ami = MagicMock(return_value="ami-12345")
    deployer.ec2_manager.create_user_data_script = MagicMock(return_value="#!/bin/bash")
    deployer.ec2_manager.upload_bootstrap_to_s3 = MagicMock(
        return_value=("bootstrap/test.sh", "https://presigned-url")
    )
    deployer.ec2_manager.create_minimal_user_data_with_presigned_url = MagicMock(
        return_value="#!/bin/bash\nminimal"
    )
    deployer.ec2_manager.launch_instance = MagicMock(return_value="i-12345")
    deployer.ec2_manager.get_instance_public_ip = MagicMock(return_value="1.2.3.4")

    result = deployer.deploy(pack_file)

    assert result == "i-12345"
    deployer.s3_manager.create_bucket.assert_called_once()
    deployer.s3_manager.upload_pack.assert_called_once_with(pack_file)
    deployer.ec2_manager.create_security_group.assert_called_once()
    deployer.ec2_manager.get_ubuntu_ami.assert_called_once()
    deployer.ec2_manager.upload_bootstrap_to_s3.assert_called_once()
    deployer.ec2_manager.create_minimal_user_data_with_presigned_url.assert_called_once()
    deployer.ec2_manager.launch_instance.assert_called_once()


def test_deploy_bucket_creation_fails(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when bucket creation fails."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=False)

    result = deployer.deploy(pack_file)

    assert result is None


def test_deploy_upload_fails(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when pack upload fails."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value=None)

    result = deployer.deploy(pack_file)

    assert result is None


def test_deploy_security_group_fails(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when security group creation fails."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value="packs/test-pack.tar.gz")
    deployer.ec2_manager.create_security_group = MagicMock(return_value=None)

    result = deployer.deploy(pack_file)

    assert result is None


def test_deploy_ami_not_found(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when AMI is not found."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value="packs/test-pack.tar.gz")
    deployer.ec2_manager.create_security_group = MagicMock(return_value="sg-12345")
    deployer.ec2_manager.get_ubuntu_ami = MagicMock(return_value=None)

    result = deployer.deploy(pack_file)

    assert result is None


def test_deploy_instance_launch_fails(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when instance launch fails."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value="packs/test-pack.tar.gz")
    deployer.ec2_manager.create_security_group = MagicMock(return_value="sg-12345")
    deployer.ec2_manager.get_ubuntu_ami = MagicMock(return_value="ami-12345")
    deployer.ec2_manager.create_user_data_script = MagicMock(return_value="#!/bin/bash")
    deployer.ec2_manager.upload_bootstrap_to_s3 = MagicMock(
        return_value=("bootstrap/test.sh", "https://presigned-url")
    )
    deployer.ec2_manager.create_minimal_user_data_with_presigned_url = MagicMock(
        return_value="#!/bin/bash\nminimal"
    )
    deployer.ec2_manager.launch_instance = MagicMock(return_value=None)

    result = deployer.deploy(pack_file)

    assert result is None


def test_stop_with_instance_id(deployer: Deployer) -> None:
    """Test stopping instance with explicit instance ID."""
    deployer.ec2_manager.stop_instance = MagicMock(return_value=True)

    result = deployer.stop("i-12345")

    assert result is True
    deployer.ec2_manager.stop_instance.assert_called_once_with("i-12345")


def test_stop_by_name(deployer: Deployer) -> None:
    """Test stopping instance by name."""
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-12345"])
    deployer.ec2_manager.stop_instance = MagicMock(return_value=True)

    result = deployer.stop()

    assert result is True
    deployer.ec2_manager.find_instances_by_name.assert_called_once()
    deployer.ec2_manager.stop_instance.assert_called_once_with("i-12345")


def test_stop_no_instances_found(deployer: Deployer) -> None:
    """Test stopping instance when none found."""
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=[])

    result = deployer.stop()

    assert result is False


def test_start_with_instance_id(deployer: Deployer) -> None:
    """Test starting instance with explicit instance ID."""
    deployer.ec2_manager.start_instance = MagicMock(return_value=True)

    result = deployer.start("i-12345")

    assert result is True
    deployer.ec2_manager.start_instance.assert_called_once_with("i-12345")


def test_start_by_name(deployer: Deployer) -> None:
    """Test starting instance by name."""
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-12345"])
    deployer.ec2_manager.start_instance = MagicMock(return_value=True)

    result = deployer.start()

    assert result is True
    deployer.ec2_manager.start_instance.assert_called_once_with("i-12345")


def test_terminate_with_instance_id(deployer: Deployer) -> None:
    """Test terminating instance with explicit instance ID."""
    deployer.ec2_manager.terminate_instance = MagicMock(return_value=True)

    result = deployer.terminate("i-12345")

    assert result is True
    deployer.ec2_manager.terminate_instance.assert_called_once_with("i-12345")


def test_terminate_by_name(deployer: Deployer) -> None:
    """Test terminating instance by name."""
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-12345"])
    deployer.ec2_manager.terminate_instance = MagicMock(return_value=True)

    result = deployer.terminate()

    assert result is True
    deployer.ec2_manager.terminate_instance.assert_called_once_with("i-12345")


def test_redeploy_success(deployer: Deployer, tmp_path: Path) -> None:
    """Test successful redeployment."""
    pack_file = tmp_path / "new-pack.tar.gz"
    pack_file.write_text("new content")

    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-old"])
    deployer.ec2_manager.terminate_instance = MagicMock(return_value=True)

    # Mock deploy method
    deployer.deploy = MagicMock(return_value="i-new")

    result = deployer.redeploy(pack_file)

    assert result == "i-new"
    deployer.ec2_manager.terminate_instance.assert_called_once()
    deployer.deploy.assert_called_once_with(pack_file)


def test_redeploy_terminate_fails_continues(deployer: Deployer, tmp_path: Path) -> None:
    """Test redeployment continues even if terminate fails."""
    pack_file = tmp_path / "new-pack.tar.gz"
    pack_file.write_text("new content")

    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-old"])
    deployer.ec2_manager.terminate_instance = MagicMock(return_value=False)
    deployer.deploy = MagicMock(return_value="i-new")

    result = deployer.redeploy(pack_file)

    assert result == "i-new"
    deployer.deploy.assert_called_once()


def test_get_status_with_instance_id(deployer: Deployer) -> None:
    """Test getting status with instance ID."""
    from datetime import datetime

    mock_details = {
        "instance_id": "i-12345",
        "state": "running",
        "instance_type": "t3.small",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }
    deployer.ec2_manager.get_instance_details = MagicMock(return_value=mock_details)

    result = deployer.get_status("i-12345")

    assert result == mock_details
    deployer.ec2_manager.get_instance_details.assert_called_once_with("i-12345")


def test_get_status_by_name(deployer: Deployer) -> None:
    """Test getting status by instance name."""
    from datetime import datetime

    mock_details = {
        "instance_id": "i-12345",
        "state": "running",
        "instance_type": "t3.small",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=["i-12345"])
    deployer.ec2_manager.get_instance_details = MagicMock(return_value=mock_details)

    result = deployer.get_status()

    assert result == mock_details
    deployer.ec2_manager.find_instances_by_name.assert_called_once_with("test-instance")
    deployer.ec2_manager.get_instance_details.assert_called_once_with("i-12345")


def test_get_status_no_instance_found(deployer: Deployer) -> None:
    """Test getting status when no instance found."""
    deployer.ec2_manager.find_instances_by_name = MagicMock(return_value=[])

    result = deployer.get_status()

    assert result is None


def test_deploy_bootstrap_upload_fails(deployer: Deployer, tmp_path: Path) -> None:
    """Test deployment when bootstrap upload to S3 fails."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    deployer.s3_manager.upload_pack = MagicMock(return_value="packs/test-pack.tar.gz")
    deployer.ec2_manager.create_security_group = MagicMock(return_value="sg-12345")
    deployer.ec2_manager.get_ubuntu_ami = MagicMock(return_value="ami-12345")
    deployer.ec2_manager.create_user_data_script = MagicMock(return_value="#!/bin/bash")
    deployer.ec2_manager.upload_bootstrap_to_s3 = MagicMock(return_value=None)

    result = deployer.deploy(pack_file)

    assert result is None
