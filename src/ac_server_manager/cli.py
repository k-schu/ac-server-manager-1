"""Command-line interface for AC Server Manager."""

import logging
import socket
import subprocess
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


def check_tcp_port(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a TCP port is open and accepting connections.

    Args:
        host: Host to check
        port: Port to check
        timeout: Connection timeout in seconds

    Returns:
        True if port is open, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"TCP port check failed for {host}:{port} - {e}")
        return False


def check_udp_port(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a UDP port is reachable.

    Note: UDP is connectionless, so this check sends a packet and waits for a response.
    A lack of ICMP port unreachable error is considered success.

    Args:
        host: Host to check
        port: Port to check
        timeout: Timeout in seconds

    Returns:
        True if port appears to be open, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # Send a test packet
        sock.sendto(b"\x00", (host, port))
        # Try to receive - if we get ICMP port unreachable, port is closed
        try:
            sock.recvfrom(1024)
            sock.close()
            return True
        except socket.timeout:
            # Timeout means no ICMP error, which suggests port might be open
            sock.close()
            return True
        except Exception:
            sock.close()
            return False
    except Exception as e:
        logger.debug(f"UDP port check failed for {host}:{port} - {e}")
        return False


def check_host_reachable(host: str, timeout: int = 5) -> bool:
    """Check if host is reachable using ping.

    Args:
        host: Host to check
        timeout: Timeout in seconds

    Returns:
        True if host is reachable, False otherwise
    """
    try:
        # Use ping command (works on Linux/Mac/Windows)
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 1,
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug(f"Ping check failed for {host} - {e}")
        return False


def check_url_accessible(url: str, timeout: int = 10) -> tuple[bool, Optional[str]]:
    """Check if a URL is accessible using curl.

    Args:
        url: URL to check
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, error_message)
    """
    try:
        result = subprocess.run(
            [
                "curl",
                "-L",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                str(timeout),
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 1,
            text=True,
        )
        http_code = result.stdout.strip()

        # Consider 2xx and 3xx as success
        if http_code.startswith("2") or http_code.startswith("3"):
            return True, None
        else:
            return False, f"HTTP {http_code}"
    except subprocess.TimeoutExpired:
        return False, "Connection timeout"
    except FileNotFoundError:
        # curl not available, skip this check
        logger.debug("curl not available, skipping URL check")
        return True, "Skipped (curl not available)"
    except Exception as e:
        return False, str(e)


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
@click.option(
    "--create-iam/--no-create-iam",
    default=False,
    help="Automatically create IAM role and instance profile for S3 access (default: off)",
)
@click.option("--iam-role-name", help="IAM role name to create (used with --create-iam)")
@click.option(
    "--iam-instance-profile-name",
    help="IAM instance profile name to create (used with --create-iam)",
)
@click.option(
    "--enable-wrapper/--no-enable-wrapper",
    default=True,
    help="Enable ac-server-wrapper for CM content downloads (default: on)",
)
@click.option(
    "--wrapper-port",
    type=int,
    default=8082,
    help="Port for ac-server-wrapper (default: 8082, must differ from AC HTTP port 8081)",
)
@click.option(
    "--use-assettoserver/--no-use-assettoserver",
    default=False,
    help="Use AssettoServer instead of default AC server (default: off)",
)
@click.option(
    "--assettoserver-version",
    default="v0.0.54",
    help="AssettoServer Docker image version (default: v0.0.54)",
)
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
    enable_wrapper: bool,
    wrapper_port: int,
    use_assettoserver: bool,
    assettoserver_version: str,
) -> None:
    """Deploy AC server from a Content Manager pack file.

    PACK_FILE: Path to the server pack .tar.gz file exported from Content Manager

    Example:
        ac-server-manager deploy my-server-pack.tar.gz
        ac-server-manager deploy my-server-pack.tar.gz --region us-west-2 --key-name my-key
        ac-server-manager deploy my-server-pack.tar.gz --create-iam
        ac-server-manager deploy my-server-pack.tar.gz --iam-instance-profile my-profile
        ac-server-manager deploy my-server-pack.tar.gz --use-assettoserver
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
        enable_wrapper=enable_wrapper,
        wrapper_port=wrapper_port,
        use_assettoserver=use_assettoserver,
        assettoserver_version=assettoserver_version,
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
@click.option("--instance-id", help="Explicitly specify EC2 instance ID to terminate")
@click.option(
    "--instance-name", default="ac-server-instance", help="Instance name tag for discovery"
)
@click.option("--s3-bucket", help="Explicitly specify S3 bucket name to delete")
@click.option("--skip-bucket", is_flag=True, help="Only terminate instance, don't delete S3 bucket")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without performing deletions"
)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--region", default="us-east-1", help="AWS region")
def terminate_all(
    instance_id: Optional[str],
    instance_name: str,
    s3_bucket: Optional[str],
    skip_bucket: bool,
    dry_run: bool,
    force: bool,
    region: str,
) -> None:
    """Terminate EC2 instance and delete associated S3 bucket.

    This command performs complete teardown of AC server infrastructure by:
    1. Terminating the EC2 instance (if found)
    2. Recursively deleting the S3 bucket and all objects/versions (unless --skip-bucket)

    By default, requires interactive confirmation where you must type TERMINATE (case-sensitive).
    Use --force to skip confirmation, --dry-run to preview actions without deleting.

    Examples:
        ac-server-manager terminate-all
        ac-server-manager terminate-all --force
        ac-server-manager terminate-all --dry-run
        ac-server-manager terminate-all --instance-id i-1234567890abcdef0 --s3-bucket my-bucket
        ac-server-manager terminate-all --skip-bucket
    """
    from .ec2_manager import EC2Manager
    from .s3_manager import S3Manager

    # Safety confirmation unless --force or --dry-run
    if not force and not dry_run:
        click.echo(
            click.style(
                "\n⚠️  WARNING: This will permanently delete your AC server infrastructure!",
                fg="red",
                bold=True,
            )
        )
        click.echo("\nThis action will:")
        click.echo("  • Terminate the EC2 instance")
        if not skip_bucket:
            click.echo("  • Delete the S3 bucket and ALL its contents (including all versions)")
        click.echo("\nThis operation CANNOT be undone!\n")

        confirmation = click.prompt(
            click.style('Type "TERMINATE" (case-sensitive) to confirm', fg="yellow", bold=True),
            type=str,
        )

        if confirmation != "TERMINATE":
            click.echo(click.style("✗ Confirmation failed. Aborting.", fg="red"))
            sys.exit(1)

        click.echo()

    # Initialize managers
    ec2_manager = EC2Manager(region)

    # Discover or use provided instance ID
    instance_to_terminate: Optional[str] = None
    if instance_id:
        instance_to_terminate = instance_id
        logger.info(f"Using explicitly provided instance ID: {instance_id}")
    else:
        # Try to discover instance by name tag
        logger.info(f"Discovering instances with name: {instance_name}")
        instances = ec2_manager.find_instances_by_name(instance_name)
        if instances:
            instance_to_terminate = instances[0]
            logger.info(f"Discovered instance: {instance_to_terminate}")
            if len(instances) > 1:
                click.echo(
                    click.style(
                        f"⚠️  Warning: Found {len(instances)} instances, using first: {instance_to_terminate}",
                        fg="yellow",
                    )
                )
        else:
            logger.info(f"No instances found with name: {instance_name}")

    # Discover or use provided S3 bucket
    bucket_name: Optional[str] = None
    if not skip_bucket:
        if s3_bucket:
            bucket_name = s3_bucket
            logger.info(f"Using explicitly provided S3 bucket: {s3_bucket}")
        else:
            # Use default bucket name from config
            config = ServerConfig(aws_region=region, instance_name=instance_name)
            bucket_name = config.s3_bucket_name
            logger.info(f"Using default S3 bucket name: {bucket_name}")

    # Display what will be done
    click.echo(
        click.style(f"\n{'[DRY RUN] ' if dry_run else ''}Teardown Plan:", fg="cyan", bold=True)
    )

    if instance_to_terminate:
        click.echo(f"  • EC2 Instance: {instance_to_terminate}")
    else:
        click.echo("  • EC2 Instance: None found (skipping)")

    if not skip_bucket and bucket_name:
        click.echo(f"  • S3 Bucket: {bucket_name} (recursive delete)")
    elif skip_bucket:
        click.echo("  • S3 Bucket: Skipped (--skip-bucket flag)")
    else:
        click.echo("  • S3 Bucket: None specified (skipping)")

    click.echo()

    # Track success/failure
    all_success = True

    # Step 1: Terminate EC2 instance
    if instance_to_terminate:
        click.echo(
            f"{'[DRY RUN] ' if dry_run else ''}Terminating EC2 instance {instance_to_terminate}..."
        )
        if ec2_manager.terminate_instance_and_wait(instance_to_terminate, dry_run=dry_run):
            click.echo(
                click.style(
                    f"✓ {'Would terminate' if dry_run else 'Terminated'} instance {instance_to_terminate}",
                    fg="green",
                )
            )
        else:
            click.echo(
                click.style(f"✗ Failed to terminate instance {instance_to_terminate}", fg="red")
            )
            all_success = False
    else:
        click.echo("No EC2 instance to terminate")

    # Step 2: Delete S3 bucket
    if not skip_bucket and bucket_name:
        click.echo(
            f"\n{'[DRY RUN] ' if dry_run else ''}Deleting S3 bucket {bucket_name} and all contents..."
        )
        s3_manager = S3Manager(bucket_name, region)
        if s3_manager.delete_bucket_recursive(dry_run=dry_run):
            click.echo(
                click.style(
                    f"✓ {'Would delete' if dry_run else 'Deleted'} bucket {bucket_name}",
                    fg="green",
                )
            )
        else:
            click.echo(click.style(f"✗ Failed to delete bucket {bucket_name}", fg="red"))
            all_success = False

    # Final summary
    click.echo()
    if dry_run:
        click.echo(
            click.style(
                "✓ Dry run completed. No resources were actually deleted.",
                fg="cyan",
                bold=True,
            )
        )
    elif all_success:
        click.echo(click.style("✓ Teardown completed successfully!", fg="green", bold=True))
    else:
        click.echo(click.style("✗ Teardown completed with errors", fg="red", bold=True))
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
@click.option(
    "--create-iam/--no-create-iam",
    default=False,
    help="Automatically create IAM role and instance profile for S3 access (default: off)",
)
@click.option("--iam-role-name", help="IAM role name to create (used with --create-iam)")
@click.option(
    "--iam-instance-profile-name",
    help="IAM instance profile name to create (used with --create-iam)",
)
@click.option(
    "--enable-wrapper/--no-enable-wrapper",
    default=True,
    help="Enable ac-server-wrapper for CM content downloads (default: on)",
)
@click.option(
    "--wrapper-port",
    type=int,
    default=8082,
    help="Port for ac-server-wrapper (default: 8082, must differ from AC HTTP port 8081)",
)
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
    enable_wrapper: bool,
    wrapper_port: int,
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
        enable_wrapper=enable_wrapper,
        wrapper_port=wrapper_port,
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
    from .config import AC_SERVER_HTTP_PORT, AC_SERVER_TCP_PORT, AC_SERVER_UDP_PORT

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
        click.echo(f"HTTP Port: {AC_SERVER_HTTP_PORT} (TCP)")
        click.echo(f"Direct Connect: {public_ip}:{AC_SERVER_TCP_PORT}")

        # Generate correct acstuff.ru link
        acstuff_url = f"https://acstuff.ru/s/q:race/online/join?ip={public_ip}&httpPort={AC_SERVER_HTTP_PORT}&password="
        click.echo(f"\n{click.style('Join Server:', fg='cyan', bold=True)}")
        click.echo(f"acstuff.ru link: {acstuff_url}")
        click.echo("\nOpen this link in your browser to join the server via Content Manager")

        # Perform connectivity checks
        click.echo(f"\n{click.style('Connectivity Checks:', fg='cyan', bold=True)}")

        # Check if host is reachable
        click.echo("Checking host reachability...")
        if check_host_reachable(public_ip):
            click.echo(click.style("  ✓ Host is reachable (ping)", fg="green"))
        else:
            click.echo(click.style("  ✗ Host is not reachable (ping)", fg="yellow"))
            click.echo("    Note: Some hosts may block ICMP ping")

        # Check TCP port (game port)
        click.echo(f"Checking TCP port {AC_SERVER_TCP_PORT}...")
        if check_tcp_port(public_ip, AC_SERVER_TCP_PORT):
            click.echo(click.style(f"  ✓ TCP port {AC_SERVER_TCP_PORT} is open", fg="green"))
        else:
            click.echo(
                click.style(f"  ✗ TCP port {AC_SERVER_TCP_PORT} is not accessible", fg="red")
            )
            click.echo("    The server may still be starting up or there may be a firewall issue")

        # Check UDP port (game port)
        click.echo(f"Checking UDP port {AC_SERVER_UDP_PORT}...")
        if check_udp_port(public_ip, AC_SERVER_UDP_PORT):
            click.echo(
                click.style(f"  ✓ UDP port {AC_SERVER_UDP_PORT} appears to be open", fg="green")
            )
        else:
            click.echo(
                click.style(f"  ✗ UDP port {AC_SERVER_UDP_PORT} is not accessible", fg="red")
            )
            click.echo("    Note: UDP checks are less reliable than TCP")

        # Check HTTP port
        click.echo(f"Checking TCP port {AC_SERVER_HTTP_PORT} (HTTP)...")
        if check_tcp_port(public_ip, AC_SERVER_HTTP_PORT):
            click.echo(
                click.style(f"  ✓ TCP port {AC_SERVER_HTTP_PORT} (HTTP) is open", fg="green")
            )
        else:
            click.echo(
                click.style(
                    f"  ✗ TCP port {AC_SERVER_HTTP_PORT} (HTTP) is not accessible", fg="red"
                )
            )
            click.echo("    The HTTP port is required for Content Manager connection")

        # Check acstuff.ru URL
        click.echo("Checking acstuff.ru join URL...")
        url_ok, url_error = check_url_accessible(acstuff_url)
        if url_ok:
            click.echo(click.style("  ✓ acstuff.ru join URL is accessible", fg="green"))
        else:
            if url_error == "Skipped (curl not available)":
                click.echo(click.style(f"  ⚠ {url_error}", fg="yellow"))
            else:
                click.echo(
                    click.style(f"  ✗ acstuff.ru join URL check failed: {url_error}", fg="yellow")
                )
                click.echo("    Note: This may not indicate a server problem")

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
