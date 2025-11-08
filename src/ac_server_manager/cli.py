"""Command-line interface for AC Server Manager."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from .config import ServerConfig
from .deployer import Deployer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
def main() -> None:
    """AC Server Manager - Automated deployment for Assetto Corsa servers on AWS.

    This tool automates the deployment of Assetto Corsa dedicated servers on AWS
    using EC2 and S3. It handles the complete lifecycle from pack upload to server
    deployment and management.
    """
    pass


@main.command()
@click.argument("pack_file", type=click.Path(exists=True, path_type=Path))
@click.option("--region", default="us-east-1", help="AWS region (default: us-east-1)")
@click.option("--instance-type", default="t3.small", help="EC2 instance type (default: t3.small)")
@click.option("--bucket", default="ac-server-packs", help="S3 bucket name")
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--key-name", help="EC2 key pair name for SSH access")
@click.option("--iam-instance-profile", help="Existing IAM instance profile name/ARN to use")
@click.option("--create-iam/--no-create-iam", default=False, help="Automatically create IAM role and instance profile for S3 access (default: off)")
@click.option("--iam-role-name", help="IAM role name to create (used with --create-iam)")
@click.option("--iam-instance-profile-name", help="IAM instance profile name to create (used with --create-iam)")
def deploy(
    pack_file: Path,
    region: str,
    instance_type: str,
    bucket: str,
    instance_name: str,
    key_name: Optional[str],
    iam_instance_profile: Optional[str],
    create_iam: bool,
    iam_role_name: Optional[str],
    iam_instance_profile_name: Optional[str],
) -> None:
    """Deploy AC server from a Content Manager pack file.

    PACK_FILE: Path to the server pack .tar.gz file exported from Content Manager

    Example:
        ac-server-manager deploy my-server-pack.tar.gz
        ac-server-manager deploy my-server-pack.tar.gz --region us-west-2 --key-name my-key
        ac-server-manager deploy my-server-pack.tar.gz --create-iam
        ac-server-manager deploy my-server-pack.tar.gz --iam-instance-profile my-profile
    """
    config = ServerConfig(
        aws_region=region,
        instance_type=instance_type,
        s3_bucket_name=bucket,
        instance_name=instance_name,
        key_name=key_name,
        iam_instance_profile=iam_instance_profile,
        auto_create_iam=create_iam,
        iam_role_name=iam_role_name,
        iam_instance_profile_name=iam_instance_profile_name,
    )

    deployer = Deployer(config)

    click.echo(f"Deploying AC server from {pack_file.name}...")
    instance_id = deployer.deploy(pack_file)

    if instance_id:
        click.echo(click.style("✓ Deployment successful!", fg="green", bold=True))
        click.echo(f"\nInstance ID: {instance_id}")
        click.echo("\nThe server is initializing and will be available in a few minutes.")
        click.echo("Use 'ac-server-manager status' to check the instance details.")
    else:
        click.echo(click.style("✗ Deployment failed", fg="red", bold=True))
        sys.exit(1)


@main.command()
@click.option("--instance-id", help="Instance ID to stop (if not provided, uses instance name)")
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--region", default="us-east-1", help="AWS region")
def stop(instance_id: Optional[str], instance_name: str, region: str) -> None:
    """Stop a running AC server instance.

    Example:
        ac-server-manager stop
        ac-server-manager stop --instance-id i-1234567890abcdef0
    """
    config = ServerConfig(aws_region=region, instance_name=instance_name)
    deployer = Deployer(config)

    click.echo("Stopping AC server instance...")
    if deployer.stop(instance_id):
        click.echo(click.style("✓ Instance stopped", fg="green", bold=True))
    else:
        click.echo(click.style("✗ Failed to stop instance", fg="red", bold=True))
        sys.exit(1)


@main.command()
@click.option("--instance-id", help="Instance ID to start (if not provided, uses instance name)")
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--region", default="us-east-1", help="AWS region")
def start(instance_id: Optional[str], instance_name: str, region: str) -> None:
    """Start a stopped AC server instance.

    Example:
        ac-server-manager start
        ac-server-manager start --instance-id i-1234567890abcdef0
    """
    config = ServerConfig(aws_region=region, instance_name=instance_name)
    deployer = Deployer(config)

    click.echo("Starting AC server instance...")
    if deployer.start(instance_id):
        click.echo(click.style("✓ Instance started", fg="green", bold=True))
    else:
        click.echo(click.style("✗ Failed to start instance", fg="red", bold=True))
        sys.exit(1)


@main.command()
@click.option(
    "--instance-id", help="Instance ID to terminate (if not provided, uses instance name)"
)
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--region", default="us-east-1", help="AWS region")
@click.confirmation_option(prompt="Are you sure you want to terminate the instance?")
def terminate(instance_id: Optional[str], instance_name: str, region: str) -> None:
    """Terminate an AC server instance.

    WARNING: This permanently terminates the instance. All data on the instance will be lost.

    Example:
        ac-server-manager terminate
        ac-server-manager terminate --instance-id i-1234567890abcdef0
    """
    config = ServerConfig(aws_region=region, instance_name=instance_name)
    deployer = Deployer(config)

    click.echo("Terminating AC server instance...")
    if deployer.terminate(instance_id):
        click.echo(click.style("✓ Instance terminated", fg="green", bold=True))
    else:
        click.echo(click.style("✗ Failed to terminate instance", fg="red", bold=True))
        sys.exit(1)


@main.command()
@click.argument("pack_file", type=click.Path(exists=True, path_type=Path))
@click.option("--instance-id", help="Instance ID to replace (if not provided, uses instance name)")
@click.option("--region", default="us-east-1", help="AWS region")
@click.option("--instance-type", default="t3.small", help="EC2 instance type")
@click.option("--bucket", default="ac-server-packs", help="S3 bucket name")
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--key-name", help="EC2 key pair name for SSH access")
@click.option("--iam-instance-profile", help="Existing IAM instance profile name/ARN to use")
@click.option("--create-iam/--no-create-iam", default=False, help="Automatically create IAM role and instance profile for S3 access (default: off)")
@click.option("--iam-role-name", help="IAM role name to create (used with --create-iam)")
@click.option("--iam-instance-profile-name", help="IAM instance profile name to create (used with --create-iam)")
def redeploy(
    pack_file: Path,
    instance_id: Optional[str],
    region: str,
    instance_type: str,
    bucket: str,
    instance_name: str,
    key_name: Optional[str],
    iam_instance_profile: Optional[str],
    create_iam: bool,
    iam_role_name: Optional[str],
    iam_instance_profile_name: Optional[str],
) -> None:
    """Terminate existing instance and redeploy with new pack.

    PACK_FILE: Path to the new server pack .tar.gz file

    Example:
        ac-server-manager redeploy new-server-pack.tar.gz
        ac-server-manager redeploy new-server-pack.tar.gz --create-iam
    """
    config = ServerConfig(
        aws_region=region,
        instance_type=instance_type,
        s3_bucket_name=bucket,
        instance_name=instance_name,
        key_name=key_name,
        iam_instance_profile=iam_instance_profile,
        auto_create_iam=create_iam,
        iam_role_name=iam_role_name,
        iam_instance_profile_name=iam_instance_profile_name,
    )

    deployer = Deployer(config)

    click.echo(f"Redeploying AC server with {pack_file.name}...")
    new_instance_id = deployer.redeploy(pack_file, instance_id)

    if new_instance_id:
        click.echo(click.style("✓ Redeployment successful!", fg="green", bold=True))
        click.echo(f"\nNew Instance ID: {new_instance_id}")
    else:
        click.echo(click.style("✗ Redeployment failed", fg="red", bold=True))
        sys.exit(1)


@main.command()
@click.option("--instance-id", help="Instance ID to check (if not provided, uses instance name)")
@click.option("--instance-name", default="ac-server-instance", help="Instance name tag")
@click.option("--region", default="us-east-1", help="AWS region")
def status(instance_id: Optional[str], instance_name: str, region: str) -> None:
    """Check the status of an AC server instance.

    Shows instance state, connection information, and acstuff.ru link for joining.

    Example:
        ac-server-manager status
        ac-server-manager status --instance-id i-1234567890abcdef0
    """
    from .config import AC_SERVER_TCP_PORT

    config = ServerConfig(aws_region=region, instance_name=instance_name)
    deployer = Deployer(config)

    click.echo("Checking AC server status...")
    details = deployer.get_status(instance_id)

    if not details:
        click.echo(click.style("✗ No instance found", fg="red", bold=True))
        sys.exit(1)

    # Display instance information
    click.echo(click.style("\n✓ Instance found", fg="green", bold=True))
    click.echo(f"\nInstance ID: {details['instance_id']}")
    click.echo(f"Name: {details.get('name', 'N/A')}")
    click.echo(
        f"State: {click.style(details['state'], fg='green' if details['state'] == 'running' else 'yellow', bold=True)}"
    )
    click.echo(f"Instance Type: {details['instance_type']}")
    click.echo(f"Launch Time: {details['launch_time']}")

    # Display connection information if instance is running
    if details["state"] == "running" and details.get("public_ip"):
        public_ip = details["public_ip"]
        click.echo(f"\n{click.style('Connection Information:', fg='cyan', bold=True)}")
        click.echo(f"Public IP: {public_ip}")
        click.echo(f"Game Port: {AC_SERVER_TCP_PORT} (UDP/TCP)")
        click.echo(f"Direct Connect: {public_ip}:{AC_SERVER_TCP_PORT}")

        # Generate acstuff.ru link
        acstuff_url = f"https://acstuff.ru/s/q:race@{public_ip}:{AC_SERVER_TCP_PORT}"
        click.echo(f"\n{click.style('Join Server:', fg='cyan', bold=True)}")
        click.echo(f"acstuff.ru link: {acstuff_url}")
        click.echo("\nOpen this link in your browser to join the server via Content Manager")
    elif details["state"] == "running":
        click.echo(
            click.style("\n⚠ Instance is running but no public IP assigned yet", fg="yellow")
        )
        click.echo("Wait a few moments and check status again")
    else:
        click.echo(click.style(f"\n⚠ Instance is {details['state']}", fg="yellow"))
        click.echo("Start the instance with: ac-server-manager start")


if __name__ == "__main__":
    main()
