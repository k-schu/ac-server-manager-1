"""Configuration models for AC Server Manager."""

from typing import Optional
from pydantic import BaseModel, Field


class AWSConfig(BaseModel):
    """AWS configuration settings."""

    region: str = Field(default="us-east-1", description="AWS region")
    profile: Optional[str] = Field(default=None, description="AWS profile name")


class ServerConfig(BaseModel):
    """Assetto Corsa server configuration."""

    instance_type: str = Field(
        default="t3.small",
        description="EC2 instance type (t3.small for 2-8 players)"
    )
    ami_id: Optional[str] = Field(
        default=None,
        description="Windows AMI ID (auto-detected if not provided)"
    )
    key_name: Optional[str] = Field(
        default=None,
        description="EC2 key pair name for SSH access"
    )
    security_group_name: str = Field(
        default="ac-server-sg",
        description="Security group name"
    )
    
    # Assetto Corsa specific ports
    http_port: int = Field(default=8081, description="HTTP port")
    tcp_port: int = Field(default=9600, description="TCP port")
    udp_port: int = Field(default=9600, description="UDP port")


class DeploymentConfig(BaseModel):
    """Deployment configuration combining AWS and server settings."""

    aws: AWSConfig = Field(default_factory=AWSConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    s3_bucket: str = Field(
        default="ac-server-packs",
        description="S3 bucket for server pack files"
    )
    instance_name_prefix: str = Field(
        default="ac-server",
        description="Prefix for EC2 instance names"
    )
