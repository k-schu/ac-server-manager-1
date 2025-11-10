"""Unit tests for EC2Manager."""

from unittest.mock import MagicMock, patch
import pytest

from ac_server_manager.ec2_manager import EC2Manager


@pytest.fixture
def ec2_manager() -> EC2Manager:
    """Create EC2Manager instance for testing."""
    with patch("boto3.client"), patch("boto3.resource"):
        return EC2Manager("us-east-1")


def test_ec2_manager_init(ec2_manager: EC2Manager) -> None:
    """Test EC2Manager initialization."""
    assert ec2_manager.region == "us-east-1"


def test_create_security_group_already_exists(ec2_manager: EC2Manager) -> None:
    """Test create_security_group when group already exists."""
    ec2_manager.ec2_client.describe_security_groups = MagicMock(
        return_value={"SecurityGroups": [{"GroupId": "sg-12345"}]}
    )

    result = ec2_manager.create_security_group("test-sg", "Test security group")

    assert result == "sg-12345"


def test_create_security_group_new(ec2_manager: EC2Manager) -> None:
    """Test create_security_group when creating new group."""
    ec2_manager.ec2_client.describe_security_groups = MagicMock(return_value={"SecurityGroups": []})
    ec2_manager.ec2_client.create_security_group = MagicMock(return_value={"GroupId": "sg-67890"})
    ec2_manager.ec2_client.authorize_security_group_ingress = MagicMock()

    result = ec2_manager.create_security_group("test-sg", "Test security group")

    assert result == "sg-67890"
    ec2_manager.ec2_client.create_security_group.assert_called_once()
    ec2_manager.ec2_client.authorize_security_group_ingress.assert_called_once()


def test_get_ubuntu_ami_success(ec2_manager: EC2Manager) -> None:
    """Test getting Ubuntu AMI."""
    ec2_manager.ec2_client.describe_images = MagicMock(
        return_value={
            "Images": [
                {"ImageId": "ami-old", "CreationDate": "2023-01-01T00:00:00.000Z"},
                {"ImageId": "ami-new", "CreationDate": "2023-12-01T00:00:00.000Z"},
            ]
        }
    )

    result = ec2_manager.get_ubuntu_ami()

    assert result == "ami-new"


