"""Configuration management for AC Server Manager."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
    """Configuration for Assetto Corsa server deployment."""

    # AWS Configuration
    aws_region: str = "us-east-1"
    instance_type: str = "t3.small"  # Suitable for 2-8 players, cost-effective
    key_name: Optional[str] = None
    security_group_name: str = "ac-server-sg"

    # S3 Configuration
    s3_bucket_name: str = "ac-server-packs"
    pack_file_key: Optional[str] = None

    # IAM Configuration
    auto_create_iam: bool = False  # Automatic IAM role/profile creation (default off)
    iam_role_name: Optional[str] = None
    iam_instance_profile_name: Optional[str] = None
    iam_instance_profile: Optional[str] = None  # Existing profile to use (takes precedence)

    # Server Configuration
    server_name: str = "AC Server"
    max_players: int = 8

    # AC Server Wrapper Configuration (optional)
    enable_wrapper: bool = True  # Enable ac-server-wrapper for CM content downloads
    wrapper_port: int = 8082  # Port for wrapper (must be different from AC HTTP port 8081)

    # AssettoServer Configuration
    use_assettoserver: bool = False  # Use AssettoServer instead of default AC server
    assettoserver_version: str = "v0.0.54"  # AssettoServer Docker image version

    # Instance tags
    instance_name: str = "ac-server-instance"

    @classmethod
    def from_dict(cls, config_dict: dict) -> "ServerConfig":
        """Create ServerConfig from dictionary.

        Args:
            config_dict: Dictionary containing configuration values

        Returns:
            ServerConfig instance
        """
        return cls(**{k: v for k, v in config_dict.items() if k in cls.__annotations__})


# Default ports for Assetto Corsa
AC_SERVER_HTTP_PORT = 8081
AC_SERVER_TCP_PORT = 9600
AC_SERVER_UDP_PORT = 9600
