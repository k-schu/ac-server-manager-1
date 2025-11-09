# AssettoServer Integration Guide

This guide explains how to use the AssettoServer deployment feature in AC Server Manager.

## Overview

AC Server Manager now supports two deployment approaches:

1. **Traditional AC Server** (default) - Uses the standard Assetto Corsa dedicated server
2. **AssettoServer** - Uses the modern [AssettoServer](https://assettoserver.org/) Docker-based solution

## Why AssettoServer?

AssettoServer is a custom game server for Assetto Corsa developed with freeroam in mind. It provides:

- **Enhanced Security**: Fixes various security issues in the default server
- **Better Performance**: Optimized for freeroam gameplay
- **CSP Support**: Built-in Custom Shaders Patch features
- **Active Development**: Regular updates and community support
- **Plugin System**: Extensible with plugins for weather, AI traffic, and more
- **Docker-based**: Easier deployment and management

## Requirements

- AWS account with EC2 and S3 access
- Content Manager server pack (.tar.gz or .zip)
- IAM instance profile with S3 access (can be auto-created with `--create-iam`)

## Quick Start

### Deploy with AssettoServer

```bash
# Basic deployment
ac-server-manager deploy server-pack.tar.gz --use-assettoserver --create-iam

# With custom version
ac-server-manager deploy server-pack.tar.gz \
  --use-assettoserver \
  --assettoserver-version v0.0.55 \
  --create-iam

# With custom region and instance type
ac-server-manager deploy server-pack.tar.gz \
  --use-assettoserver \
  --region us-west-2 \
  --instance-type t3.medium \
  --key-name my-key \
  --create-iam
```

### Deploy with Traditional AC Server

```bash
# Traditional deployment (default)
ac-server-manager deploy server-pack.tar.gz --create-iam
```

## How It Works

### AssettoServer Deployment Process

1. **Pack Upload**: Your Content Manager pack is uploaded to S3
2. **Tool Upload**: The AssettoServer preparation tool is uploaded to S3
3. **EC2 Launch**: An Ubuntu EC2 instance is launched
4. **Bootstrap Script Execution**:
   - Installs Docker and required dependencies
   - Downloads pack and preparation tool from S3
   - Converts pack to AssettoServer format using the preparation tool
   - Creates Docker Compose configuration
   - Pulls AssettoServer Docker image
   - Starts AssettoServer container

### Directory Structure

After deployment, the EC2 instance has:

```
/opt/assettoserver/
├── docker-compose.yml          # Docker Compose configuration
├── server-pack.tar.gz          # Original pack (for reference)
├── assetto_server_prepare.py   # Preparation tool
├── deploy-status.json          # Deployment status
└── data/                       # AssettoServer data directory
    ├── cfg/                    # Server configuration
    │   ├── server_cfg.ini
    │   ├── entry_list.ini
    │   └── ...
    ├── content/                # Game content
    │   ├── cars/
    │   └── tracks/
    └── extra_cfg.yml           # AssettoServer-specific config
```

## Configuration

### Server Configuration

The traditional `server_cfg.ini` is preserved and used. AssettoServer reads this file for basic server settings.

### AssettoServer Configuration

Additional AssettoServer features are configured in `extra_cfg.yml`. The preparation tool generates a basic configuration, which you can customize by SSHing to the instance:

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cd /opt/assettoserver/data
sudo nano extra_cfg.yml
# After editing, restart the container:
cd /opt/assettoserver
sudo docker compose restart
```

### Example extra_cfg.yml Customizations

```yaml
# Enable weather plugins
EnablePlugins:
  - LiveWeatherPlugin
  - RandomWeatherPlugin

# Configure AI traffic
EnableAi: true
AiParams:
  MinAiSafetyLevel: 80
  MaxAiSafetyLevel: 100
  DefaultAiLevel: 95

# Enable time dilation
EnablePlugins:
  - TimeDilationPlugin

TimeDilationPlugin:
  TimeDilationTable:
    - SunAngle: -90
      Multiplier: 1.0
    - SunAngle: 0
      Multiplier: 20.0
    - SunAngle: 90
      Multiplier: 1.0
```

## Management Commands

All standard AC Server Manager commands work with AssettoServer deployments:

```bash
# Check server status
ac-server-manager status

# Stop the server
ac-server-manager stop

# Start the server
ac-server-manager start

# Terminate instance
ac-server-manager terminate

# Complete teardown
ac-server-manager terminate-all
```

## Monitoring and Logs

### Check Deployment Status

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cat /opt/assettoserver/deploy-status.json
```

### View Deployment Logs

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cat /var/log/assettoserver-deploy.log
```

### View AssettoServer Logs

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cd /opt/assettoserver
sudo docker compose logs -f
```

### Check Container Status

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
sudo docker ps
```

## Connecting to the Server

Connect using Content Manager or Assetto Corsa:

- **Server Address**: `<instance-ip>:9600`
- **HTTP Port**: `http://<instance-ip>:8081`

The HTTP port provides a web interface for server management (if enabled in AssettoServer configuration).

## Troubleshooting

### Deployment Failed

Check deployment logs:
```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cat /var/log/assettoserver-deploy.log
```

### Container Not Running

Check Docker logs:
```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cd /opt/assettoserver
sudo docker compose ps
sudo docker compose logs
```

### Configuration Issues

Validate configuration:
```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cd /opt/assettoserver/data
cat extra_cfg.yml
# Check for YAML syntax errors
python3 -c "import yaml; yaml.safe_load(open('extra_cfg.yml'))"
```

### Restart Server

```bash
ssh -i your-key.pem ubuntu@<instance-ip>
cd /opt/assettoserver
sudo docker compose restart
```

## Cost Considerations

AssettoServer deployment has similar costs to traditional AC server:

- **EC2 Instance**: t3.small (~$15/month if running 24/7)
- **S3 Storage**: ~$0.023/GB/month
- **Data Transfer**: First 100 GB free per month

The Docker overhead is minimal and doesn't significantly impact costs.

## Switching Between Deployment Types

You cannot switch an existing deployment between traditional and AssettoServer. To change:

1. Terminate the existing deployment: `ac-server-manager terminate`
2. Redeploy with desired type:
   ```bash
   # Switch to AssettoServer
   ac-server-manager deploy pack.tar.gz --use-assettoserver --create-iam
   
   # Switch to traditional
   ac-server-manager deploy pack.tar.gz --create-iam
   ```

## Advanced: Manual Preparation Tool Usage

You can use the preparation tool separately to convert packs locally:

```bash
python tools/assetto_server_prepare.py server-pack.tar.gz ./output-directory
```

This creates an AssettoServer-compatible directory structure that you can customize before deployment.

## Resources

- [AssettoServer Documentation](https://assettoserver.org/)
- [AssettoServer GitHub](https://github.com/compujuckel/AssettoServer)
- [AssettoServer Discord](https://discord.gg/uXEXRcSkyz)
- [Docker Hub - AssettoServer](https://hub.docker.com/r/compujuckel/assettoserver)

## Support

For issues specific to:
- **AC Server Manager**: Open an issue on the [GitHub repository](https://github.com/k-schu/ac-server-manager/issues)
- **AssettoServer**: Visit the [AssettoServer Discord](https://discord.gg/uXEXRcSkyz) or [GitHub Discussions](https://github.com/compujuckel/AssettoServer/discussions)
