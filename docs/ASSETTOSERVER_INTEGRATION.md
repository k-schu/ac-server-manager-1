# AssettoServer Integration Guide

This document explains how AC Server Manager integrates with [AssettoServer](https://assettoserver.org/), ensuring proper UDP port mapping, network configuration, and deployment best practices.

## Overview

AssettoServer is a custom game server for Assetto Corsa developed with freeroam gameplay in mind. It provides enhanced features, better security, and active community support compared to the default Assetto Corsa dedicated server.

This integration allows you to deploy AssettoServer using Content Manager server packs while benefiting from AssettoServer's improved functionality.

## What is AssettoServer?

AssettoServer is a modern, Docker-based server implementation for Assetto Corsa that provides:

- **Enhanced Security**: Fixes security vulnerabilities present in the default AC server
- **Custom Shaders Patch (CSP) Support**: Native support for CSP features and content
- **Plugin System**: Extensible architecture with plugins for weather, AI traffic, timing, and more
- **Active Development**: Regular updates and an engaged community
- **Better Freeroam Experience**: Optimized for freeroam gameplay with improved networking
- **Docker Deployment**: Containerized for easier management and deployment

For more information, visit the [official AssettoServer documentation](https://assettoserver.org/docs/intro).

## How It Works

### Content Manager Pack Conversion

AC Server Manager accepts standard Content Manager server packs (`.tar.gz` or `.zip` files) and automatically converts them to AssettoServer-compatible format:

1. **Pack Upload**: Your CM pack is uploaded to S3
2. **Extraction**: Pack is extracted on the EC2 instance
3. **Structure Conversion**: The `assetto_server_prepare.py` tool reorganizes content into AssettoServer's expected structure:
   - `cfg/` - Server configuration files (server_cfg.ini, entry_list.ini, etc.)
   - `content/` - Game content (cars and tracks)
   - `extra_cfg.yml` - AssettoServer-specific configuration

4. **Docker Deployment**: AssettoServer runs in a Docker container with proper port mappings

### Docker Compose Configuration

The deployment creates a `docker-compose.yml` with **explicit UDP port mapping** (critical for player connectivity):

```yaml
version: "3.9"

services:
  assettoserver:
    image: compujuckel/assettoserver:v0.0.54
    container_name: assettoserver
    ports:
      - "9600:9600/udp"    # Game port UDP - REQUIRED for players to connect
      - "9600:9600/tcp"    # Game port TCP
      - "8081:8081/tcp"    # HTTP API/interface
      - "8080:8080/tcp"    # File server for content downloads
    volumes:
      - ./data:/data
    environment:
      - TZ=UTC
    restart: unless-stopped
```

**Important**: The `/udp` suffix on port 9600 is **mandatory**. Without explicit UDP mapping, Docker will only map TCP, and players will not be able to connect to the server.

## AWS Security Group Configuration

For AssettoServer to be accessible, your EC2 security group must allow the following inbound traffic:

### Required Ports

| Port | Protocol | Description | Priority |
|------|----------|-------------|----------|
| 9600 | UDP | Game traffic | **Critical** |
| 9600 | TCP | Game traffic | **Critical** |
| 8081 | TCP | HTTP API/interface | Recommended |
| 8080 | TCP | File server | Recommended |
| 22 | TCP | SSH access | Optional |

### Security Group Rules Example

```bash
# Via AWS CLI
aws ec2 authorize-security-group-ingress \
    --group-id sg-xxxxx \
    --ip-permissions \
        IpProtocol=udp,FromPort=9600,ToPort=9600,IpRanges='[{CidrIp=0.0.0.0/0,Description="AC Game UDP"}]' \
        IpProtocol=tcp,FromPort=9600,ToPort=9600,IpRanges='[{CidrIp=0.0.0.0/0,Description="AC Game TCP"}]' \
        IpProtocol=tcp,FromPort=8081,ToPort=8081,IpRanges='[{CidrIp=0.0.0.0/0,Description="AC HTTP"}]' \
        IpProtocol=tcp,FromPort=8080,ToPort=8080,IpRanges='[{CidrIp=0.0.0.0/0,Description="AC File Server"}]'
```

**Note**: AC Server Manager automatically creates security groups with these rules when you deploy, but you should verify them if experiencing connectivity issues.

## Host Firewall Configuration

The deployment script automatically configures the Ubuntu firewall (ufw) to allow required ports:

```bash
# Automatically configured during deployment
ufw allow 9600/udp
ufw allow 9600/tcp
ufw allow 8081/tcp
ufw allow 8080/tcp
```

If you need to manually verify or reconfigure:

```bash
# Check firewall status
sudo ufw status

# Manually allow ports if needed
sudo ufw allow 9600/udp
sudo ufw allow 9600/tcp
sudo ufw allow 8081/tcp
sudo ufw allow 8080/tcp
```

## Network Load Balancer (NLB) Considerations

If you plan to use an AWS Network Load Balancer for production deployments:

- **UDP Support**: NLB supports UDP, but requires specific target group configuration
- **Health Checks**: Configure TCP health checks on port 8081 (HTTP endpoint)
- **Sticky Sessions**: Enable flow hash algorithm for UDP to maintain player connections
- **Costs**: NLB incurs hourly charges plus data processing charges

Example NLB configuration:
- **Protocol**: UDP on port 9600 → Target port 9600
- **Health Check**: TCP on port 8081
- **Attributes**: Enable cross-zone load balancing, enable connection termination

## Health Check Script

A health check script is available at `/usr/local/bin/check_assettoserver_instance.sh` (or `tools/check_assettoserver_instance.sh` in the repository).

### Running the Health Check

```bash
# On the EC2 instance
sudo bash /usr/local/bin/check_assettoserver_instance.sh

# Or locally (if copied from tools/)
bash tools/check_assettoserver_instance.sh
```

The script verifies:
1. ✓ Docker daemon is running
2. ✓ AssettoServer container is running
3. ✓ Required ports are listening (UDP 9600, TCP 9600, TCP 8081, TCP 8080)
4. ✓ HTTP endpoints are responding
5. ✓ Container logs show no critical errors
6. ✓ Deployment status is "started"

Exit codes:
- `0` - All checks passed, server is healthy
- `1` - One or more checks failed, troubleshooting needed

## Deployment Examples

### Basic Deployment

```bash
ac-server-manager deploy server-pack.tar.gz --use-assettoserver --create-iam
```

### Custom Region and Instance Type

```bash
ac-server-manager deploy server-pack.tar.gz \
    --use-assettoserver \
    --region us-west-2 \
    --instance-type t3.medium \
    --key-name my-ec2-key \
    --create-iam
```

### Specific AssettoServer Version

```bash
ac-server-manager deploy server-pack.tar.gz \
    --use-assettoserver \
    --assettoserver-version v0.0.55 \
    --create-iam
```

## Verifying Deployment

### 1. Check Deployment Status

```bash
# SSH to the instance
ssh -i your-key.pem ubuntu@<instance-ip>

# Check deployment status file
cat /opt/assettoserver/deploy-status.json

# Check deployment logs
cat /var/log/assettoserver-deploy.log
```

### 2. Verify Container is Running

```bash
# Check container status
docker ps

# View container logs
docker logs assettoserver

# Follow logs in real-time
docker logs -f assettoserver
```

### 3. Test Network Connectivity

From an external machine:

```bash
# Test UDP port (requires nmap-ncat)
nc -u -v -z <instance-ip> 9600

# Test TCP port
nc -v -z <instance-ip> 9600

# Test HTTP endpoint
curl http://<instance-ip>:8081/
```

### 4. Run Health Check

```bash
# On the instance
sudo bash /usr/local/bin/check_assettoserver_instance.sh
```

## Troubleshooting

### Players Cannot Connect

**Symptom**: Server appears online but players get connection timeout

**Common Causes**:
1. ❌ Security group doesn't allow UDP on port 9600
2. ❌ Docker compose missing `/udp` suffix on port mapping
3. ❌ Host firewall (ufw) blocking UDP traffic

**Solution**:
```bash
# 1. Verify security group rules in AWS console
# 2. Check docker-compose.yml has explicit UDP mapping
cat /opt/assettoserver/docker-compose.yml | grep "9600.*udp"

# 3. Check firewall
sudo ufw status | grep 9600

# 4. Verify ports are listening
ss -ulnp | grep 9600  # UDP
ss -tlnp | grep 9600  # TCP
```

### Container Fails to Start

**Symptom**: `docker ps` shows no running container

**Diagnosis**:
```bash
# Check container status (including stopped containers)
docker ps -a

# View container logs
docker logs assettoserver

# Check deployment logs
cat /var/log/assettoserver-deploy.log

# Verify data directory structure
ls -la /opt/assettoserver/data/
```

**Common Issues**:
- Missing or invalid server_cfg.ini
- Missing track or car content
- Incorrect extra_cfg.yml syntax

### Content Not Loading

**Symptom**: Server starts but tracks/cars don't load

**Diagnosis**:
```bash
# Verify content structure
ls -la /opt/assettoserver/data/content/cars/
ls -la /opt/assettoserver/data/content/tracks/

# Check container logs for missing content errors
docker logs assettoserver 2>&1 | grep -i "missing\|not found"
```

**Solution**: Ensure your Content Manager pack includes all required content (cars, tracks, track configs).

## Steam Authentication (Optional)

AssettoServer supports Steam authentication for an additional layer of security. This requires a Steam Web API key.

**Note**: Steam authentication is **optional** and not required for basic functionality. The current implementation does not configure Steam auth by default.

To enable Steam authentication:

1. Get a Steam Web API key from https://steamcommunity.com/dev/apikey
2. SSH to your instance and edit the server configuration:
   ```bash
   cd /opt/assettoserver/data/cfg
   sudo nano server_cfg.ini
   ```
3. Add the Steam settings:
   ```ini
   [STEAM]
   AUTH=1
   API_KEY=YOUR_STEAM_API_KEY_HERE
   ```
4. Restart the container:
   ```bash
   cd /opt/assettoserver
   sudo docker compose restart
   ```

For more details, see [AssettoServer Steam Authentication Docs](https://assettoserver.org/docs/misc/steam-auth).

## Advanced Configuration

### Customizing AssettoServer Features

AssettoServer provides additional features through `extra_cfg.yml`. After deployment, you can customize:

```bash
# SSH to instance
ssh -i your-key.pem ubuntu@<instance-ip>

# Edit AssettoServer configuration
cd /opt/assettoserver/data
sudo nano extra_cfg.yml

# Example customizations:
# - Enable weather plugins
# - Configure AI traffic
# - Enable time dilation
# - Add custom CSP settings

# Restart to apply changes
cd /opt/assettoserver
sudo docker compose restart
```

### Plugin System

AssettoServer supports plugins for extended functionality. See the [AssettoServer documentation](https://assettoserver.org/docs/intro) for available plugins and configuration.

## Reference Links

- **AssettoServer Official Site**: https://assettoserver.org/
- **AssettoServer Documentation**: https://assettoserver.org/docs/intro
- **Beginner's Guide**: https://assettoserver.org/docs/thebeginnersguide
- **Steam Authentication**: https://assettoserver.org/docs/misc/steam-auth
- **GitHub Repository**: https://github.com/compujuckel/AssettoServer
- **Docker Hub**: https://hub.docker.com/r/compujuckel/assettoserver
- **Discord Community**: https://discord.gg/uXEXRcSkyz

## Support

- **AC Server Manager Issues**: https://github.com/k-schu/ac-server-manager/issues
- **AssettoServer Support**: Discord community or GitHub discussions
- **AWS Support**: For infrastructure-related issues
