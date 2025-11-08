"""Unit tests for IAMManager."""

from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError

from ac_server_manager.iam_manager import IAMManager


@pytest.fixture
def iam_manager() -> IAMManager:
    """Create IAMManager instance for testing."""
    with patch("boto3.client"):
        return IAMManager("us-east-1")


def test_iam_manager_init(iam_manager: IAMManager) -> None:
    """Test IAMManager initialization."""
    assert iam_manager.region == "us-east-1"


def test_ensure_role_and_instance_profile_creates_new_resources(
    iam_manager: IAMManager,
) -> None:
    """Test ensure_role_and_instance_profile when creating new resources."""
    # Mock get_role to raise NoSuchEntity (role doesn't exist)
    iam_manager.iam_client.get_role = MagicMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchEntity"}}, "get_role"
        )
    )
    # Mock create_role
    iam_manager.iam_client.create_role = MagicMock(
        return_value={"Role": {"Arn": "arn:aws:iam::123456789012:role/test-role"}}
    )
    
    # Mock get_instance_profile to first raise NoSuchEntity, then return created profile
    iam_manager.iam_client.get_instance_profile = MagicMock(
        side_effect=[
            ClientError({"Error": {"Code": "NoSuchEntity"}}, "get_instance_profile"),
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::123456789012:instance-profile/test-profile",
                    "Roles": [],
                }
            }
        ]
    )
    # Mock create_instance_profile
    iam_manager.iam_client.create_instance_profile = MagicMock(
        return_value={
            "InstanceProfile": {
                "Arn": "arn:aws:iam::123456789012:instance-profile/test-profile"
            }
        }
    )
    # Mock add_role_to_instance_profile
    iam_manager.iam_client.add_role_to_instance_profile = MagicMock()
    # Mock put_role_policy
    iam_manager.iam_client.put_role_policy = MagicMock()

    result = iam_manager.ensure_role_and_instance_profile(
        "test-role", "test-profile", "test-bucket"
    )

    assert result == "test-profile"
    iam_manager.iam_client.create_role.assert_called_once()
    iam_manager.iam_client.create_instance_profile.assert_called_once()
    iam_manager.iam_client.add_role_to_instance_profile.assert_called_once()
    iam_manager.iam_client.put_role_policy.assert_called_once()


def test_ensure_role_and_instance_profile_uses_existing_resources(
    iam_manager: IAMManager,
) -> None:
    """Test ensure_role_and_instance_profile when resources already exist."""
    # Mock get_role to return existing role
    iam_manager.iam_client.get_role = MagicMock(
        return_value={"Role": {"Arn": "arn:aws:iam::123456789012:role/test-role"}}
    )
    # Mock get_instance_profile to return existing profile with role already attached
    iam_manager.iam_client.get_instance_profile = MagicMock(
        return_value={
            "InstanceProfile": {
                "Arn": "arn:aws:iam::123456789012:instance-profile/test-profile",
                "Roles": [{"RoleName": "test-role"}],
            }
        }
    )
    # Mock put_role_policy
    iam_manager.iam_client.put_role_policy = MagicMock()

    result = iam_manager.ensure_role_and_instance_profile(
        "test-role", "test-profile", "test-bucket"
    )

    assert result == "test-profile"
    # Should not create resources since they exist
    assert not hasattr(iam_manager.iam_client, "create_role") or not iam_manager.iam_client.create_role.called
    # Should still update the policy (idempotent)
    iam_manager.iam_client.put_role_policy.assert_called_once()


