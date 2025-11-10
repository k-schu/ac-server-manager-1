# Content Manager Download Feature via ac-server-wrapper

This document explains how the ac-server-wrapper integration enables Content Manager clients to automatically download missing cars, tracks, skins, and weather from your Assetto Corsa server.

## Overview

When you deploy a server with `--enable-wrapper` (enabled by default), the system:

1. **Installs Node.js 20** on the server
2. **Clones ac-server-wrapper** from https://github.com/gro-ove/ac-server-wrapper
3. **Creates configuration files** for the wrapper
4. **Sets up a systemd service** to run the wrapper
5. **Opens port 8082** in the security group for wrapper HTTP traffic
6. **Patches content.json files** to fix Windows absolute paths
7. **Copies content files** to the `cm_content` directory for serving

## How It Works

### Architecture

```
Content Manager Client
        ↓ (1) Request server info
ac-server-wrapper (port 8082)
        ↓ (2) Forward to AC server
AC Server (ports 8081, 9600)
        ↓ (3) Return server info + content list
ac-server-wrapper
        ↓ (4) Add download URLs from content.json
Content Manager Client
        ↓ (5) Download missing content from wrapper
ac-server-wrapper (serves files from cm_content/)
```

### Configuration Files

The wrapper installation creates these files:

**`/opt/acserver/preset/cm_wrapper_params.json`**
```json
{
  "port": 8082,
  "verboseLog": true,
  "downloadSpeedLimit": 1000000,
  "downloadPasswordOnly": false,
  "publishPasswordChecksum": true
}
```

**`/opt/acserver/preset/cm_content/`** - Directory containing:
- `content.json` - Maps content IDs to downloadable files
- Content files (cars, tracks, skins as ZIP files)

### content.json Structure

The `content.json` file tells Content Manager where to download missing content:

```json
{
  "cars": {
    "ks_ferrari_458": {
      "version": "1.0",
      "file": "ks_ferrari_458.zip",
      "skins": {
        "white": {
          "file": "ks_ferrari_458_white_skin.zip"
        }
      }
    },
    "custom_car": {
      "version": "2.1",
      "url": "https://example.com/downloads/custom_car.zip"
    }
  },
  "track": {
    "version": "1.5",
    "file": "spa.zip"
  },
  "weather": {
    "sol_01_scattered_clouds": {
      "file": "sol_01_scattered_clouds.zip"
    }
  }
}
```

**Key Points:**
- Use `"file": "filename.zip"` to serve from the server's `cm_content/` directory
- Use `"url": "https://..."` to redirect downloads to external hosting
- `"version"` is optional but recommended for cache management
- Files must be in ZIP format

## Automatic Content Patching

The deployment automatically patches any existing `content.json` files in your server pack:

1. **Detects Windows absolute paths** (e.g., `C:\Users\...` or `\\server\share`)
2. **Finds matching files** in the extracted pack
3. **Copies files to `cm_content/`** directory
4. **Rewrites paths** to relative references
5. **Creates backups** (`.bak` files)

This ensures Content Manager server packs created on Windows work correctly on Linux.

## Using the Feature

### Basic Deployment (Wrapper Enabled by Default)

```bash
# Deploy with wrapper on default port 8082
ac-server-manager deploy my-server-pack.tar.gz
```

### Custom Port

```bash
# Deploy with wrapper on custom port
ac-server-manager deploy my-server-pack.tar.gz --wrapper-port 9000
```

### Disable Wrapper

```bash
# Deploy without wrapper
ac-server-manager deploy my-server-pack.tar.gz --no-enable-wrapper
```

## Adding Custom Content for Downloads

If you want to make additional content downloadable, you have two options:

### Option 1: Package in Server Pack

Include a `content.json` file in your Content Manager server pack before deployment:

1. Create `cm_content/` directory in your pack
2. Add `cm_content/content.json` with your content mappings
3. Add ZIP files of your cars/tracks to `cm_content/`
4. Create the server pack and deploy

### Option 2: Add to Running Server

SSH into your server and manually add content:

```bash
# SSH to server
ssh -i your-key.pem ubuntu@your-server-ip

# Navigate to cm_content directory
cd /opt/acserver/preset/cm_content/

# Create or edit content.json
sudo nano content.json

# Upload your content ZIP files
# (use scp from your local machine)
```

Then restart the wrapper:
```bash
sudo systemctl restart acserver-wrapper
```

