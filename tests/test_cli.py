"""Unit tests for CLI commands."""

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from ac_server_manager.cli import status, terminate_all
from ac_server_manager.config import AC_SERVER_HTTP_PORT, AC_SERVER_TCP_PORT


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


def test_status_command_displays_acstuff_url(runner: CliRunner) -> None:
    """Test that status command displays correct acstuff.ru join link format."""
    mock_details = {
        "instance_id": "i-12345",
        "state": "running",
        "instance_type": "t3.small",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        patch("ac_server_manager.cli.check_host_reachable") as mock_ping,
        patch("ac_server_manager.cli.check_tcp_port") as mock_tcp,
        patch("ac_server_manager.cli.check_udp_port") as mock_udp,
        patch("ac_server_manager.cli.check_url_accessible") as mock_url,
    ):

        mock_deployer_instance = MagicMock()
        mock_deployer_instance.get_status.return_value = mock_details
        MockDeployer.return_value = mock_deployer_instance

        # Mock connectivity checks to pass
        mock_ping.return_value = True
        mock_tcp.return_value = True
        mock_udp.return_value = True
        mock_url.return_value = (True, None)

        result = runner.invoke(status)

        assert result.exit_code == 0
        # Check that the new acstuff.ru URL format is displayed with & separators
        expected_url = f"https://acstuff.ru/s/q:race/online/join?ip=1.2.3.4&httpPort={AC_SERVER_HTTP_PORT}&password="
        assert expected_url in result.output
        assert "acstuff.ru link:" in result.output
        # Ensure old format with colon is not present
        assert f"1.2.3.4:{AC_SERVER_TCP_PORT}" not in result.output.split("acstuff.ru link:")[1]


def test_status_command_displays_connection_info(runner: CliRunner) -> None:
    """Test that status command displays all connection information."""
    mock_details = {
        "instance_id": "i-12345",
        "state": "running",
        "instance_type": "t3.small",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        patch("ac_server_manager.cli.check_host_reachable") as mock_ping,
        patch("ac_server_manager.cli.check_tcp_port") as mock_tcp,
        patch("ac_server_manager.cli.check_udp_port") as mock_udp,
        patch("ac_server_manager.cli.check_url_accessible") as mock_url,
    ):

        mock_deployer_instance = MagicMock()
        mock_deployer_instance.get_status.return_value = mock_details
        MockDeployer.return_value = mock_deployer_instance

        # Mock connectivity checks to pass
        mock_ping.return_value = True
        mock_tcp.return_value = True
        mock_udp.return_value = True
        mock_url.return_value = (True, None)

        result = runner.invoke(status)

        assert result.exit_code == 0
        assert "Instance ID: i-12345" in result.output
        assert "State:" in result.output
        assert "running" in result.output
        assert "Public IP: 1.2.3.4" in result.output
        assert f"Direct Connect: 1.2.3.4:{AC_SERVER_TCP_PORT}" in result.output
        assert "Join Server:" in result.output
        assert "Connectivity Checks:" in result.output


def test_status_command_no_instance_found(runner: CliRunner) -> None:
    """Test status command when no instance is found."""
    with patch("ac_server_manager.cli.Deployer") as MockDeployer:
        mock_deployer_instance = MagicMock()
        mock_deployer_instance.get_status.return_value = None
        MockDeployer.return_value = mock_deployer_instance

        result = runner.invoke(status)

        assert result.exit_code == 1
        assert "No instance found" in result.output


def test_status_command_instance_not_running(runner: CliRunner) -> None:
    """Test status command when instance is not in running state."""
    mock_details = {
        "instance_id": "i-12345",
        "state": "stopped",
        "instance_type": "t3.small",
        "public_ip": None,
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }

    with patch("ac_server_manager.cli.Deployer") as MockDeployer:
        mock_deployer_instance = MagicMock()
        mock_deployer_instance.get_status.return_value = mock_details
        MockDeployer.return_value = mock_deployer_instance

        result = runner.invoke(status)

        assert result.exit_code == 0
        assert "Instance is stopped" in result.output
        # Should not display acstuff.ru link for stopped instance
        assert "acstuff.ru" not in result.output


