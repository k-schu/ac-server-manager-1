"""Unit tests for EC2Manager."""

from unittest.mock import MagicMock, patch
import pytest

from ac_server_manager.ec2_manager import EC2Manager


@pytest.fixture
def ec2_manager() -> EC2Manager:
    """Create EC2Manager instance for testing."""
    with patch("boto3.client"), patch("boto3.resource"):
        return EC2Manager("us-east-1")


def test_ec2_manager_init(ec2_manager: EC2Manager) -> None:
    """Test EC2Manager initialization."""
    assert ec2_manager.region == "us-east-1"


def test_create_security_group_already_exists(ec2_manager: EC2Manager) -> None:
    """Test create_security_group when group already exists."""
    ec2_manager.ec2_client.describe_security_groups = MagicMock(
        return_value={"SecurityGroups": [{"GroupId": "sg-12345"}]}
    )

    result = ec2_manager.create_security_group("test-sg", "Test security group")

    assert result == "sg-12345"


def test_create_security_group_new(ec2_manager: EC2Manager) -> None:
    """Test create_security_group when creating new group."""
    ec2_manager.ec2_client.describe_security_groups = MagicMock(return_value={"SecurityGroups": []})
    ec2_manager.ec2_client.create_security_group = MagicMock(return_value={"GroupId": "sg-67890"})
    ec2_manager.ec2_client.authorize_security_group_ingress = MagicMock()

    result = ec2_manager.create_security_group("test-sg", "Test security group")

    assert result == "sg-67890"
    ec2_manager.ec2_client.create_security_group.assert_called_once()
    ec2_manager.ec2_client.authorize_security_group_ingress.assert_called_once()


def test_get_ubuntu_ami_success(ec2_manager: EC2Manager) -> None:
    """Test getting Ubuntu AMI."""
    ec2_manager.ec2_client.describe_images = MagicMock(
        return_value={
            "Images": [
                {"ImageId": "ami-old", "CreationDate": "2023-01-01T00:00:00.000Z"},
                {"ImageId": "ami-new", "CreationDate": "2023-12-01T00:00:00.000Z"},
            ]
        }
    )

    result = ec2_manager.get_ubuntu_ami()

    assert result == "ami-new"


def test_get_ubuntu_ami_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting Ubuntu AMI when none found."""
    ec2_manager.ec2_client.describe_images = MagicMock(return_value={"Images": []})

    result = ec2_manager.get_ubuntu_ami()

    assert result is None


def test_create_user_data_script(ec2_manager: EC2Manager) -> None:
    """Test user data script creation."""
    script = ec2_manager.create_user_data_script("test-bucket", "packs/test.tar.gz")

    assert "#!/bin/bash" in script
    assert "aws s3 cp s3://test-bucket/packs/test.tar.gz" in script
    assert "tar -xzf server-pack.tar.gz" in script
    assert "chmod +x acServer" in script
    assert "systemctl start acserver" in script


def test_launch_instance_success(ec2_manager: EC2Manager) -> None:
    """Test successful instance launch."""
    ec2_manager.ec2_client.run_instances = MagicMock(
        return_value={"Instances": [{"InstanceId": "i-12345"}]}
    )
    ec2_manager.ec2_client.get_waiter = MagicMock()

    result = ec2_manager.launch_instance(
        ami_id="ami-12345",
        instance_type="t3.small",
        security_group_id="sg-12345",
        user_data="#!/bin/bash",
        instance_name="test-instance",
    )

    assert result == "i-12345"
    ec2_manager.ec2_client.run_instances.assert_called_once()


def test_launch_instance_with_key(ec2_manager: EC2Manager) -> None:
    """Test instance launch with SSH key."""
    ec2_manager.ec2_client.run_instances = MagicMock(
        return_value={"Instances": [{"InstanceId": "i-12345"}]}
    )
    ec2_manager.ec2_client.get_waiter = MagicMock()

    result = ec2_manager.launch_instance(
        ami_id="ami-12345",
        instance_type="t3.small",
        security_group_id="sg-12345",
        user_data="#!/bin/bash",
        instance_name="test-instance",
        key_name="my-key",
    )

    assert result == "i-12345"
    call_args = ec2_manager.ec2_client.run_instances.call_args[1]
    assert call_args["KeyName"] == "my-key"


def test_get_instance_public_ip(ec2_manager: EC2Manager) -> None:
    """Test getting instance public IP."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={"Reservations": [{"Instances": [{"PublicIpAddress": "1.2.3.4"}]}]}
    )

    result = ec2_manager.get_instance_public_ip("i-12345")

    assert result == "1.2.3.4"


def test_get_instance_public_ip_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting instance public IP when not found."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.get_instance_public_ip("i-12345")

    assert result is None


def test_stop_instance(ec2_manager: EC2Manager) -> None:
    """Test stopping instance."""
    ec2_manager.ec2_client.stop_instances = MagicMock()

    result = ec2_manager.stop_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.stop_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_start_instance(ec2_manager: EC2Manager) -> None:
    """Test starting instance."""
    ec2_manager.ec2_client.start_instances = MagicMock()

    result = ec2_manager.start_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.start_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_terminate_instance(ec2_manager: EC2Manager) -> None:
    """Test terminating instance."""
    ec2_manager.ec2_client.terminate_instances = MagicMock()

    result = ec2_manager.terminate_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_find_instances_by_name(ec2_manager: EC2Manager) -> None:
    """Test finding instances by name."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-12345"}]},
                {"Instances": [{"InstanceId": "i-67890"}]},
            ]
        }
    )

    result = ec2_manager.find_instances_by_name("test-instance")

    assert len(result) == 2
    assert "i-12345" in result
    assert "i-67890" in result


def test_find_instances_by_name_none_found(ec2_manager: EC2Manager) -> None:
    """Test finding instances by name when none exist."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.find_instances_by_name("test-instance")

    assert result == []


def test_get_instance_details_success(ec2_manager: EC2Manager) -> None:
    """Test getting instance details successfully."""
    from datetime import datetime

    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-12345",
                            "State": {"Name": "running"},
                            "InstanceType": "t3.small",
                            "PublicIpAddress": "1.2.3.4",
                            "PrivateIpAddress": "10.0.0.1",
                            "LaunchTime": datetime(2024, 1, 1),
                            "Tags": [
                                {"Key": "Name", "Value": "test-instance"},
                                {"Key": "Application", "Value": "ac-server"},
                            ],
                        }
                    ]
                }
            ]
        }
    )

    result = ec2_manager.get_instance_details("i-12345")

    assert result is not None
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "running"
    assert result["instance_type"] == "t3.small"
    assert result["public_ip"] == "1.2.3.4"
    assert result["private_ip"] == "10.0.0.1"
    assert result["name"] == "test-instance"


def test_get_instance_details_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting instance details when instance not found."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.get_instance_details("i-99999")

    assert result is None


def test_get_instance_details_no_public_ip(ec2_manager: EC2Manager) -> None:
    """Test getting instance details when no public IP assigned."""
    from datetime import datetime

    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-12345",
                            "State": {"Name": "stopped"},
                            "InstanceType": "t3.small",
                            "PrivateIpAddress": "10.0.0.1",
                            "LaunchTime": datetime(2024, 1, 1),
                            "Tags": [{"Key": "Name", "Value": "test-instance"}],
                        }
                    ]
                }
            ]
        }
    )

    result = ec2_manager.get_instance_details("i-12345")

    assert result is not None
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "stopped"
    assert result["public_ip"] is None
