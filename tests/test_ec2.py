"""Tests for EC2Manager."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from ac_server_manager.ec2 import EC2Manager
from ac_server_manager.config import ServerConfig


@pytest.fixture
def ec2_manager():
    """Create an EC2Manager instance with mocked boto3 clients."""
    with patch("ac_server_manager.ec2.boto3.Session") as mock_session:
        mock_ec2_client = Mock()
        mock_ssm_client = Mock()
        mock_session.return_value.client.side_effect = lambda service: {
            "ec2": mock_ec2_client,
            "ssm": mock_ssm_client
        }[service]
        
        manager = EC2Manager("us-east-1")
        manager.ec2_client = mock_ec2_client
        manager.ssm_client = mock_ssm_client
        yield manager


@pytest.fixture
def server_config():
    """Create a test server configuration."""
    return ServerConfig()


def test_get_windows_ami(ec2_manager):
    """Test getting Windows AMI ID."""
    ec2_manager.ec2_client.describe_images.return_value = {
        "Images": [
            {"ImageId": "ami-12345", "CreationDate": "2023-01-01"},
            {"ImageId": "ami-67890", "CreationDate": "2023-06-01"},
        ]
    }
    
    result = ec2_manager.get_windows_ami()
    
    assert result == "ami-67890"  # Should return the latest one


def test_create_security_group_existing(ec2_manager, server_config):
    """Test getting existing security group."""
    ec2_manager.ec2_client.describe_security_groups.return_value = {
        "SecurityGroups": [{"GroupId": "sg-12345"}]
    }
    
    result = ec2_manager.create_security_group("test-sg", server_config)
    
    assert result == "sg-12345"


def test_create_security_group_new(ec2_manager, server_config):
    """Test creating a new security group."""
    ec2_manager.ec2_client.describe_security_groups.return_value = {
        "SecurityGroups": []
    }
    ec2_manager.ec2_client.describe_vpcs.return_value = {
        "Vpcs": [{"VpcId": "vpc-12345"}]
    }
    ec2_manager.ec2_client.create_security_group.return_value = {
        "GroupId": "sg-67890"
    }
    ec2_manager.ec2_client.authorize_security_group_ingress.return_value = {}
    
    result = ec2_manager.create_security_group("test-sg", server_config)
    
    assert result == "sg-67890"
    ec2_manager.ec2_client.authorize_security_group_ingress.assert_called_once()


def test_create_user_data_script(ec2_manager):
    """Test creating user data script."""
    result = ec2_manager.create_user_data_script(
        "https://example.com/pack.zip",
        8081,
        9600
    )
    
    assert "https://example.com/pack.zip" in result
    assert "acServer.exe" in result
    assert "ac-server-info" in result


def test_launch_instance(ec2_manager, server_config):
    """Test launching an EC2 instance."""
    ec2_manager.ec2_client.describe_images.return_value = {
        "Images": [{"ImageId": "ami-12345", "CreationDate": "2023-01-01"}]
    }
    ec2_manager.ec2_client.run_instances.return_value = {
        "Instances": [{"InstanceId": "i-12345"}]
    }
    
    # Mock waiter
    mock_waiter = Mock()
    ec2_manager.ec2_client.get_waiter.return_value = mock_waiter
    
    with patch.object(ec2_manager, "_get_or_create_ssm_instance_profile", return_value="test-profile"):
        result = ec2_manager.launch_instance(
            "test-instance",
            server_config,
            "sg-12345",
            "https://example.com/pack.zip"
        )
    
    assert result == "i-12345"
    mock_waiter.wait.assert_called_once()


def test_get_instance_info(ec2_manager):
    """Test getting instance information."""
    ec2_manager.ec2_client.describe_instances.return_value = {
        "Reservations": [{
            "Instances": [{
                "InstanceId": "i-12345",
                "State": {"Name": "running"},
                "PublicIpAddress": "1.2.3.4",
                "PrivateIpAddress": "10.0.0.1",
                "InstanceType": "t3.small",
                "LaunchTime": "2023-01-01T00:00:00Z"
            }]
        }]
    }
    
    with patch.object(ec2_manager, "get_server_info", return_value=None):
        result = ec2_manager.get_instance_info("i-12345")
    
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "running"
    assert result["public_ip"] == "1.2.3.4"


def test_stop_instance(ec2_manager):
    """Test stopping an instance."""
    ec2_manager.ec2_client.stop_instances.return_value = {}
    
    result = ec2_manager.stop_instance("i-12345")
    
    assert result is True
    ec2_manager.ec2_client.stop_instances.assert_called_once_with(
        InstanceIds=["i-12345"]
    )


def test_start_instance(ec2_manager):
    """Test starting an instance."""
    ec2_manager.ec2_client.start_instances.return_value = {}
    
    result = ec2_manager.start_instance("i-12345")
    
    assert result is True
    ec2_manager.ec2_client.start_instances.assert_called_once_with(
        InstanceIds=["i-12345"]
    )


def test_terminate_instance(ec2_manager):
    """Test terminating an instance."""
    ec2_manager.ec2_client.terminate_instances.return_value = {}
    
    result = ec2_manager.terminate_instance("i-12345")
    
    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_called_once_with(
        InstanceIds=["i-12345"]
    )


def test_find_instances_by_tag(ec2_manager):
    """Test finding instances by tag."""
    ec2_manager.ec2_client.describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": "i-12345"}]},
            {"Instances": [{"InstanceId": "i-67890"}]}
        ]
    }
    
    result = ec2_manager.find_instances_by_tag("Application", "AssettoCorsaServer")
    
    assert result == ["i-12345", "i-67890"]