def test_status_command_connectivity_checks_failing(runner: CliRunner) -> None:
    """Test that status command displays connectivity check failures."""
    mock_details = {
        "instance_id": "i-12345",
        "state": "running",
        "instance_type": "t3.small",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "launch_time": datetime(2024, 1, 1),
        "name": "test-instance",
    }

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        patch("ac_server_manager.cli.check_host_reachable") as mock_ping,
        patch("ac_server_manager.cli.check_tcp_port") as mock_tcp,
        patch("ac_server_manager.cli.check_udp_port") as mock_udp,
        patch("ac_server_manager.cli.check_url_accessible") as mock_url,
    ):

        mock_deployer_instance = MagicMock()
        mock_deployer_instance.get_status.return_value = mock_details
        MockDeployer.return_value = mock_deployer_instance

        # Mock connectivity checks to fail
        mock_ping.return_value = False
        mock_tcp.return_value = False
        mock_udp.return_value = False
        mock_url.return_value = (False, "HTTP 404")

        result = runner.invoke(status)

        assert result.exit_code == 0
        assert "Connectivity Checks:" in result.output
        assert "is not reachable" in result.output
        assert "is not accessible" in result.output
        assert "failed" in result.output or "not accessible" in result.output


def test_terminate_all_dry_run(runner: CliRunner) -> None:
    """Test terminate-all command in dry-run mode."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.find_instances_by_name.return_value = ["i-12345"]
        mock_ec2.terminate_instance_and_wait.return_value = True
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        mock_s3.delete_bucket_recursive.return_value = True
        MockS3Manager.return_value = mock_s3

        result = runner.invoke(terminate_all, ["--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "No resources were actually deleted" in result.output
        mock_ec2.terminate_instance_and_wait.assert_called_once_with("i-12345", dry_run=True)
        mock_s3.delete_bucket_recursive.assert_called_once_with(dry_run=True)


def test_terminate_all_force(runner: CliRunner) -> None:
    """Test terminate-all command with force flag."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.find_instances_by_name.return_value = ["i-12345"]
        mock_ec2.terminate_instance_and_wait.return_value = True
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        mock_s3.delete_bucket_recursive.return_value = True
        MockS3Manager.return_value = mock_s3

        result = runner.invoke(terminate_all, ["--force"])

        assert result.exit_code == 0
        assert "Teardown completed successfully" in result.output
        # Should not have prompted for confirmation
        assert "Type" not in result.output or "TERMINATE" not in result.output.split("Teardown")[0]


def test_terminate_all_skip_bucket(runner: CliRunner) -> None:
    """Test terminate-all command with skip-bucket flag."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.find_instances_by_name.return_value = ["i-12345"]
        mock_ec2.terminate_instance_and_wait.return_value = True
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        MockS3Manager.return_value = mock_s3

        result = runner.invoke(terminate_all, ["--force", "--skip-bucket"])

        assert result.exit_code == 0
        assert "Teardown completed successfully" in result.output
        # S3 manager should not have been called to delete bucket
        mock_s3.delete_bucket_recursive.assert_not_called()


def test_terminate_all_with_explicit_ids(runner: CliRunner) -> None:
    """Test terminate-all command with explicit instance and bucket."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.terminate_instance_and_wait.return_value = True
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        mock_s3.delete_bucket_recursive.return_value = True
        MockS3Manager.return_value = mock_s3

        result = runner.invoke(
            terminate_all,
            ["--force", "--instance-id", "i-explicit", "--s3-bucket", "my-explicit-bucket"],
        )

        assert result.exit_code == 0
        mock_ec2.terminate_instance_and_wait.assert_called_once_with("i-explicit", dry_run=False)
        # Check that S3Manager was created with the explicit bucket name
        MockS3Manager.assert_called_with("my-explicit-bucket", "us-east-1")