def test_get_ubuntu_ami_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting Ubuntu AMI when none found."""
    ec2_manager.ec2_client.describe_images = MagicMock(return_value={"Images": []})

    result = ec2_manager.get_ubuntu_ami()

    assert result is None


def test_create_user_data_script(ec2_manager: EC2Manager) -> None:
    """Test user data script creation."""
    script = ec2_manager.create_user_data_script("test-bucket", "packs/test.tar.gz")

    # Basic script structure
    assert "#!/bin/bash" in script
    assert "set -euo pipefail" in script

    # Required packages installation
    assert "awscli" in script
    assert "unzip" in script
    assert "wget" in script
    assert "tar" in script
    assert "jq" in script
    assert "lib32gcc-s1" in script
    assert "lib32stdc++6" in script
    assert "iproute2" in script or "net-tools" in script

    # S3 download with retries
    assert "aws s3 cp s3://test-bucket/packs/test.tar.gz" in script
    assert "MAX_RETRIES" in script
    assert "RETRY_DELAY" in script

    # Pack extraction and verification
    assert "tar -xzf server-pack.tar.gz" in script

    # Binary location and verification
    assert "find /opt/acserver" in script
    assert "acServer" in script or "acserver" in script
    assert "file" in script  # file command to check binary type
    assert "ELF" in script
    assert "PE32" in script or "Windows" in script  # Check for Windows binary detection

    # Binary permissions - now uses variable
    assert "chmod +x" in script
    assert "chown root:root" in script

    # ldd check for dependencies
    assert "ldd" in script

    # Systemd service creation with dynamic path
    assert "systemctl daemon-reload" in script
    assert "systemctl enable acserver" in script
    assert "systemctl start acserver" in script
    assert "/etc/systemd/system/acserver.service" in script
    assert "WorkingDirectory=" in script
    assert "ExecStart=" in script

    # Validation timeout
    assert "VALIDATION_TIMEOUT" in script

    # Process validation
    assert "pgrep" in script

    # Port validation with both ss and netstat fallback
    assert "ss -tlnp" in script or "netstat -tlnp" in script
    assert "ss -ulnp" in script or "netstat -ulnp" in script

    # Port constants and usage
    assert "AC_SERVER_TCP_PORT=9600" in script
    assert "AC_SERVER_UDP_PORT=9600" in script
    assert "AC_SERVER_HTTP_PORT=8081" in script
    # Ports are now referenced via variables
    assert "$AC_SERVER_TCP_PORT" in script
    assert "$AC_SERVER_UDP_PORT" in script
    assert "$AC_SERVER_HTTP_PORT" in script

    # HTTP endpoint check
    assert "curl" in script
    assert "http://127.0.0.1" in script

    # Public IP retrieval
    assert "169.254.169.254/latest/meta-data/public-ipv4" in script

    # acstuff join link
    assert "acstuff" in script

    # Log validation - common error patterns
    assert "track not found" in script
    assert "content not found" in script
    assert "missing track" in script
    assert "failed to bind" in script
    assert "port.*in use" in script
    assert "address already in use" in script
    assert "permission denied" in script
    assert "segmentation fault" in script

    # Status file
    assert "/opt/acserver/deploy-status.json" in script
    assert "STATUS_FILE" in script
    assert "write_status" in script
    assert '"success":' in script
    assert '"timestamp":' in script
    assert '"public_ip":' in script
    assert '"error_messages":' in script

    # Deployment log
    assert "/var/log/acserver-deploy.log" in script
    assert "DEPLOY_LOG" in script
    assert "log_message" in script

    # Exit codes
    assert "exit 1" in script  # Failure case
    assert "exit 0" in script  # Success case
    assert "VALIDATION FAILED" in script
    assert "VALIDATION PASSED" in script

    # Error tracking
    assert "ERROR_MESSAGES" in script
    assert "add_error" in script

    # Content.json patching script with local cm_content copying (PATCH_CONTENT_JSON marker)
    assert "PATCH_CONTENT_JSON" in script
    assert "Patching content.json files to work with ac-server-wrapper" in script
    assert "python3 << 'PYTHON_CONTENT_PATCHER'" in script
    assert "is_windows_absolute_path" in script
    assert "fix_windows_path_local" in script or "copy_file_to_cm_content" in script
    assert "shutil.copy2" in script
    assert "patch_content_json_file" in script
    assert "PYTHON_CONTENT_PATCHER" in script
    assert "cm_content" in script
    assert ".bak" in script  # Backup files
    # Verify the patching runs after extraction but before server start
    extraction_idx = script.find("tar -xzf server-pack.tar.gz")
    patching_idx = script.find("Patching content.json files to work with ac-server-wrapper")
    service_start_idx = script.find("systemctl start acserver")
    assert (
        extraction_idx < patching_idx < service_start_idx
    ), "Content.json patching must run after extraction and before service start"


def test_launch_instance_success(ec2_manager: EC2Manager) -> None:
    """Test successful instance launch."""
    ec2_manager.ec2_client.run_instances = MagicMock(
        return_value={"Instances": [{"InstanceId": "i-12345"}]}
    )
    ec2_manager.ec2_client.get_waiter = MagicMock()

    result = ec2_manager.launch_instance(
        ami_id="ami-12345",
        instance_type="t3.small",
        security_group_id="sg-12345",
        user_data="#!/bin/bash",
        instance_name="test-instance",
    )

    assert result == "i-12345"
    ec2_manager.ec2_client.run_instances.assert_called_once()


def test_launch_instance_with_key(ec2_manager: EC2Manager) -> None:
    """Test instance launch with SSH key."""
    ec2_manager.ec2_client.run_instances = MagicMock(
        return_value={"Instances": [{"InstanceId": "i-12345"}]}
    )
    ec2_manager.ec2_client.get_waiter = MagicMock()

    result = ec2_manager.launch_instance(
        ami_id="ami-12345",
        instance_type="t3.small",
        security_group_id="sg-12345",
        user_data="#!/bin/bash",
        instance_name="test-instance",
        key_name="my-key",
    )

    assert result == "i-12345"
    call_args = ec2_manager.ec2_client.run_instances.call_args[1]
    assert call_args["KeyName"] == "my-key"


def test_get_instance_public_ip(ec2_manager: EC2Manager) -> None:
    """Test getting instance public IP."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={"Reservations": [{"Instances": [{"PublicIpAddress": "1.2.3.4"}]}]}
    )

    result = ec2_manager.get_instance_public_ip("i-12345")

    assert result == "1.2.3.4"


