"""Unit tests for S3Manager."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from ac_server_manager.s3_manager import S3Manager


@pytest.fixture
def s3_manager() -> S3Manager:
    """Create S3Manager instance for testing."""
    with patch("boto3.client"):
        return S3Manager("test-bucket", "us-east-1")


def test_s3_manager_init(s3_manager: S3Manager) -> None:
    """Test S3Manager initialization."""
    assert s3_manager.bucket_name == "test-bucket"
    assert s3_manager.region == "us-east-1"


def test_create_bucket_already_exists(s3_manager: S3Manager) -> None:
    """Test create_bucket when bucket already exists."""
    s3_manager.s3_client.head_bucket = MagicMock()

    result = s3_manager.create_bucket()

    assert result is True
    s3_manager.s3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")


def test_create_bucket_new(s3_manager: S3Manager) -> None:
    """Test create_bucket when creating new bucket."""
    from botocore.exceptions import ClientError

    # Mock head_bucket to raise 404
    s3_manager.s3_client.head_bucket = MagicMock(
        side_effect=ClientError({"Error": {"Code": "404"}}, "head_bucket")
    )
    s3_manager.s3_client.create_bucket = MagicMock()

    result = s3_manager.create_bucket()

    assert result is True
    s3_manager.s3_client.create_bucket.assert_called_once()


def test_upload_pack_success(s3_manager: S3Manager, tmp_path: Path) -> None:
    """Test successful pack upload."""
    # Create a temporary pack file
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    s3_manager.s3_client.upload_file = MagicMock()

    result = s3_manager.upload_pack(pack_file)

    assert result == "packs/test-pack.tar.gz"
    s3_manager.s3_client.upload_file.assert_called_once()


def test_upload_pack_file_not_found(s3_manager: S3Manager) -> None:
    """Test upload_pack with non-existent file."""
    result = s3_manager.upload_pack(Path("/nonexistent/file.tar.gz"))

    assert result is None


def test_upload_pack_custom_key(s3_manager: S3Manager, tmp_path: Path) -> None:
    """Test upload_pack with custom S3 key."""
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")

    s3_manager.s3_client.upload_file = MagicMock()

    result = s3_manager.upload_pack(pack_file, "custom/key.tar.gz")

    assert result == "custom/key.tar.gz"


def test_download_pack_success(s3_manager: S3Manager, tmp_path: Path) -> None:
    """Test successful pack download."""
    download_path = tmp_path / "downloaded-pack.tar.gz"
    s3_manager.s3_client.download_file = MagicMock()

    result = s3_manager.download_pack("packs/test.tar.gz", download_path)

    assert result is True
    s3_manager.s3_client.download_file.assert_called_once()


def test_list_packs_success(s3_manager: S3Manager) -> None:
    """Test listing packs."""
    s3_manager.s3_client.list_objects_v2 = MagicMock(
        return_value={"Contents": [{"Key": "packs/pack1.tar.gz"}, {"Key": "packs/pack2.tar.gz"}]}
    )

    result = s3_manager.list_packs()

    assert len(result) == 2
    assert "packs/pack1.tar.gz" in result
    assert "packs/pack2.tar.gz" in result


def test_list_packs_empty(s3_manager: S3Manager) -> None:
    """Test listing packs when bucket is empty."""
    s3_manager.s3_client.list_objects_v2 = MagicMock(return_value={})

    result = s3_manager.list_packs()

    assert result == []


def test_delete_pack_success(s3_manager: S3Manager) -> None:
    """Test successful pack deletion."""
    s3_manager.s3_client.delete_object = MagicMock()

    result = s3_manager.delete_pack("packs/test.tar.gz")

    assert result is True
    s3_manager.s3_client.delete_object.assert_called_once()


def test_delete_bucket_recursive_bucket_not_found(s3_manager: S3Manager) -> None:
    """Test delete_bucket_recursive when bucket doesn't exist."""
    from botocore.exceptions import ClientError

    s3_manager.s3_client.head_bucket = MagicMock(
        side_effect=ClientError({"Error": {"Code": "404"}}, "head_bucket")
    )

    result = s3_manager.delete_bucket_recursive()

    assert result is True


def test_delete_bucket_recursive_non_versioned(s3_manager: S3Manager) -> None:
    """Test delete_bucket_recursive with non-versioned bucket."""
    s3_manager.s3_client.head_bucket = MagicMock()
    s3_manager.s3_client.get_bucket_versioning = MagicMock(return_value={})
    s3_manager.s3_client.get_paginator = MagicMock(
        return_value=MagicMock(
            paginate=MagicMock(
                return_value=[{"Contents": [{"Key": "file1.txt"}, {"Key": "file2.txt"}]}]
            )
        )
    )
    s3_manager.s3_client.delete_objects = MagicMock(
        return_value={"Deleted": [{"Key": "file1.txt"}, {"Key": "file2.txt"}]}
    )
    s3_manager.s3_client.delete_bucket = MagicMock()

    result = s3_manager.delete_bucket_recursive()

    assert result is True
    s3_manager.s3_client.delete_objects.assert_called_once()
    s3_manager.s3_client.delete_bucket.assert_called_once()


