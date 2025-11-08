"""Command-line interface for AC Server Manager."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from . import __version__
from .config import AWSConfig, DeploymentConfig, ServerConfig
from .deployer import ACServerDeployer

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """AC Server Manager - Automate Assetto Corsa server deployment on AWS.
    
    This tool helps you deploy and manage Assetto Corsa dedicated servers on AWS EC2.
    
    Usage with UV:
    
        # Install dependencies
        uv pip install -e .
        
        # Deploy a server
        ac-deploy deploy /path/to/server-pack.zip
        
        # List servers
        ac-deploy list
        
        # Stop a server
        ac-deploy stop i-1234567890abcdef0
    """
    pass


@main.command()
@click.argument("pack_path", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", help="Custom name for the instance")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
@click.option("--bucket", default="ac-server-packs", help="S3 bucket name")
@click.option("--instance-type", default="t3.small", help="EC2 instance type")
def deploy(
    pack_path: Path,
    name: Optional[str],
    region: str,
    profile: Optional[str],
    bucket: str,
    instance_type: str
) -> None:
    """Deploy a new Assetto Corsa server.
    
    PACK_PATH: Path to the server pack ZIP file created from Content Manager.
    
    The pack should include:
    - acServer.exe
    - cfg/ directory with server configuration
    - content/ directory with tracks and cars
    - system/ directory
    """
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile),
            server=ServerConfig(instance_type=instance_type),
            s3_bucket=bucket
        )
        
        deployer = ACServerDeployer(config)
        
        click.echo(f"🚀 Deploying AC server from {pack_path}...")
        result = deployer.deploy(pack_path, name)
        
        click.echo("\n✅ Deployment successful!")
        click.echo(f"Instance ID: {result['instance_id']}")
        click.echo(f"Instance Name: {result['instance_name']}")
        click.echo(f"Public IP: {result['public_ip']}")
        
        if "acstuff_link" in result:
            click.echo(f"\n🎮 Server Connection Link:")
            click.echo(f"   {result['acstuff_link']}")
            click.echo("\nShare this link with players to connect via Content Manager!")
        elif "server_info" in result:
            click.echo("\n📊 Server Info:")
            for key, value in result["server_info"].items():
                click.echo(f"   {key}: {value}")
        else:
            click.echo("\n⚠️  Server info not available yet. Use 'ac-deploy status <instance-id>' to check later.")
        
        click.echo(f"\nPorts:")
        click.echo(f"   HTTP: {config.server.http_port}")
        click.echo(f"   TCP: {config.server.tcp_port}")
        click.echo(f"   UDP: {config.server.udp_port}")
        
    except Exception as e:
        click.echo(f"❌ Deployment failed: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
def list(region: str, profile: Optional[str]) -> None:
    """List all AC server instances."""
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        servers = deployer.list_servers()
        
        if not servers:
            click.echo("No AC servers found.")
            return
        
        click.echo(f"\n📋 Found {len(servers)} AC server(s):\n")
        
        for server in servers:
            click.echo(f"Instance ID: {server['instance_id']}")
            click.echo(f"  State: {server['state']}")
            click.echo(f"  Type: {server['instance_type']}")
            click.echo(f"  Public IP: {server.get('public_ip', 'N/A')}")
            click.echo(f"  Launch Time: {server['launch_time']}")
            
            if "server_info" in server and server["server_info"]:
                click.echo("  Server Info:")
                for key, value in server["server_info"].items():
                    click.echo(f"    {key}: {value}")
            
            click.echo()
        
    except Exception as e:
        click.echo(f"❌ Failed to list servers: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("instance_id")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
def status(instance_id: str, region: str, profile: Optional[str]) -> None:
    """Get detailed status of a server instance."""
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        info = deployer.get_server_status(instance_id)
        
        click.echo(f"\n📊 Server Status for {instance_id}:\n")
        click.echo(f"State: {info['state']}")
        click.echo(f"Type: {info['instance_type']}")
        click.echo(f"Public IP: {info.get('public_ip', 'N/A')}")
        click.echo(f"Private IP: {info.get('private_ip', 'N/A')}")
        click.echo(f"Launch Time: {info['launch_time']}")
        
        if "server_info" in info and info["server_info"]:
            click.echo("\nServer Information:")
            for key, value in info["server_info"].items():
                click.echo(f"  {key}: {value}")
                
                if key == "AC_SERVER_LINK":
                    click.echo(f"\n🎮 Connect via: {value}")
        
    except Exception as e:
        click.echo(f"❌ Failed to get status: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("instance_id")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
def stop(instance_id: str, region: str, profile: Optional[str]) -> None:
    """Stop a running server instance."""
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        
        if deployer.stop_server(instance_id):
            click.echo(f"✅ Server {instance_id} is stopping...")
        else:
            click.echo(f"❌ Failed to stop server {instance_id}", err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"❌ Failed to stop server: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("instance_id")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
def start(instance_id: str, region: str, profile: Optional[str]) -> None:
    """Start a stopped server instance."""
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        
        if deployer.start_server(instance_id):
            click.echo(f"✅ Server {instance_id} is starting...")
        else:
            click.echo(f"❌ Failed to start server {instance_id}", err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"❌ Failed to start server: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("instance_id")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
@click.confirmation_option(prompt="Are you sure you want to terminate this instance?")
def terminate(instance_id: str, region: str, profile: Optional[str]) -> None:
    """Terminate a server instance (permanent deletion)."""
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        
        if deployer.terminate_server(instance_id):
            click.echo(f"✅ Server {instance_id} is terminating...")
        else:
            click.echo(f"❌ Failed to terminate server {instance_id}", err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"❌ Failed to terminate server: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("instance_id")
@click.argument("pack_path", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", help="Custom name for the new instance")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--profile", help="AWS profile name")
def redeploy(
    instance_id: str,
    pack_path: Path,
    name: Optional[str],
    region: str,
    profile: Optional[str]
) -> None:
    """Redeploy a server with a new pack file.
    
    This will terminate the old instance and create a new one with the updated pack.
    """
    try:
        config = DeploymentConfig(
            aws=AWSConfig(region=region, profile=profile)
        )
        
        deployer = ACServerDeployer(config)
        
        click.echo(f"🔄 Redeploying server (old: {instance_id})...")
        result = deployer.redeploy_server(instance_id, pack_path, name)
        
        click.echo("\n✅ Redeployment successful!")
        click.echo(f"New Instance ID: {result['instance_id']}")
        click.echo(f"Instance Name: {result['instance_name']}")
        click.echo(f"Public IP: {result['public_ip']}")
        
        if "acstuff_link" in result:
            click.echo(f"\n🎮 Server Connection Link:")
            click.echo(f"   {result['acstuff_link']}")
        
    except Exception as e:
        click.echo(f"❌ Redeployment failed: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