def test_terminate_all_no_resources_found(runner: CliRunner) -> None:
    """Test terminate-all command when no resources are found."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.find_instances_by_name.return_value = []
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        mock_s3.delete_bucket_recursive.return_value = True
        MockS3Manager.return_value = mock_s3

        result = runner.invoke(terminate_all, ["--force"])

        assert result.exit_code == 0
        assert "No EC2 instance to terminate" in result.output
        assert "Teardown completed successfully" in result.output


def test_terminate_all_confirmation_required(runner: CliRunner) -> None:
    """Test terminate-all command requires confirmation without force."""
    with (
        patch("ac_server_manager.ec2_manager.EC2Manager") as MockEC2Manager,
        patch("ac_server_manager.s3_manager.S3Manager") as MockS3Manager,
    ):
        mock_ec2 = MagicMock()
        mock_ec2.find_instances_by_name.return_value = ["i-12345"]
        mock_ec2.terminate_instance_and_wait.return_value = True
        MockEC2Manager.return_value = mock_ec2

        mock_s3 = MagicMock()
        MockS3Manager.return_value = mock_s3

        # Simulate user entering wrong confirmation
        result = runner.invoke(terminate_all, input="WRONG\n")

        assert result.exit_code == 1
        assert "Confirmation failed" in result.output
        # Should not have called any AWS operations
        mock_ec2.terminate_instance_and_wait.assert_not_called()


def test_deploy_accepts_wrapper_options(runner: CliRunner) -> None:
    """Test that deploy command accepts --enable-wrapper and --wrapper-port options."""
    from ac_server_manager.cli import deploy
    from pathlib import Path
    import tempfile

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file,
    ):
        tmp_path = Path(tmp_file.name)

        try:
            mock_deployer_instance = MagicMock()
            mock_deployer_instance.deploy.return_value = "i-test123"
            MockDeployer.return_value = mock_deployer_instance

            # Test with --enable-wrapper and custom port
            result = runner.invoke(
                deploy, [str(tmp_path), "--enable-wrapper", "--wrapper-port", "9000"]
            )

            assert result.exit_code == 0
            # Verify Deployer was called with correct config
            MockDeployer.assert_called_once()
            config = MockDeployer.call_args[0][0]
            assert config.enable_wrapper is True
            assert config.wrapper_port == 9000
        finally:
            tmp_path.unlink()


def test_deploy_wrapper_defaults(runner: CliRunner) -> None:
    """Test that deploy command uses correct defaults for wrapper options."""
    from ac_server_manager.cli import deploy
    from pathlib import Path
    import tempfile

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file,
    ):
        tmp_path = Path(tmp_file.name)

        try:
            mock_deployer_instance = MagicMock()
            mock_deployer_instance.deploy.return_value = "i-test123"
            MockDeployer.return_value = mock_deployer_instance

            # Test without wrapper options - should use defaults
            result = runner.invoke(deploy, [str(tmp_path)])

            assert result.exit_code == 0
            MockDeployer.assert_called_once()
            config = MockDeployer.call_args[0][0]
            assert config.enable_wrapper is False
            assert config.wrapper_port == 8082
        finally:
            tmp_path.unlink()


def test_deploy_no_enable_wrapper(runner: CliRunner) -> None:
    """Test that deploy command accepts --no-enable-wrapper option."""
    from ac_server_manager.cli import deploy
    from pathlib import Path
    import tempfile

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file,
    ):
        tmp_path = Path(tmp_file.name)

        try:
            mock_deployer_instance = MagicMock()
            mock_deployer_instance.deploy.return_value = "i-test123"
            MockDeployer.return_value = mock_deployer_instance

            # Test explicit --no-enable-wrapper
            result = runner.invoke(deploy, [str(tmp_path), "--no-enable-wrapper"])

            assert result.exit_code == 0
            MockDeployer.assert_called_once()
            config = MockDeployer.call_args[0][0]
            assert config.enable_wrapper is False
        finally:
            tmp_path.unlink()


def test_redeploy_accepts_wrapper_options(runner: CliRunner) -> None:
    """Test that redeploy command accepts --enable-wrapper and --wrapper-port options."""
    from ac_server_manager.cli import redeploy
    from pathlib import Path
    import tempfile

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file,
    ):
        tmp_path = Path(tmp_file.name)

        try:
            mock_deployer_instance = MagicMock()
            mock_deployer_instance.redeploy.return_value = "i-test456"
            MockDeployer.return_value = mock_deployer_instance

            # Test with --enable-wrapper and custom port
            result = runner.invoke(
                redeploy, [str(tmp_path), "--enable-wrapper", "--wrapper-port", "9001"]
            )

            assert result.exit_code == 0
            MockDeployer.assert_called_once()
            config = MockDeployer.call_args[0][0]
            assert config.enable_wrapper is True
            assert config.wrapper_port == 9001
        finally:
            tmp_path.unlink()


def test_redeploy_wrapper_defaults(runner: CliRunner) -> None:
    """Test that redeploy command uses correct defaults for wrapper options."""
    from ac_server_manager.cli import redeploy
    from pathlib import Path
    import tempfile

    with (
        patch("ac_server_manager.cli.Deployer") as MockDeployer,
        tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file,
    ):
        tmp_path = Path(tmp_file.name)

        try:
            mock_deployer_instance = MagicMock()
            mock_deployer_instance.redeploy.return_value = "i-test456"
            MockDeployer.return_value = mock_deployer_instance

            # Test without wrapper options - should use defaults
            result = runner.invoke(redeploy, [str(tmp_path)])

            assert result.exit_code == 0
            MockDeployer.assert_called_once()
            config = MockDeployer.call_args[0][0]
            assert config.enable_wrapper is False
            assert config.wrapper_port == 8082
        finally:
            tmp_path.unlink()

