"""Tests for S3Manager."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from ac_server_manager.s3 import S3Manager


@pytest.fixture
def s3_manager():
    """Create an S3Manager instance with mocked boto3 client."""
    with patch("ac_server_manager.s3.boto3.Session") as mock_session:
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        manager = S3Manager("test-bucket", "us-east-1")
        manager.s3_client = mock_client
        yield manager


def test_create_bucket_already_exists(s3_manager):
    """Test creating bucket when it already exists."""
    s3_manager.s3_client.head_bucket.return_value = {}
    
    result = s3_manager.create_bucket()
    
    assert result is True
    s3_manager.s3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")


def test_create_bucket_new(s3_manager):
    """Test creating a new bucket."""
    error_response = {"Error": {"Code": "404"}}
    s3_manager.s3_client.head_bucket.side_effect = ClientError(error_response, "head_bucket")
    s3_manager.s3_client.create_bucket.return_value = {}
    
    result = s3_manager.create_bucket()
    
    assert result is True
    s3_manager.s3_client.create_bucket.assert_called_once()


def test_upload_pack(s3_manager, tmp_path):
    """Test uploading a pack file."""
    pack_file = tmp_path / "test-pack.zip"
    pack_file.write_text("test content")
    
    s3_manager.s3_client.upload_file.return_value = None
    
    result = s3_manager.upload_pack(pack_file)
    
    assert result == "test-pack.zip"
    s3_manager.s3_client.upload_file.assert_called_once()


def test_upload_pack_file_not_found(s3_manager):
    """Test uploading non-existent pack file."""
    with pytest.raises(FileNotFoundError):
        s3_manager.upload_pack(Path("/nonexistent/file.zip"))


def test_get_pack_url(s3_manager):
    """Test generating presigned URL."""
    s3_manager.s3_client.generate_presigned_url.return_value = "https://example.com/pack.zip"
    
    result = s3_manager.get_pack_url("test-pack.zip")
    
    assert result == "https://example.com/pack.zip"
    s3_manager.s3_client.generate_presigned_url.assert_called_once()


def test_delete_pack(s3_manager):
    """Test deleting a pack."""
    s3_manager.s3_client.delete_object.return_value = {}
    
    result = s3_manager.delete_pack("test-pack.zip")
    
    assert result is True
    s3_manager.s3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="test-pack.zip"
    )


def test_list_packs(s3_manager):
    """Test listing packs."""
    s3_manager.s3_client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "pack1.zip"},
            {"Key": "pack2.zip"}
        ]
    }
    
    result = s3_manager.list_packs()
    
    assert result == ["pack1.zip", "pack2.zip"]


def test_list_packs_empty(s3_manager):
    """Test listing packs when bucket is empty."""
    s3_manager.s3_client.list_objects_v2.return_value = {}
    
    result = s3_manager.list_packs()
    
    assert result == []