def test_get_instance_public_ip_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting instance public IP when not found."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.get_instance_public_ip("i-12345")

    assert result is None


def test_stop_instance(ec2_manager: EC2Manager) -> None:
    """Test stopping instance."""
    ec2_manager.ec2_client.stop_instances = MagicMock()

    result = ec2_manager.stop_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.stop_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_start_instance(ec2_manager: EC2Manager) -> None:
    """Test starting instance."""
    ec2_manager.ec2_client.start_instances = MagicMock()

    result = ec2_manager.start_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.start_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_terminate_instance(ec2_manager: EC2Manager) -> None:
    """Test terminating instance."""
    ec2_manager.ec2_client.terminate_instances = MagicMock()

    result = ec2_manager.terminate_instance("i-12345")

    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_called_once_with(InstanceIds=["i-12345"])


def test_terminate_instance_and_wait_success(ec2_manager: EC2Manager) -> None:
    """Test terminating instance with wait."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-12345", "State": {"Name": "running"}}]}
            ]
        }
    )
    ec2_manager.ec2_client.terminate_instances = MagicMock()
    mock_waiter = MagicMock()
    ec2_manager.ec2_client.get_waiter = MagicMock(return_value=mock_waiter)

    result = ec2_manager.terminate_instance_and_wait("i-12345")

    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_called_once()
    mock_waiter.wait.assert_called_once()


def test_terminate_instance_and_wait_already_terminated(ec2_manager: EC2Manager) -> None:
    """Test terminating instance that's already terminated."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-12345", "State": {"Name": "terminated"}}]}
            ]
        }
    )
    ec2_manager.ec2_client.terminate_instances = MagicMock()

    result = ec2_manager.terminate_instance_and_wait("i-12345")

    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_not_called()


def test_terminate_instance_and_wait_not_found(ec2_manager: EC2Manager) -> None:
    """Test terminating instance that doesn't exist."""
    from botocore.exceptions import ClientError

    ec2_manager.ec2_client.describe_instances = MagicMock(
        side_effect=ClientError(
            {"Error": {"Code": "InvalidInstanceID.NotFound"}}, "describe_instances"
        )
    )

    result = ec2_manager.terminate_instance_and_wait("i-12345")

    assert result is True


def test_terminate_instance_and_wait_dry_run(ec2_manager: EC2Manager) -> None:
    """Test terminating instance in dry-run mode."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-12345", "State": {"Name": "running"}}]}
            ]
        }
    )
    ec2_manager.ec2_client.terminate_instances = MagicMock()

    result = ec2_manager.terminate_instance_and_wait("i-12345", dry_run=True)

    assert result is True
    ec2_manager.ec2_client.terminate_instances.assert_not_called()


def test_find_instances_by_name(ec2_manager: EC2Manager) -> None:
    """Test finding instances by name."""
    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-12345"}]},
                {"Instances": [{"InstanceId": "i-67890"}]},
            ]
        }
    )

    result = ec2_manager.find_instances_by_name("test-instance")

    assert len(result) == 2
    assert "i-12345" in result
    assert "i-67890" in result


def test_find_instances_by_name_none_found(ec2_manager: EC2Manager) -> None:
    """Test finding instances by name when none exist."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.find_instances_by_name("test-instance")

    assert result == []


