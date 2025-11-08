"""Integration tests for user-data validation script."""

import subprocess
import tempfile
from pathlib import Path

from ac_server_manager.ec2_manager import EC2Manager


def test_validation_script_syntax() -> None:
    """Test that generated validation script has valid bash syntax."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Write script to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        # Check bash syntax
        result = subprocess.run(
            ["bash", "-n", script_path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"
    finally:
        Path(script_path).unlink()


def test_validation_script_contains_all_checks() -> None:
    """Test that validation script includes all required validation functions."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for all validation functions
    assert "check_process_running()" in script
    assert "check_ports_listening()" in script
    assert "check_server_logs()" in script

    # Check for validation execution
    assert "if ! check_process_running; then" in script
    assert "if ! check_ports_listening; then" in script
    assert "if ! check_server_logs; then" in script


def test_validation_script_checks_correct_ports() -> None:
    """Test that validation script checks the correct port numbers."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Verify port numbers are correct
    assert ":9600" in script  # Game port
    assert ":8081" in script  # HTTP API port


def test_validation_script_has_proper_exit_codes() -> None:
    """Test that validation script has proper exit codes."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for exit codes
    assert "exit 1" in script  # Failure
    assert "exit 0" in script  # Success

    # Check for validation status messages
    assert "VALIDATION FAILED" in script
    assert "VALIDATION PASSED" in script


def test_validation_script_checks_common_errors() -> None:
    """Test that validation script checks for common error patterns."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for common error patterns
    error_patterns = [
        "track not found",
        "content not found",
        "missing track",
        "missing car",
        "invalid configuration",
        "failed to load",
        "error loading",
        "bind.*failed",
        "port.*in use",
        "address already in use",
    ]

    for pattern in error_patterns:
        assert pattern in script, f"Error pattern '{pattern}' not found in script"


def test_validation_script_has_logging() -> None:
    """Test that validation script includes proper logging."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for logging setup
    assert "DEPLOYMENT_LOG=" in script
    assert "VALIDATION_LOG=" in script
    assert "log_message()" in script

    # Check for log messages
    assert "Starting Post-Boot Validation" in script
    assert "Checking if acServer process is running" in script
    assert "Checking if required ports are listening" in script
    assert "Checking server logs for configuration errors" in script


def test_validation_script_waits_for_process() -> None:
    """Test that validation script waits for process to start."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for wait loop
    assert "for i in {1..30}; do" in script  # Process wait
    assert "for i in {1..10}; do" in script  # Log file wait
    assert "sleep" in script


def test_validation_script_uses_pgrep() -> None:
    """Test that validation script uses pgrep to check process."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for pgrep usage
    assert 'pgrep -x "acServer"' in script


def test_validation_script_uses_ss_for_ports() -> None:
    """Test that validation script uses ss command for port checking."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for ss command usage
    assert "ss -tlnp" in script  # TCP listening
    assert "ss -ulnp" in script  # UDP listening


def test_validation_script_provides_troubleshooting_info() -> None:
    """Test that validation script provides troubleshooting information on failure."""
    manager = EC2Manager("us-east-1")
    script = manager.create_user_data_script("test-bucket", "test-key.tar.gz")

    # Check for troubleshooting commands
    assert "systemctl status acserver" in script
    assert "journalctl -u acserver" in script
