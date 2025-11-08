"""Unit tests for config module."""

from ac_server_manager.config import (
    ServerConfig,
    AC_SERVER_HTTP_PORT,
    AC_SERVER_TCP_PORT,
    AC_SERVER_UDP_PORT,
)


def test_server_config_defaults() -> None:
    """Test ServerConfig default values."""
    config = ServerConfig()

    assert config.aws_region == "us-east-1"
    assert config.instance_type == "t3.small"
    assert config.key_name is None
    assert config.security_group_name == "ac-server-sg"
    assert config.s3_bucket_name == "ac-server-packs"
    assert config.pack_file_key is None
    assert config.auto_create_iam is False
    assert config.iam_role_name is None
    assert config.iam_instance_profile_name is None
    assert config.iam_instance_profile is None
    assert config.server_name == "AC Server"
    assert config.max_players == 8
    assert config.instance_name == "ac-server-instance"


def test_server_config_custom_values() -> None:
    """Test ServerConfig with custom values."""
    config = ServerConfig(
        aws_region="us-west-2",
        instance_type="t3.medium",
        key_name="my-key",
        s3_bucket_name="my-bucket",
        max_players=16,
    )

    assert config.aws_region == "us-west-2"
    assert config.instance_type == "t3.medium"
    assert config.key_name == "my-key"
    assert config.s3_bucket_name == "my-bucket"
    assert config.max_players == 16


def test_server_config_from_dict() -> None:
    """Test ServerConfig.from_dict method."""
    config_dict = {
        "aws_region": "eu-west-1",
        "instance_type": "t3.large",
        "key_name": "test-key",
        "max_players": 12,
        "auto_create_iam": True,
        "iam_role_name": "custom-role",
        "iam_instance_profile_name": "custom-profile",
        "extra_field": "should be ignored",
    }

    config = ServerConfig.from_dict(config_dict)

    assert config.aws_region == "eu-west-1"
    assert config.instance_type == "t3.large"
    assert config.key_name == "test-key"
    assert config.max_players == 12
    assert config.auto_create_iam is True
    assert config.iam_role_name == "custom-role"
    assert config.iam_instance_profile_name == "custom-profile"
    assert not hasattr(config, "extra_field")


def test_ac_server_ports() -> None:
    """Test AC server port constants."""
    assert AC_SERVER_HTTP_PORT == 8081
    assert AC_SERVER_TCP_PORT == 9600
    assert AC_SERVER_UDP_PORT == 9600