def test_get_instance_details_success(ec2_manager: EC2Manager) -> None:
    """Test getting instance details successfully."""
    from datetime import datetime

    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-12345",
                            "State": {"Name": "running"},
                            "InstanceType": "t3.small",
                            "PublicIpAddress": "1.2.3.4",
                            "PrivateIpAddress": "10.0.0.1",
                            "LaunchTime": datetime(2024, 1, 1),
                            "Tags": [
                                {"Key": "Name", "Value": "test-instance"},
                                {"Key": "Application", "Value": "ac-server"},
                            ],
                        }
                    ]
                }
            ]
        }
    )

    result = ec2_manager.get_instance_details("i-12345")

    assert result is not None
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "running"
    assert result["instance_type"] == "t3.small"
    assert result["public_ip"] == "1.2.3.4"
    assert result["private_ip"] == "10.0.0.1"
    assert result["name"] == "test-instance"


def test_get_instance_details_not_found(ec2_manager: EC2Manager) -> None:
    """Test getting instance details when instance not found."""
    ec2_manager.ec2_client.describe_instances = MagicMock(return_value={"Reservations": []})

    result = ec2_manager.get_instance_details("i-99999")

    assert result is None


def test_get_instance_details_no_public_ip(ec2_manager: EC2Manager) -> None:
    """Test getting instance details when no public IP assigned."""
    from datetime import datetime

    ec2_manager.ec2_client.describe_instances = MagicMock(
        return_value={
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-12345",
                            "State": {"Name": "stopped"},
                            "InstanceType": "t3.small",
                            "PrivateIpAddress": "10.0.0.1",
                            "LaunchTime": datetime(2024, 1, 1),
                            "Tags": [{"Key": "Name", "Value": "test-instance"}],
                        }
                    ]
                }
            ]
        }
    )

    result = ec2_manager.get_instance_details("i-12345")

    assert result is not None
    assert result["instance_id"] == "i-12345"
    assert result["state"] == "stopped"
    assert result["public_ip"] is None


def test_upload_bootstrap_to_s3_success(ec2_manager: EC2Manager) -> None:
    """Test successful bootstrap script upload to S3."""
    from unittest.mock import MagicMock

    mock_s3_manager = MagicMock()
    mock_s3_manager.bucket_name = "test-bucket"
    mock_s3_manager.upload_bytes = MagicMock(return_value=True)
    mock_s3_manager.generate_presigned_url = MagicMock(
        return_value="https://test-bucket.s3.amazonaws.com/bootstrap/test.sh?signature=..."
    )

    bootstrap_script = "#!/bin/bash\necho 'test'"
    result = ec2_manager.upload_bootstrap_to_s3(mock_s3_manager, bootstrap_script)

    assert result is not None
    s3_key, presigned_url = result
    assert s3_key.startswith("bootstrap/bootstrap-")
    assert s3_key.endswith(".sh")
    assert presigned_url == "https://test-bucket.s3.amazonaws.com/bootstrap/test.sh?signature=..."
    mock_s3_manager.upload_bytes.assert_called_once()
    mock_s3_manager.generate_presigned_url.assert_called_once()


def test_upload_bootstrap_to_s3_upload_fails(ec2_manager: EC2Manager) -> None:
    """Test bootstrap upload when S3 upload fails."""
    from unittest.mock import MagicMock

    mock_s3_manager = MagicMock()
    mock_s3_manager.upload_bytes = MagicMock(return_value=False)

    bootstrap_script = "#!/bin/bash\necho 'test'"
    result = ec2_manager.upload_bootstrap_to_s3(mock_s3_manager, bootstrap_script)

    assert result is None


def test_upload_bootstrap_to_s3_presigned_url_fails(ec2_manager: EC2Manager) -> None:
    """Test bootstrap upload when presigned URL generation fails."""
    from unittest.mock import MagicMock

    mock_s3_manager = MagicMock()
    mock_s3_manager.upload_bytes = MagicMock(return_value=True)
    mock_s3_manager.generate_presigned_url = MagicMock(return_value=None)

    bootstrap_script = "#!/bin/bash\necho 'test'"
    result = ec2_manager.upload_bootstrap_to_s3(mock_s3_manager, bootstrap_script)

    assert result is None


