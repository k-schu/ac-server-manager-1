"""Unit tests for user-data size limits and S3 bootstrap approach."""

from unittest.mock import patch
import pytest

from ac_server_manager.ec2_manager import EC2Manager
from ac_server_manager.s3_manager import S3Manager


def test_validate_user_data_size_within_limit() -> None:
    """Test that user-data within limit passes validation."""
    manager = EC2Manager("us-east-1")
    small_user_data = "#!/bin/bash\necho 'hello'\n" * 100  # Small script

    # Should not raise
    manager.validate_user_data_size(small_user_data)


def test_validate_user_data_size_exceeds_limit() -> None:
    """Test that user-data exceeding limit raises error."""
    manager = EC2Manager("us-east-1")
    # Create a large user-data that exceeds 16384 bytes
    large_user_data = "#!/bin/bash\n" + ("echo 'test'\n" * 2000)

    with pytest.raises(RuntimeError) as exc_info:
        manager.validate_user_data_size(large_user_data)

    assert "exceeds AWS EC2 limit" in str(exc_info.value)
    assert "16384 bytes" in str(exc_info.value)


def test_create_minimal_user_data_script_with_iam() -> None:
    """Test minimal user-data creation with IAM instance profile."""
    manager = EC2Manager("us-east-1")

    user_data = manager.create_minimal_user_data_script(
        s3_bucket="test-bucket",
        s3_key="packs/test.tar.gz",
        installer_s3_key="installers/installer.sh",
        presigned_url_installer=None,
        presigned_url_pack=None,
        wrapper_port=8080,
    )

    # Verify it's a bash script
    assert user_data.startswith("#!/bin/bash")

    # Verify it contains AWS CLI command
    assert "aws s3 cp" in user_data
    assert "awscli" in user_data

    # Verify environment variable exports
    assert "S3_BUCKET=" in user_data
    assert "S3_KEY=" in user_data

    # Verify it's under the limit
    size = len(user_data.encode("utf-8"))
    assert size < 16384


def test_create_minimal_user_data_script_with_presigned_urls() -> None:
    """Test minimal user-data creation with presigned URLs."""
    manager = EC2Manager("us-east-1")

    presigned_installer = "https://test-bucket.s3.amazonaws.com/installer.sh?X-Amz-Signature=abc123"
    presigned_pack = "https://test-bucket.s3.amazonaws.com/pack.tar.gz?X-Amz-Signature=xyz789"

    user_data = manager.create_minimal_user_data_script(
        s3_bucket="test-bucket",
        s3_key="packs/test.tar.gz",
        installer_s3_key="installers/installer.sh",
        presigned_url_installer=presigned_installer,
        presigned_url_pack=presigned_pack,
        wrapper_port=8080,
    )

    # Verify it's a bash script
    assert user_data.startswith("#!/bin/bash")

    # Verify it uses curl instead of AWS CLI
    assert "curl" in user_data
    assert presigned_installer in user_data

    # Verify PRESIGNED_URL is exported for the pack
    assert "PRESIGNED_URL=" in user_data
    assert presigned_pack in user_data

    # Verify it's under the limit
    size = len(user_data.encode("utf-8"))
    assert size < 16384


def test_minimal_user_data_is_significantly_smaller_than_full_script() -> None:
    """Test that minimal user-data is much smaller than the old full script."""
    manager = EC2Manager("us-east-1")

    # Old approach (full script in user-data)
    old_user_data = manager.create_user_data_script(
        s3_bucket="test-bucket",
        s3_key="packs/test.tar.gz",
        wrapper_port=8080,
    )

    # New approach (minimal bootstrap)
    new_user_data = manager.create_minimal_user_data_script(
        s3_bucket="test-bucket",
        s3_key="packs/test.tar.gz",
        installer_s3_key="installers/installer.sh",
        presigned_url_installer=None,
        presigned_url_pack=None,
        wrapper_port=8080,
    )

    old_size = len(old_user_data.encode("utf-8"))
    new_size = len(new_user_data.encode("utf-8"))

    # Verify old script exceeds limit
    assert old_size >= 16384, f"Old script should exceed limit, but is {old_size} bytes"

    # Verify new script is under limit
    assert new_size < 16384, f"New script should be under limit, but is {new_size} bytes"

    # Verify new script is significantly smaller (at least 90% reduction)
    reduction_percent = ((old_size - new_size) / old_size) * 100
    assert reduction_percent > 90, f"Size reduction should be >90%, but is {reduction_percent:.1f}%"


def test_s3_manager_upload_file_content() -> None:
    """Test S3Manager can upload file content as string."""
    manager = S3Manager("test-bucket", "us-east-1")

    with patch.object(manager.s3_client, "put_object") as mock_put:
        mock_put.return_value = {}

        result = manager.upload_file_content("test content", "test-key")

        assert result is True
        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert call_args[1]["Bucket"] == "test-bucket"
        assert call_args[1]["Key"] == "test-key"
        assert call_args[1]["Body"] == b"test content"


def test_s3_manager_generate_presigned_url() -> None:
    """Test S3Manager can generate presigned URLs."""
    manager = S3Manager("test-bucket", "us-east-1")

    with patch.object(manager.s3_client, "generate_presigned_url") as mock_generate:
        mock_generate.return_value = (
            "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Signature=abc"
        )

        result = manager.generate_presigned_url("test-key", expiration=3600)

        assert result is not None
        assert result.startswith("https://")
        mock_generate.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "test-key"},
            ExpiresIn=3600,
        )


def test_s3_manager_generate_presigned_url_custom_expiration() -> None:
    """Test S3Manager generates presigned URLs with custom expiration."""
    manager = S3Manager("test-bucket", "us-east-1")

    with patch.object(manager.s3_client, "generate_presigned_url") as mock_generate:
        mock_generate.return_value = (
            "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Signature=abc"
        )

        result = manager.generate_presigned_url("test-key", expiration=7200)

        assert result is not None
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args
        assert call_args[1]["ExpiresIn"] == 7200
