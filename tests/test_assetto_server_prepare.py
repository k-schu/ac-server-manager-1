"""Tests for AssettoServer preparation tool."""

import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest


class TestAssettoServerPrepare:
    """Test cases for AssettoServer preparation tool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def sample_pack_tar(self, temp_dir):
        """Create a sample Content Manager pack as tar.gz."""
        pack_dir = temp_dir / "pack_content"
        pack_dir.mkdir()

        # Create cfg directory with server_cfg.ini
        cfg_dir = pack_dir / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "server_cfg.ini").write_text("[SERVER]\nNAME=Test Server\nMAX_CLIENTS=20\n")

        # Create content directory with sample car and track
        content_dir = pack_dir / "content"
        content_dir.mkdir()

        cars_dir = content_dir / "cars"
        cars_dir.mkdir()
        car_dir = cars_dir / "ks_ferrari_458"
        car_dir.mkdir()
        (car_dir / "data.acd").write_text("car_data")

        tracks_dir = content_dir / "tracks"
        tracks_dir.mkdir()
        track_dir = tracks_dir / "spa"
        track_dir.mkdir()
        (track_dir / "models.ini").write_text("track_data")

        # Create tar.gz pack
        pack_file = temp_dir / "test-pack.tar.gz"
        with tarfile.open(pack_file, "w:gz") as tar:
            tar.add(pack_dir, arcname="")

        shutil.rmtree(pack_dir)
        return pack_file

    @pytest.fixture
    def sample_pack_zip(self, temp_dir):
        """Create a sample Content Manager pack as zip."""
        pack_dir = temp_dir / "pack_content"
        pack_dir.mkdir()

        # Create cfg directory with server_cfg.ini
        cfg_dir = pack_dir / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "server_cfg.ini").write_text("[SERVER]\nNAME=Zip Test Server\nMAX_CLIENTS=16\n")

        # Create content directory
        content_dir = pack_dir / "content"
        content_dir.mkdir()
        cars_dir = content_dir / "cars"
        cars_dir.mkdir()

        # Create zip pack
        pack_file = temp_dir / "test-pack.zip"
        with zipfile.ZipFile(pack_file, "w") as zipf:
            for file_path in pack_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(pack_dir)
                    zipf.write(file_path, arcname)

        shutil.rmtree(pack_dir)
        return pack_file

    def test_prepare_tar_pack(self, sample_pack_tar, temp_dir):
        """Test preparation of tar.gz pack."""
        # Import here to avoid issues if module doesn't exist yet
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from assetto_server_prepare import AssettoServerPreparer

        output_dir = temp_dir / "output"
        preparer = AssettoServerPreparer(sample_pack_tar, output_dir)

        success = preparer.prepare()

        assert success is True
        assert (output_dir / "cfg").exists()
        assert (output_dir / "content").exists()
        assert (output_dir / "content" / "cars").exists()
        assert (output_dir / "content" / "tracks").exists()
        assert (output_dir / "extra_cfg.yml").exists()

        # Check configuration was copied
        assert (output_dir / "cfg" / "server_cfg.ini").exists()

        # Check content was copied
        assert (output_dir / "content" / "cars" / "ks_ferrari_458").exists()
        assert (output_dir / "content" / "tracks" / "spa").exists()

    def test_prepare_zip_pack(self, sample_pack_zip, temp_dir):
        """Test preparation of zip pack."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from assetto_server_prepare import AssettoServerPreparer

        output_dir = temp_dir / "output"
        preparer = AssettoServerPreparer(sample_pack_zip, output_dir)

        success = preparer.prepare()

        assert success is True
        assert (output_dir / "cfg").exists()
        assert (output_dir / "extra_cfg.yml").exists()

    def test_prepare_nonexistent_pack(self, temp_dir):
        """Test preparation with nonexistent pack file."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from assetto_server_prepare import AssettoServerPreparer

        pack_file = temp_dir / "nonexistent.tar.gz"
        output_dir = temp_dir / "output"
        preparer = AssettoServerPreparer(pack_file, output_dir)

        success = preparer.prepare()

        # Should fail gracefully
        assert success is False

    def test_extra_cfg_generation(self, sample_pack_tar, temp_dir):
        """Test that extra_cfg.yml is generated correctly."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from assetto_server_prepare import AssettoServerPreparer

        output_dir = temp_dir / "output"
        preparer = AssettoServerPreparer(sample_pack_tar, output_dir)

        preparer.prepare()

        extra_cfg = output_dir / "extra_cfg.yml"
        assert extra_cfg.exists()

        content = extra_cfg.read_text()
        assert "Server:" in content
        assert "Name:" in content
        assert "MaxClients:" in content

    def test_cleanup_temp_directory(self, sample_pack_tar, temp_dir):
        """Test that temporary extraction directory is cleaned up."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from assetto_server_prepare import AssettoServerPreparer

        output_dir = temp_dir / "output"
        preparer = AssettoServerPreparer(sample_pack_tar, output_dir)

        preparer.prepare()

        # Temp directory should be cleaned up
        temp_extract_dir = output_dir / "temp_extract"
        assert not temp_extract_dir.exists()