## Monitoring and Troubleshooting

### Check Wrapper Status

```bash
# Check if wrapper is running
sudo systemctl status acserver-wrapper

# View wrapper logs
sudo journalctl -u acserver-wrapper -n 50 -f

# Check wrapper installation log
sudo cat /var/log/acserver-wrapper-install.log

# Check wrapper stdout
sudo tail -f /var/log/acserver-wrapper-stdout.log

# Check wrapper stderr
sudo tail -f /var/log/acserver-wrapper-stderr.log
```

### Common Issues

**Wrapper not starting:**
- Check Node.js installation: `node --version`
- Verify wrapper files exist: `ls -la /opt/acserver/wrapper/`
- Check configuration: `cat /opt/acserver/preset/cm_wrapper_params.json`

**Content not downloading:**
- Verify content.json exists: `cat /opt/acserver/preset/cm_content/content.json`
- Check file permissions: `ls -la /opt/acserver/preset/cm_content/`
- Verify port 8082 is open: `sudo ss -tlnp | grep 8082`

**Wrong port:**
- The wrapper port is configured in `cm_wrapper_params.json`, not as a command-line argument
- Default is 8082, which is opened in the security group
- If you change the port, update both the config file and security group

## Technical Details

### Port Configuration

The wrapper port MUST be configured in `cm_wrapper_params.json`. The wrapper does not accept a `--port` command-line argument.

**Correct:**
```bash
# In cm_wrapper_params.json
{"port": 8082, ...}

# systemd service
ExecStart=/usr/bin/node /opt/acserver/wrapper/ac-server-wrapper.js /opt/acserver/preset
```

**Incorrect:**
```bash
# This will NOT work
ExecStart=/usr/bin/node /opt/acserver/wrapper/ac-server-wrapper.js --port 8082 /opt/acserver/preset
```

### systemd Service

The wrapper runs as a systemd service with these properties:

- **Service Name:** `acserver-wrapper.service`
- **Working Directory:** `/opt/acserver/wrapper`
- **Preset Directory:** `/opt/acserver/preset`
- **Restart Policy:** On failure, 10-second delay
- **Logs:** 
  - stdout: `/var/log/acserver-wrapper-stdout.log`
  - stderr: `/var/log/acserver-wrapper-stderr.log`

### Content Patching Process

The deployment includes a Python script that:

1. Walks the entire server pack directory tree
2. Finds all `content.json` files
3. For each file:
   - Parses JSON (creates `.bak` backup)
   - Recursively processes all values
   - Detects Windows paths in `"file"` fields only (not `"url"`)
   - Searches for matching files by basename
   - Copies files to `cm_content/`
   - Updates paths to relative references
   - Saves patched JSON

This is completely automatic and requires no user intervention.

## Best Practices

1. **Test locally first:** Test your content.json structure with ac-server-wrapper locally before deploying
2. **Use version numbers:** Include version in content.json for proper cache invalidation
3. **Optimize file sizes:** Compress textures and use appropriate formats to minimize download times
4. **External hosting for large files:** Use `"url"` for very large track downloads (>100MB)
5. **Monitor bandwidth:** The wrapper has downloadSpeedLimit (default 1MB/s) to prevent overwhelming the server
6. **Keep logs:** Wrapper logs are useful for debugging content download issues

## Security Considerations

- **downloadPasswordOnly: false** - Content can be downloaded without server password (default)
- **downloadPasswordOnly: true** - Requires server password to download content
- **publishPasswordChecksum: true** - Publishes SHA-1 hash of password for client validation
- **Port 8082** - Open to internet by default; wrapper handles HTTP requests

## Performance

- **Caching:** Wrapper caches AC server responses (≈1ms vs ≈20ms)
- **Compression:** Responses use gzip compression
- **Speed limiting:** Downloads limited to 1MB/s by default to maintain gameplay quality
- **Non-blocking installation:** Wrapper installs asynchronously; server starts immediately

## References

- **ac-server-wrapper GitHub:** https://github.com/gro-ove/ac-server-wrapper
- **Content Manager:** https://assettocorsa.club/content-manager.html
- **Assetto Corsa Server:** Official server documentation

## Support

If you encounter issues with content downloads:

1. Check wrapper logs (see Monitoring section)
2. Verify content.json structure matches examples
3. Ensure files exist in cm_content/ directory
4. Check security group allows port 8082
5. Open an issue with logs and configuration
