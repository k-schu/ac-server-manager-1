"""Tests for ACServerDeployer."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ac_server_manager.deployer import ACServerDeployer
from ac_server_manager.config import DeploymentConfig


@pytest.fixture
def deployer():
    """Create a deployer with mocked managers."""
    with patch("ac_server_manager.deployer.S3Manager") as mock_s3, \
         patch("ac_server_manager.deployer.EC2Manager") as mock_ec2:
        
        dep = ACServerDeployer()
        dep.s3_manager = mock_s3.return_value
        dep.ec2_manager = mock_ec2.return_value
        yield dep


@pytest.fixture
def mock_pack_file(tmp_path):
    """Create a mock pack file."""
    pack_file = tmp_path / "test-pack.zip"
    pack_file.write_text("test content")
    return pack_file


def test_deploy(deployer, mock_pack_file):
    """Test deploying a server."""
    deployer.s3_manager.create_bucket.return_value = True
    deployer.s3_manager.upload_pack.return_value = "test-pack.zip"
    deployer.s3_manager.get_pack_url.return_value = "https://example.com/pack.zip"
    deployer.ec2_manager.create_security_group.return_value = "sg-12345"
    deployer.ec2_manager.launch_instance.return_value = "i-12345"
    deployer.ec2_manager.get_instance_info.return_value = {
        "instance_id": "i-12345",
        "public_ip": "1.2.3.4",
        "state": "running"
    }
    deployer.ec2_manager.get_server_info.return_value = {
        "AC_SERVER_LINK": "http://acstuff.ru/s/q/abc123",
        "SERVER_STATUS": "RUNNING"
    }
    
    result = deployer.deploy(mock_pack_file, "test-server")
    
    assert result["instance_id"] == "i-12345"
    assert result["instance_name"] == "test-server"
    assert result["acstuff_link"] == "http://acstuff.ru/s/q/abc123"
    assert result["public_ip"] == "1.2.3.4"


def test_deploy_without_server_info(deployer, mock_pack_file):
    """Test deploying when server info is not available."""
    deployer.s3_manager.create_bucket.return_value = True
    deployer.s3_manager.upload_pack.return_value = "test-pack.zip"
    deployer.s3_manager.get_pack_url.return_value = "https://example.com/pack.zip"
    deployer.ec2_manager.create_security_group.return_value = "sg-12345"
    deployer.ec2_manager.launch_instance.return_value = "i-12345"
    deployer.ec2_manager.get_instance_info.return_value = {
        "instance_id": "i-12345",
        "public_ip": "1.2.3.4"
    }
    deployer.ec2_manager.get_server_info.return_value = None
    
    result = deployer.deploy(mock_pack_file)
    
    assert result["instance_id"] == "i-12345"
    assert "acstuff_link" not in result


def test_stop_server(deployer):
    """Test stopping a server."""
    deployer.ec2_manager.stop_instance.return_value = True
    
    result = deployer.stop_server("i-12345")
    
    assert result is True
    deployer.ec2_manager.stop_instance.assert_called_once_with("i-12345")


def test_start_server(deployer):
    """Test starting a server."""
    deployer.ec2_manager.start_instance.return_value = True
    
    result = deployer.start_server("i-12345")
    
    assert result is True
    deployer.ec2_manager.start_instance.assert_called_once_with("i-12345")


def test_terminate_server(deployer):
    """Test terminating a server."""
    deployer.ec2_manager.terminate_instance.return_value = True
    
    result = deployer.terminate_server("i-12345")
    
    assert result is True
    deployer.ec2_manager.terminate_instance.assert_called_once_with("i-12345")


def test_redeploy_server(deployer, mock_pack_file):
    """Test redeploying a server."""
    deployer.ec2_manager.terminate_instance.return_value = True
    deployer.s3_manager.create_bucket.return_value = True
    deployer.s3_manager.upload_pack.return_value = "test-pack.zip"
    deployer.s3_manager.get_pack_url.return_value = "https://example.com/pack.zip"
    deployer.ec2_manager.create_security_group.return_value = "sg-12345"
    deployer.ec2_manager.launch_instance.return_value = "i-67890"
    deployer.ec2_manager.get_instance_info.return_value = {
        "instance_id": "i-67890",
        "public_ip": "1.2.3.4"
    }
    deployer.ec2_manager.get_server_info.return_value = None
    
    result = deployer.redeploy_server("i-12345", mock_pack_file, "new-server")
    
    assert result["instance_id"] == "i-67890"
    deployer.ec2_manager.terminate_instance.assert_called_once_with("i-12345")


def test_get_server_status(deployer):
    """Test getting server status."""
    deployer.ec2_manager.get_instance_info.return_value = {
        "instance_id": "i-12345",
        "state": "running"
    }
    
    result = deployer.get_server_status("i-12345")
    
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "running"


def test_list_servers(deployer):
    """Test listing servers."""
    deployer.ec2_manager.find_instances_by_tag.return_value = ["i-12345", "i-67890"]
    deployer.ec2_manager.get_instance_info.side_effect = [
        {"instance_id": "i-12345", "state": "running"},
        {"instance_id": "i-67890", "state": "stopped"}
    ]
    
    result = deployer.list_servers()
    
    assert len(result) == 2
    assert result[0]["instance_id"] == "i-12345"
    assert result[1]["instance_id"] == "i-67890"


def test_delete_pack(deployer):
    """Test deleting a pack."""
    deployer.s3_manager.delete_pack.return_value = True
    
    result = deployer.delete_pack("test-pack.zip")
    
    assert result is True
    deployer.s3_manager.delete_pack.assert_called_once_with("test-pack.zip")


def test_list_packs(deployer):
    """Test listing packs."""
    deployer.s3_manager.list_packs.return_value = ["pack1.zip", "pack2.zip"]
    
    result = deployer.list_packs()
    
    assert result == ["pack1.zip", "pack2.zip"]
