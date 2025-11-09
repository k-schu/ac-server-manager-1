#!/usr/bin/env python3
"""
AssettoServer Pack Preparation Tool

This script converts Content Manager server packs to AssettoServer-compatible format.
AssettoServer uses a different structure and configuration approach from the default
Assetto Corsa dedicated server.

Usage:
    python tools/assetto_server_prepare.py <pack_file> <output_directory>

Arguments:
    pack_file: Path to Content Manager pack file (.tar.gz or .zip)
    output_directory: Destination directory for AssettoServer data

The script will:
1. Extract the Content Manager pack
2. Reorganize content into AssettoServer structure:
   - cfg/ - Server configuration files
   - content/ - Track and car data
3. Generate AssettoServer configuration (extra_cfg.yml)
"""

import argparse
import logging
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AssettoServerPreparer:
    """Prepares Content Manager packs for AssettoServer deployment."""

    def __init__(self, pack_file: Path, output_dir: Path):
        """Initialize preparer.

        Args:
            pack_file: Path to Content Manager pack
            output_dir: Destination for AssettoServer data
        """
        self.pack_file = pack_file
        self.output_dir = output_dir
        self.temp_dir = output_dir / "temp_extract"

    def prepare(self) -> bool:
        """Prepare AssettoServer data from Content Manager pack.

        Returns:
            True if preparation succeeded, False otherwise
        """
        try:
            logger.info(f"Preparing AssettoServer data from {self.pack_file}")

            # Create output directory structure
            self._create_directory_structure()

            # Extract pack
            if not self._extract_pack():
                return False

            # Copy configuration files
            if not self._copy_configuration():
                return False

            # Copy content (tracks and cars)
            if not self._copy_content():
                return False

            # Generate AssettoServer configuration
            if not self._generate_assettoserver_config():
                return False

            # Cleanup temp directory
            self._cleanup()

            logger.info(f"✓ AssettoServer data prepared successfully in {self.output_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to prepare AssettoServer data: {e}")
            return False

    def _create_directory_structure(self) -> None:
        """Create AssettoServer directory structure."""
        logger.info("Creating directory structure...")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "cfg").mkdir(exist_ok=True)
        (self.output_dir / "content").mkdir(exist_ok=True)
        (self.output_dir / "content" / "cars").mkdir(exist_ok=True)
        (self.output_dir / "content" / "tracks").mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)

    def _extract_pack(self) -> bool:
        """Extract Content Manager pack.

        Returns:
            True if extraction succeeded, False otherwise
        """
        logger.info("Extracting pack file...")

        try:
            if self.pack_file.suffix == ".zip":
                with zipfile.ZipFile(self.pack_file, "r") as zip_ref:
                    zip_ref.extractall(self.temp_dir)
            elif self.pack_file.suffix == ".gz" or self.pack_file.name.endswith(".tar.gz"):
                with tarfile.open(self.pack_file, "r:gz") as tar_ref:
                    tar_ref.extractall(self.temp_dir)
            else:
                logger.error(f"Unsupported pack format: {self.pack_file.suffix}")
                return False

            logger.info("✓ Pack extracted successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to extract pack: {e}")
            return False

    def _copy_configuration(self) -> bool:
        """Copy configuration files from extracted pack.

        Returns:
            True if copy succeeded, False otherwise
        """
        logger.info("Copying configuration files...")

        try:
            cfg_source = self.temp_dir / "cfg"
            cfg_dest = self.output_dir / "cfg"

            if cfg_source.exists():
                # Copy all configuration files
                for cfg_file in cfg_source.glob("*"):
                    if cfg_file.is_file():
                        shutil.copy2(cfg_file, cfg_dest)
                        logger.debug(f"  Copied {cfg_file.name}")
            else:
                logger.warning("No cfg directory found in pack")

            logger.info("✓ Configuration files copied")
            return True

        except Exception as e:
            logger.error(f"Failed to copy configuration: {e}")
            return False

    def _copy_content(self) -> bool:
        """Copy content (tracks and cars) from extracted pack.

        Returns:
            True if copy succeeded, False otherwise
        """
        logger.info("Copying content files...")

        try:
            content_dest = self.output_dir / "content"

            # Copy cars
            cars_source = self.temp_dir / "content" / "cars"
            if cars_source.exists():
                cars_dest = content_dest / "cars"
                for car_dir in cars_source.iterdir():
                    if car_dir.is_dir():
                        dest_car = cars_dest / car_dir.name
                        if dest_car.exists():
                            shutil.rmtree(dest_car)
                        shutil.copytree(car_dir, dest_car)
                        logger.debug(f"  Copied car: {car_dir.name}")
            else:
                logger.warning("No cars directory found in pack")

            # Copy tracks
            tracks_source = self.temp_dir / "content" / "tracks"
            if tracks_source.exists():
                tracks_dest = content_dest / "tracks"
                for track_dir in tracks_source.iterdir():
                    if track_dir.is_dir():
                        dest_track = tracks_dest / track_dir.name
                        if dest_track.exists():
                            shutil.rmtree(dest_track)
                        shutil.copytree(track_dir, dest_track)
                        logger.debug(f"  Copied track: {track_dir.name}")
            else:
                logger.warning("No tracks directory found in pack")

            logger.info("✓ Content files copied")
            return True

        except Exception as e:
            logger.error(f"Failed to copy content: {e}")
            return False

    def _generate_assettoserver_config(self) -> bool:
        """Generate AssettoServer-specific configuration.

        Returns:
            True if generation succeeded, False otherwise
        """
        logger.info("Generating AssettoServer configuration...")

        try:
            # Read server_cfg.ini to get basic server settings
            server_cfg_path = self.output_dir / "cfg" / "server_cfg.ini"
            server_name = "AssettoServer"
            max_clients = 24

            if server_cfg_path.exists():
                with open(server_cfg_path, "r") as f:
                    for line in f:
                        if line.startswith("NAME="):
                            server_name = line.split("=", 1)[1].strip()
                        elif line.startswith("MAX_CLIENTS="):
                            max_clients = int(line.split("=", 1)[1].strip())

            # Generate extra_cfg.yml for AssettoServer
            extra_cfg_path = self.output_dir / "extra_cfg.yml"
            extra_cfg_content = f"""# AssettoServer Extra Configuration
# Generated by AssettoServer Preparation Tool

# Server Settings
Server:
  Name: {server_name}
  MaxClients: {max_clients}
  WelcomeMessage: Welcome to {server_name}!

# Enable CSP (Custom Shaders Patch) features
EnableClientMessages: true
EnableAi: false
AiParams:
  MinAiSafetyLevel: 80
  MaxAiSafetyLevel: 100

# Additional plugins can be enabled here
# Example:
# EnablePlugins:
#   - LiveWeatherPlugin
#   - RandomWeatherPlugin
"""

            with open(extra_cfg_path, "w") as f:
                f.write(extra_cfg_content)

            logger.info(f"✓ Generated {extra_cfg_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate AssettoServer config: {e}")
            return False

    def _cleanup(self) -> None:
        """Clean up temporary extraction directory."""
        logger.info("Cleaning up temporary files...")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Prepare Content Manager packs for AssettoServer deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/assetto_server_prepare.py server-pack.tar.gz /opt/assettoserver/data
  python tools/assetto_server_prepare.py server-pack.zip ./assettoserver-data
        """,
    )
    parser.add_argument(
        "pack_file", type=Path, help="Path to Content Manager pack file (.tar.gz or .zip)"
    )
    parser.add_argument(
        "output_directory", type=Path, help="Destination directory for AssettoServer data"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate pack file exists
    if not args.pack_file.exists():
        logger.error(f"Pack file not found: {args.pack_file}")
        return 1

    # Prepare AssettoServer data
    preparer = AssettoServerPreparer(args.pack_file, args.output_directory)
    success = preparer.prepare()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