def test_delete_bucket_recursive_versioned(s3_manager: S3Manager) -> None:
    """Test delete_bucket_recursive with versioned bucket."""
    s3_manager.s3_client.head_bucket = MagicMock()
    s3_manager.s3_client.get_bucket_versioning = MagicMock(return_value={"Status": "Enabled"})
    s3_manager.s3_client.get_paginator = MagicMock(
        return_value=MagicMock(
            paginate=MagicMock(
                return_value=[
                    {
                        "Versions": [
                            {"Key": "file1.txt", "VersionId": "v1"},
                            {"Key": "file1.txt", "VersionId": "v2"},
                        ],
                        "DeleteMarkers": [{"Key": "file2.txt", "VersionId": "dm1"}],
                    }
                ]
            )
        )
    )
    s3_manager.s3_client.delete_objects = MagicMock(
        return_value={"Deleted": [{"Key": "file1.txt"}, {"Key": "file1.txt"}, {"Key": "file2.txt"}]}
    )
    s3_manager.s3_client.delete_bucket = MagicMock()

    result = s3_manager.delete_bucket_recursive()

    assert result is True
    s3_manager.s3_client.delete_objects.assert_called_once()
    s3_manager.s3_client.delete_bucket.assert_called_once()


def test_delete_bucket_recursive_dry_run(s3_manager: S3Manager) -> None:
    """Test delete_bucket_recursive in dry-run mode."""
    s3_manager.s3_client.head_bucket = MagicMock()
    s3_manager.s3_client.get_bucket_versioning = MagicMock(return_value={})
    s3_manager.s3_client.get_paginator = MagicMock(
        return_value=MagicMock(
            paginate=MagicMock(return_value=[{"Contents": [{"Key": "file1.txt"}]}])
        )
    )
    s3_manager.s3_client.delete_objects = MagicMock()
    s3_manager.s3_client.delete_bucket = MagicMock()

    result = s3_manager.delete_bucket_recursive(dry_run=True)

    assert result is True
    # Ensure no actual deletions happened in dry-run mode
    s3_manager.s3_client.delete_objects.assert_not_called()
    s3_manager.s3_client.delete_bucket.assert_not_called()


def test_upload_bytes_success(s3_manager: S3Manager) -> None:
    """Test successful bytes upload."""
    test_data = b"test bootstrap script content"
    s3_manager.s3_client.put_object = MagicMock()

    result = s3_manager.upload_bytes("bootstrap/test.sh", test_data)

    assert result is True
    s3_manager.s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket", Key="bootstrap/test.sh", Body=test_data
    )


def test_upload_bytes_failure(s3_manager: S3Manager) -> None:
    """Test bytes upload failure."""
    from botocore.exceptions import ClientError

    test_data = b"test data"
    s3_manager.s3_client.put_object = MagicMock(
        side_effect=ClientError({"Error": {"Code": "AccessDenied"}}, "put_object")
    )

    result = s3_manager.upload_bytes("bootstrap/test.sh", test_data)

    assert result is False


def test_generate_presigned_url_success(s3_manager: S3Manager) -> None:
    """Test successful presigned URL generation."""
    expected_url = "https://test-bucket.s3.amazonaws.com/bootstrap/test.sh?X-Amz-Signature=..."
    s3_manager.s3_client.generate_presigned_url = MagicMock(return_value=expected_url)

    result = s3_manager.generate_presigned_url("bootstrap/test.sh", expiration_secs=3600)

    assert result == expected_url
    s3_manager.s3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "bootstrap/test.sh"},
        ExpiresIn=3600,
    )


def test_generate_presigned_url_default_expiration(s3_manager: S3Manager) -> None:
    """Test presigned URL generation with default expiration."""
    expected_url = "https://test-bucket.s3.amazonaws.com/bootstrap/test.sh?X-Amz-Signature=..."
    s3_manager.s3_client.generate_presigned_url = MagicMock(return_value=expected_url)

    result = s3_manager.generate_presigned_url("bootstrap/test.sh")

    assert result == expected_url
    call_args = s3_manager.s3_client.generate_presigned_url.call_args
    assert call_args[1]["ExpiresIn"] == 3600  # Default 1 hour


def test_generate_presigned_url_failure(s3_manager: S3Manager) -> None:
    """Test presigned URL generation failure."""
    from botocore.exceptions import ClientError

    s3_manager.s3_client.generate_presigned_url = MagicMock(
        side_effect=ClientError({"Error": {"Code": "NoSuchKey"}}, "generate_presigned_url")
    )

    result = s3_manager.generate_presigned_url("bootstrap/nonexistent.sh")

    assert result is None
