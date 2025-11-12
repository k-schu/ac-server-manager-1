"""Utilities for handling AC server pack files."""

import json
import logging
import tarfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_wrapper_port_from_pack(pack_file_path: Path) -> Optional[int]:
    """Extract wrapper port from cm_wrapper_params.json in the pack.

    Args:
        pack_file_path: Path to the server pack tar.gz file

    Returns:
        Wrapper port number if found in cm_wrapper_params.json, None otherwise
    """
    try:
        with tarfile.open(pack_file_path, "r:gz") as tar:
            # Look for cm_wrapper_params.json anywhere in the tarball
            for member in tar.getmembers():
                if member.name.endswith("cm_wrapper_params.json"):
                    logger.info(f"Found cm_wrapper_params.json at {member.name}")

                    # Extract and parse the JSON
                    file_obj = tar.extractfile(member)
                    if file_obj is None:
                        logger.warning(f"Could not extract {member.name}")
                        continue

                    try:
                        content = file_obj.read().decode("utf-8")
                        wrapper_params = json.loads(content)

                        # Extract port from the JSON
                        if "port" in wrapper_params:
                            port = int(wrapper_params["port"])
                            logger.info(f"Found wrapper port in pack: {port}")
                            return port
                        else:
                            logger.warning("cm_wrapper_params.json found but no 'port' field")
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Failed to parse cm_wrapper_params.json: {e}")
                        continue

            logger.info("No cm_wrapper_params.json found in pack")
            return None

    except (tarfile.TarError, OSError) as e:
        logger.error(f"Error reading pack file: {e}")
        return None
