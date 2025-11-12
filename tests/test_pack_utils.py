"""Tests for pack_utils module."""

import json
import tarfile
from pathlib import Path
from typing import Generator

import pytest

from ac_server_manager.pack_utils import extract_wrapper_port_from_pack


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def pack_with_wrapper_params(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test pack with cm_wrapper_params.json."""
    pack_path = temp_dir / "test-pack.tar.gz"

    # Create a temporary directory structure
    pack_contents = temp_dir / "pack_contents"
    pack_contents.mkdir()

    # Create cm_wrapper_params.json
    wrapper_params = {"port": 8090, "enabled": True}
    wrapper_params_file = pack_contents / "cm_wrapper_params.json"
    wrapper_params_file.write_text(json.dumps(wrapper_params))

    # Create tarball
    with tarfile.open(pack_path, "w:gz") as tar:
        tar.add(str(wrapper_params_file), arcname="cm_wrapper_params.json")

    yield pack_path


@pytest.fixture
def pack_with_nested_wrapper_params(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test pack with cm_wrapper_params.json in a subdirectory."""
    pack_path = temp_dir / "test-pack-nested.tar.gz"

    # Create a temporary directory structure
    pack_contents = temp_dir / "pack_contents_nested"
    pack_contents.mkdir()
    subdir = pack_contents / "server"
    subdir.mkdir()

    # Create cm_wrapper_params.json in subdirectory
    wrapper_params = {"port": 8095, "enabled": True}
    wrapper_params_file = subdir / "cm_wrapper_params.json"
    wrapper_params_file.write_text(json.dumps(wrapper_params))

    # Create tarball
    with tarfile.open(pack_path, "w:gz") as tar:
        tar.add(str(wrapper_params_file), arcname="server/cm_wrapper_params.json")

    yield pack_path


@pytest.fixture
def pack_without_wrapper_params(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test pack without cm_wrapper_params.json."""
    pack_path = temp_dir / "test-pack-no-wrapper.tar.gz"

    # Create a temporary directory structure
    pack_contents = temp_dir / "pack_contents_no_wrapper"
    pack_contents.mkdir()

    # Create a dummy file
    dummy_file = pack_contents / "dummy.txt"
    dummy_file.write_text("test")

    # Create tarball
    with tarfile.open(pack_path, "w:gz") as tar:
        tar.add(str(dummy_file), arcname="dummy.txt")

    yield pack_path


@pytest.fixture
def pack_with_invalid_wrapper_params(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test pack with invalid cm_wrapper_params.json."""
    pack_path = temp_dir / "test-pack-invalid.tar.gz"

    # Create a temporary directory structure
    pack_contents = temp_dir / "pack_contents_invalid"
    pack_contents.mkdir()

    # Create invalid cm_wrapper_params.json
    wrapper_params_file = pack_contents / "cm_wrapper_params.json"
    wrapper_params_file.write_text("not valid json{")

    # Create tarball
    with tarfile.open(pack_path, "w:gz") as tar:
        tar.add(str(wrapper_params_file), arcname="cm_wrapper_params.json")

    yield pack_path


@pytest.fixture
def pack_with_wrapper_params_no_port(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test pack with cm_wrapper_params.json missing port field."""
    pack_path = temp_dir / "test-pack-no-port.tar.gz"

    # Create a temporary directory structure
    pack_contents = temp_dir / "pack_contents_no_port"
    pack_contents.mkdir()

    # Create cm_wrapper_params.json without port
    wrapper_params = {"enabled": True}
    wrapper_params_file = pack_contents / "cm_wrapper_params.json"
    wrapper_params_file.write_text(json.dumps(wrapper_params))

    # Create tarball
    with tarfile.open(pack_path, "w:gz") as tar:
        tar.add(str(wrapper_params_file), arcname="cm_wrapper_params.json")

    yield pack_path


def test_extract_wrapper_port_from_pack_success(pack_with_wrapper_params: Path) -> None:
    """Test extracting wrapper port from pack with cm_wrapper_params.json."""
    port = extract_wrapper_port_from_pack(pack_with_wrapper_params)
    assert port == 8090


def test_extract_wrapper_port_from_nested_pack(pack_with_nested_wrapper_params: Path) -> None:
    """Test extracting wrapper port from pack with nested cm_wrapper_params.json."""
    port = extract_wrapper_port_from_pack(pack_with_nested_wrapper_params)
    assert port == 8095


def test_extract_wrapper_port_no_params_file(pack_without_wrapper_params: Path) -> None:
    """Test extracting wrapper port when cm_wrapper_params.json doesn't exist."""
    port = extract_wrapper_port_from_pack(pack_without_wrapper_params)
    assert port is None


def test_extract_wrapper_port_invalid_json(pack_with_invalid_wrapper_params: Path) -> None:
    """Test extracting wrapper port from pack with invalid JSON."""
    port = extract_wrapper_port_from_pack(pack_with_invalid_wrapper_params)
    assert port is None


def test_extract_wrapper_port_no_port_field(
    pack_with_wrapper_params_no_port: Path,
) -> None:
    """Test extracting wrapper port when port field is missing."""
    port = extract_wrapper_port_from_pack(pack_with_wrapper_params_no_port)
    assert port is None


def test_extract_wrapper_port_nonexistent_file(temp_dir: Path) -> None:
    """Test extracting wrapper port from nonexistent file."""
    nonexistent = temp_dir / "nonexistent.tar.gz"
    port = extract_wrapper_port_from_pack(nonexistent)
    assert port is None
