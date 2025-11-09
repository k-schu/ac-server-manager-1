# AssettoServer Tools

This directory contains tools for preparing and deploying Assetto Corsa servers using the AssettoServer approach.

## assetto_server_prepare.py

Converts Content Manager server packs to AssettoServer-compatible format.

### Overview

AssettoServer uses a different directory structure and configuration approach from the default Assetto Corsa dedicated server. This tool automates the conversion process.

### Usage

```bash
python tools/assetto_server_prepare.py <pack_file> <output_directory>
```

**Arguments:**
- `pack_file`: Path to Content Manager pack file (.tar.gz or .zip)
- `output_directory`: Destination directory for AssettoServer data

**Options:**
- `-v, --verbose`: Enable verbose logging

### Examples

```bash
# Convert a tar.gz pack
python tools/assetto_server_prepare.py server-pack.tar.gz /opt/assettoserver/data

# Convert a zip pack with verbose output
python tools/assetto_server_prepare.py server-pack.zip ./assettoserver-data -v
```

### What it does

1. **Extracts** the Content Manager pack to a temporary directory
2. **Reorganizes content** into AssettoServer structure:
   - `cfg/` - Server configuration files (server_cfg.ini, entry_list.ini, etc.)
   - `content/cars/` - Car data and models
   - `content/tracks/` - Track data and models
3. **Generates** AssettoServer configuration:
   - `extra_cfg.yml` - AssettoServer-specific configuration
4. **Cleans up** temporary files

### Directory Structure

After preparation, the output directory will have:

```
output_directory/
├── cfg/
│   ├── server_cfg.ini
│   ├── entry_list.ini
│   └── ...
├── content/
│   ├── cars/
│   │   ├── car_name_1/
│   │   └── car_name_2/
│   └── tracks/
│       └── track_name/
└── extra_cfg.yml
```

### AssettoServer Integration

To use with AssettoServer deployment:

```bash
# Deploy with AssettoServer using the CLI
ac-server-manager deploy server-pack.tar.gz --use-assettoserver
```

The preparation tool is automatically uploaded to S3 and used during EC2 instance initialization when `--use-assettoserver` is enabled.

### References

- [AssettoServer Documentation](https://assettoserver.org/)
- [AssettoServer GitHub](https://github.com/compujuckel/AssettoServer)
- [Docker Hub - AssettoServer](https://hub.docker.com/r/compujuckel/assettoserver)