def test_ensure_role_and_instance_profile_attaches_role_to_profile(
    iam_manager: IAMManager,
) -> None:
    """Test ensure_role_and_instance_profile attaches role to profile if not attached."""
    # Mock get_role to return existing role
    iam_manager.iam_client.get_role = MagicMock(
        return_value={"Role": {"Arn": "arn:aws:iam::123456789012:role/test-role"}}
    )
    # Mock get_instance_profile to return existing profile without role attached
    iam_manager.iam_client.get_instance_profile = MagicMock(
        return_value={
            "InstanceProfile": {
                "Arn": "arn:aws:iam::123456789012:instance-profile/test-profile",
                "Roles": [],
            }
        }
    )
    # Mock add_role_to_instance_profile
    iam_manager.iam_client.add_role_to_instance_profile = MagicMock()
    # Mock put_role_policy
    iam_manager.iam_client.put_role_policy = MagicMock()

    result = iam_manager.ensure_role_and_instance_profile(
        "test-role", "test-profile", "test-bucket"
    )

    assert result == "test-profile"
    # Should attach role since it wasn't attached
    iam_manager.iam_client.add_role_to_instance_profile.assert_called_once_with(
        InstanceProfileName="test-profile", RoleName="test-role"
    )


def test_ensure_role_and_instance_profile_handles_permission_error(
    iam_manager: IAMManager,
) -> None:
    """Test ensure_role_and_instance_profile handles permission errors."""
    # Mock get_role to raise AccessDenied
    iam_manager.iam_client.get_role = MagicMock(
        side_effect=ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}},
            "get_role",
        )
    )

    with pytest.raises(Exception) as exc_info:
        iam_manager.ensure_role_and_instance_profile(
            "test-role", "test-profile", "test-bucket"
        )

    assert "Failed to create/configure IAM resources" in str(exc_info.value)
    assert "User is not authorized" in str(exc_info.value)


def test_attach_s3_policy_creates_correct_policy(iam_manager: IAMManager) -> None:
    """Test that _attach_s3_policy creates correct policy document."""
    import json

    iam_manager.iam_client.put_role_policy = MagicMock()

    iam_manager._attach_s3_policy("test-role", "test-bucket")

    # Verify put_role_policy was called
    iam_manager.iam_client.put_role_policy.assert_called_once()
    call_args = iam_manager.iam_client.put_role_policy.call_args

    # Verify the policy document
    policy_doc = json.loads(call_args[1]["PolicyDocument"])
    assert policy_doc["Version"] == "2012-10-17"
    assert len(policy_doc["Statement"]) == 2

    # Check GetObject statement
    get_object_stmt = policy_doc["Statement"][0]
    assert get_object_stmt["Effect"] == "Allow"
    assert "s3:GetObject" in get_object_stmt["Action"]
    assert "arn:aws:s3:::test-bucket/*" in get_object_stmt["Resource"]

    # Check ListBucket statement
    list_bucket_stmt = policy_doc["Statement"][1]
    assert list_bucket_stmt["Effect"] == "Allow"
    assert "s3:ListBucket" in list_bucket_stmt["Action"]
    assert "arn:aws:s3:::test-bucket" in list_bucket_stmt["Resource"]


def test_ensure_role_creates_role_with_ec2_trust_policy(
    iam_manager: IAMManager,
) -> None:
    """Test that _ensure_role creates role with correct EC2 trust policy."""
    import json

    # Mock get_role to raise NoSuchEntity
    iam_manager.iam_client.get_role = MagicMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchEntity"}}, "get_role"
        )
    )
    # Mock create_role
    iam_manager.iam_client.create_role = MagicMock(
        return_value={"Role": {"Arn": "arn:aws:iam::123456789012:role/test-role"}}
    )

    iam_manager._ensure_role("test-role")

    # Verify create_role was called
    iam_manager.iam_client.create_role.assert_called_once()
    call_args = iam_manager.iam_client.create_role.call_args

    # Verify the trust policy
    trust_policy = json.loads(call_args[1]["AssumeRolePolicyDocument"])
    assert trust_policy["Version"] == "2012-10-17"
    assert len(trust_policy["Statement"]) == 1

    statement = trust_policy["Statement"][0]
    assert statement["Effect"] == "Allow"
    assert statement["Principal"] == {"Service": "ec2.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"