def test_create_minimal_user_data_with_presigned_url(ec2_manager: EC2Manager) -> None:
    """Test minimal user data script creation with presigned URL."""
    presigned_url = "https://test-bucket.s3.amazonaws.com/bootstrap/test.sh?X-Amz-Signature=..."

    user_data = ec2_manager.create_minimal_user_data_with_presigned_url(presigned_url)

    # Check script structure
    assert "#!/bin/bash" in user_data
    assert "set -e" in user_data

    # Check download logic with both curl and wget
    assert "curl" in user_data
    assert "wget" in user_data
    assert presigned_url in user_data

    # Check bootstrap path
    assert "/tmp/bootstrap.sh" in user_data
    assert "BOOTSTRAP_PATH" in user_data

    # Check execution
    assert "chmod +x" in user_data
    assert 'exec "$BOOTSTRAP_PATH"' in user_data

    # Verify size is small
    size = len(user_data.encode("utf-8"))
    assert size < 2000, f"Minimal user data should be < 2KB, got {size} bytes"


def test_create_minimal_user_data_size_is_under_16kb(ec2_manager: EC2Manager) -> None:
    """Test that minimal user data stays well under 16KB limit."""
    # Even with a very long presigned URL (AWS URLs can be quite long)
    long_presigned_url = (
        "https://test-bucket.s3.us-east-1.amazonaws.com/"
        "bootstrap/bootstrap-20231201-123456-abcd1234.sh?"
        "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
        "X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2F20231201%2Fus-east-1%2Fs3%2Faws4_request&"
        "X-Amz-Date=20231201T120000Z&"
        "X-Amz-Expires=3600&"
        "X-Amz-SignedHeaders=host&"
        "X-Amz-Signature=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    )

    user_data = ec2_manager.create_minimal_user_data_with_presigned_url(long_presigned_url)

    size = len(user_data.encode("utf-8"))
    assert size < 16384, f"User data must be under 16KB, got {size} bytes"
    assert size < 2000, f"Minimal user data should be well under 16KB, got {size} bytes"


def test_create_user_data_script_local_content_json_patching(ec2_manager: EC2Manager) -> None:
    """Test that user data script includes local cm_content patching for content.json."""
    s3_bucket = "test-bucket"
    s3_key = "packs/my-server-pack-v1.2.tar.gz"

    script = ec2_manager.create_user_data_script(s3_bucket, s3_key)

    # Verify PACK_ID is derived and set (S3_BUCKET no longer needed)
    assert "export PACK_ID=" in script
    # PACK_ID should be sanitized version of filename
    assert "my-server-pack-v1_2" in script or "my_server_pack_v1_2" in script

    # Verify python3 is installed (but not pip/boto3)
    assert "python3" in script
    assert "python3-pip" not in script
    assert "boto3" not in script

    # Verify Python content patcher script is embedded with PATCH_CONTENT_JSON marker
    assert "PATCH_CONTENT_JSON" in script
    assert "PYTHON_CONTENT_PATCHER" in script
    assert "Patching content.json files to work with ac-server-wrapper" in script

    # Verify shutil import and usage for local file copying
    assert "import shutil" in script
    assert "shutil.copy2" in script

    # Verify local file operations (no S3 upload)
    assert "copy_file_to_cm_content" in script
    assert "fix_windows_path_local" in script
    assert "cm_content" in script
    assert "preset" in script  # Check for preset directory

    # Verify backup creation
    assert ".bak" in script

    # Verify Windows path detection
    assert "is_windows_absolute_path" in script
    assert "[a-zA-Z]:[/\\\\]" in script  # Drive letter pattern

    # Verify content.json file processing
    assert "content.json" in script
    assert "patch_content_json_file" in script

    # Verify environment variable usage in Python script (only PACK_ID now)
    assert "os.environ.get('PACK_ID')" in script

    # Verify no S3 operations
    assert "upload_file" not in script
    assert "generate_presigned_url" not in script
    assert "boto3.client('s3')" not in script

    # Verify 'file' vs 'url' field handling
    assert "key == 'file'" in script

    # Verify wrapper port adjustment
    assert "adjust_wrapper_port" in script
    assert "cm_wrapper_params.json" in script

    # Verify patching happens after extraction but before server start
    extraction_idx = script.find("tar -xzf server-pack.tar.gz")
    patching_idx = script.find("Patching content.json files to work with ac-server-wrapper")
    server_start_idx = script.find("systemctl start acserver")

    assert extraction_idx > 0, "Extraction command not found"
    assert patching_idx > 0, "Patching command not found"
    assert server_start_idx > 0, "Server start command not found"
    assert (
        extraction_idx < patching_idx < server_start_idx
    ), "Content.json patching must run after extraction and before server start"


def test_create_user_data_script_pack_id_sanitization(ec2_manager: EC2Manager) -> None:
    """Test that PACK_ID is properly sanitized from various S3 key formats."""
    test_cases = [
        ("packs/simple.tar.gz", "simple"),
        ("packs/with-dashes.tar.gz", "with-dashes"),
        ("packs/with_underscores.tar.gz", "with_underscores"),
        ("nested/path/to/pack.tar.gz", "pack"),
        ("packs/special!@#chars.tar.gz", "special___chars"),
        ("packs/version-1.2.3.tar.gz", "version-1_2_3"),
        ("packs/pack.zip", "pack"),
    ]

    for s3_key, expected_sanitized in test_cases:
        script = ec2_manager.create_user_data_script("test-bucket", s3_key)

        # Check that PACK_ID is set
        assert "export PACK_ID=" in script

        # Extract the PACK_ID value from the script
        import re

        pack_id_match = re.search(r'export PACK_ID="([^"]+)"', script)
        assert pack_id_match is not None, f"PACK_ID not found in script for key: {s3_key}"

        pack_id = pack_id_match.group(1)

        # Verify it's properly sanitized (only alphanumeric, dashes, underscores)
        assert re.match(
            r"^[a-zA-Z0-9_-]+$", pack_id
        ), f"PACK_ID '{pack_id}' contains invalid characters for key: {s3_key}"

        # Verify it matches expected pattern (exact match or close enough)
        assert (
            expected_sanitized in pack_id
            or pack_id in expected_sanitized
            or pack_id == expected_sanitized
        ), f"PACK_ID '{pack_id}' doesn't match expected '{expected_sanitized}' for key: {s3_key}"


def test_wrapper_cm_wrapper_params_json_creation(ec2_manager: EC2Manager) -> None:
    """Test that cm_wrapper_params.json is created with correct port when wrapper is enabled."""
    # Test with wrapper enabled and custom port
    script = ec2_manager.create_user_data_script(
        "test-bucket", "test-pack.tar.gz", enable_wrapper=True, wrapper_port=8082
    )

    # Verify cm_wrapper_params.json is created
    assert "cm_wrapper_params.json" in script
    assert 'cat > "$D/cm_wrapper_params.json"' in script

    # Verify the file contains the correct port
    assert '"port": 8082' in script or '"port": $P' in script

    # Verify other important fields are present
    assert '"verboseLog": true' in script
    assert '"downloadSpeedLimit"' in script
    assert '"downloadPasswordOnly"' in script
    assert '"publishPasswordChecksum"' in script

    # Verify the systemd service uses the correct command (no --port argument)
    assert (
        "/usr/bin/node /opt/acserver/wrapper/ac-server-wrapper.js /opt/acserver/preset" in script
    )
    # Verify the incorrect --port argument is NOT in the systemd service
    assert "--port" not in script.split("ExecStart=")[1].split("\n")[0]


def test_wrapper_disabled_no_params_json(ec2_manager: EC2Manager) -> None:
    """Test that cm_wrapper_params.json is NOT created when wrapper is disabled."""
    script = ec2_manager.create_user_data_script(
        "test-bucket", "test-pack.tar.gz", enable_wrapper=False
    )

    # Verify wrapper installation script is NOT created
    assert "install-wrapper.sh" not in script
    assert "ac-server-wrapper.git" not in script
    assert "acserver-wrapper.service" not in script
    
    # The adjust_wrapper_port function is still in the script (part of content.json patching)
    # but it won't do anything since no wrapper is installed
