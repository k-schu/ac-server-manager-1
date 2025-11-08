"""Tests for configuration models."""

import pytest
from ac_server_manager.config import AWSConfig, ServerConfig, DeploymentConfig


def test_aws_config_defaults():
    """Test AWS config with default values."""
    config = AWSConfig()
    
    assert config.region == "us-east-1"
    assert config.profile is None


def test_aws_config_custom():
    """Test AWS config with custom values."""
    config = AWSConfig(region="eu-west-1", profile="my-profile")
    
    assert config.region == "eu-west-1"
    assert config.profile == "my-profile"


def test_server_config_defaults():
    """Test server config with default values."""
    config = ServerConfig()
    
    assert config.instance_type == "t3.small"
    assert config.http_port == 8081
    assert config.tcp_port == 9600
    assert config.udp_port == 9600
    assert config.security_group_name == "ac-server-sg"


def test_server_config_custom():
    """Test server config with custom values."""
    config = ServerConfig(
        instance_type="t3.medium",
        http_port=8082,
        tcp_port=9601
    )
    
    assert config.instance_type == "t3.medium"
    assert config.http_port == 8082
    assert config.tcp_port == 9601


def test_deployment_config_defaults():
    """Test deployment config with default values."""
    config = DeploymentConfig()
    
    assert config.aws.region == "us-east-1"
    assert config.server.instance_type == "t3.small"
    assert config.s3_bucket == "ac-server-packs"
    assert config.instance_name_prefix == "ac-server"


def test_deployment_config_custom():
    """Test deployment config with custom values."""
    config = DeploymentConfig(
        aws=AWSConfig(region="us-west-2"),
        server=ServerConfig(instance_type="t3.medium"),
        s3_bucket="my-bucket",
        instance_name_prefix="my-server"
    )
    
    assert config.aws.region == "us-west-2"
    assert config.server.instance_type == "t3.medium"
    assert config.s3_bucket == "my-bucket"
    assert config.instance_name_prefix == "my-server"
