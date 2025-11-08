# AC Server Manager

Automated deployment tool for Assetto Corsa dedicated servers on AWS. This tool handles the complete lifecycle of deploying, managing, and updating Assetto Corsa servers using AWS EC2 and S3.

## Features

- 🚀 **Fully Automated Deployment**: Deploy Assetto Corsa servers to AWS with a single command
- 📦 **Content Manager Integration**: Direct support for Content Manager's "Server -> Pack ZIP" functionality
- 💰 **Cost-Optimized**: Uses t3.small instances suitable for 2-8 players at minimal AWS cost
- 🔄 **Easy Updates**: Redeploy with new server packs without manual intervention
- 🎮 **Server Lifecycle Management**: Start, stop, and terminate servers as needed
- ☁️ **S3 Storage**: Automatic pack file storage and retrieval

## Prerequisites

- Python 3.9 or higher
- [UV](https://github.com/astral-sh/uv) package manager (recommended)
- AWS Account with appropriate permissions
- AWS credentials configured (`~/.aws/credentials` or environment variables)

## Installation

### Using UV (Recommended)

UV is a fast Python package installer and resolver. Install UV first:

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then install AC Server Manager:

```bash
# Clone the repository
git clone https://github.com/k-schu/ac-server-manager-1.git
cd ac-server-manager-1

# Create virtual environment and install with UV
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/k-schu/ac-server-manager-1.git
cd ac-server-manager-1

# Install
pip install -e .
```

## AWS Setup

### Required AWS Permissions

Your AWS credentials need the following permissions:
- EC2: `DescribeInstances`, `RunInstances`, `TerminateInstances`, `StopInstances`, `StartInstances`, `DescribeImages`, `CreateSecurityGroup`, `AuthorizeSecurityGroupIngress`, `DescribeSecurityGroups`
- S3: `CreateBucket`, `PutObject`, `GetObject`, `ListBucket`, `DeleteObject`

**For automatic IAM role creation (optional, when using `--create-iam` flag):**
- IAM: `CreateRole`, `GetRole`, `CreateInstanceProfile`, `GetInstanceProfile`, `AddRoleToInstanceProfile`, `PutRolePolicy`

Note: IAM permissions are only required if you use the `--create-iam` flag to automatically create IAM resources. You can alternatively create IAM resources manually and pass them via `--iam-instance-profile`.

### AWS Configuration

Configure your AWS credentials:

```bash
aws configure
```

Or set environment variables:

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

## Usage

### Creating a Server Pack

1. Open Assetto Corsa Content Manager
2. Go to **Server** tab
3. Configure your server settings
4. Click **Pack** -> **Create server package**
5. Save the `.tar.gz` file

### Deploying a Server

Deploy your server pack to AWS:

```bash
ac-server-manager deploy server-pack.tar.gz
```

With custom options:

```bash
ac-server-manager deploy server-pack.tar.gz \
  --region us-west-2 \
  --instance-type t3.small \
  --bucket my-ac-servers \
  --instance-name my-race-server \
  --key-name my-ssh-key
```

### S3 Access Options

The EC2 instance needs permissions to download the server pack from S3. There are two ways to configure this:

#### Option 1: Automatic IAM Role Creation (Recommended)

Use the `--create-iam` flag to automatically create an IAM role and instance profile with minimal S3 permissions:

```bash
ac-server-manager deploy server-pack.tar.gz --create-iam
```

Optionally specify custom names:

```bash
ac-server-manager deploy server-pack.tar.gz \
  --create-iam \
  --iam-role-name my-custom-role \
  --iam-instance-profile-name my-custom-profile
```

**Requirements:**
- Your AWS credentials must have IAM permissions to create roles and instance profiles
- Creates a role with trust policy for EC2 service
- Attaches minimal inline policy: `s3:GetObject` on bucket/* and `s3:ListBucket` on bucket
- Resources are reused if they already exist (idempotent)

#### Option 2: Use Existing IAM Instance Profile

If you have an existing IAM instance profile with S3 access, you can use it:

```bash
ac-server-manager deploy server-pack.tar.gz \
  --iam-instance-profile my-existing-profile
```

The instance profile must have permissions for:
- `s3:GetObject` on your bucket and objects
- `s3:ListBucket` on your bucket

**Note:** If `--iam-instance-profile` is provided, it takes precedence over `--create-iam`.

The server will be deployed and available at the public IP address shown in the output. The server is accessible on:
- UDP/TCP Port 9600 (game traffic)
- TCP Port 8081 (HTTP API)

### Managing Your Server

**Stop a running server:**
```bash
ac-server-manager stop
```

**Start a stopped server:**
```bash
ac-server-manager start
```

**Terminate a server (permanent):**
```bash
ac-server-manager terminate
```

**Redeploy with a new pack:**
```bash
ac-server-manager redeploy new-server-pack.tar.gz
```

You can use the same IAM options with redeploy:

```bash
ac-server-manager redeploy new-server-pack.tar.gz --create-iam
```

### Finding Your Server in Content Manager

After deployment:
1. Note the public IP address from the deployment output
2. In Content Manager, go to **Online** -> **LAN**
3. Or manually connect using the IP address and port 9600

## Architecture

### Instance Type Selection

The default instance type is **t3.small** which provides:
- 2 vCPUs
- 2 GB RAM
- ~$15/month if running 24/7
- Suitable for 2-8 players

For larger servers (8-16 players), consider:
- **t3.medium**: 2 vCPUs, 4 GB RAM (~$30/month)
- **t3.large**: 2 vCPUs, 8 GB RAM (~$60/month)

### Cost Optimization

To minimize costs:
1. **Stop servers when not in use**: Use `ac-server-manager stop` when not racing
2. **Use on-demand pricing**: Only pay when the server is running
3. **Terminate unused instances**: Use `ac-server-manager terminate` to permanently remove servers
4. **Regional selection**: Choose regions closer to your players for better latency

Estimated costs:
- **Storage (S3)**: ~$0.023/GB/month for server packs
- **EC2 t3.small**: ~$0.0208/hour when running
- **Data transfer**: First 100 GB free per month

### Deployment Process

1. **S3 Upload**: Server pack is uploaded to S3
2. **Security Group**: Creates/reuses security group with game ports open
3. **EC2 Launch**: Launches Ubuntu instance with appropriate configuration
4. **Initialization**: Downloads pack from S3, extracts, and starts server
5. **Systemd Service**: Server runs as a systemd service for automatic restart
6. **Post-Boot Validation**: Automated validation ensures server is running correctly:
   - **Process Check**: Verifies acServer process is running
   - **Port Validation**: Confirms TCP/UDP 9600 and TCP 8081 are listening
   - **Log Analysis**: Scans server logs for configuration errors or missing content
   - **Exit Codes**: Returns non-zero exit code if validation fails, ensuring deployment automation detects issues

## Development

### Setup Development Environment with UV

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov

# Type checking
mypy src/ac_server_manager

# Code formatting
black src/ tests/

# Linting
ruff check src/ tests/
```

### Project Structure

```
ac-server-manager-1/
├── src/
│   └── ac_server_manager/
│       ├── __init__.py
│       ├── cli.py           # Command-line interface
│       ├── config.py        # Configuration management
│       ├── deployer.py      # Deployment orchestration
│       ├── ec2_manager.py   # EC2 operations
│       └── s3_manager.py    # S3 operations
├── tests/
│   ├── test_config.py
│   ├── test_deployer.py
│   ├── test_ec2_manager.py
│   └── test_s3_manager.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Running Tests

```bash
# Install test dependencies
uv pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage report
pytest --cov=ac_server_manager --cov-report=html

# Run specific test file
pytest tests/test_deployer.py

# Run specific test
pytest tests/test_deployer.py::test_deploy_success
```

## Troubleshooting

### Post-Deployment Validation

After deploying a server, the instance runs an automated validation process that checks:
- Server process is running
- Required ports are listening (TCP/UDP 9600, TCP 8081)
- HTTP endpoint is responding
- Server logs for common errors

The validation results are saved to `/opt/acserver/deploy-status.json` on the instance.

#### Checking Deployment Status

To verify your deployment was successful:

1. **SSH into the instance:**
   ```bash
   ssh -i <your-key>.pem ubuntu@<public-ip>
   ```

2. **Check the status file:**
   ```bash
   cat /opt/acserver/deploy-status.json
   ```
   
   A successful deployment will show:
   ```json
   {
     "success": true,
     "timestamp": "2024-01-15T12:34:56+00:00",
     "public_ip": "1.2.3.4",
     "ports": {
       "tcp": 9600,
       "udp": 9600,
       "http": 8081
     },
     "error_messages": []
   }
   ```

3. **Check deployment logs:**
   ```bash
   cat /var/log/acserver-deploy.log
   ```

4. **Check systemd service status:**
   ```bash
   systemctl status acserver
   ```

5. **View service logs:**
   ```bash
   journalctl -u acserver -n 50
   ```

### Common Deployment Issues

#### Missing Linux Binary

**Error:** "Windows PE binary detected" or "No acServer binary found"

**Cause:** The server pack contains a Windows binary instead of a Linux binary, or the binary is missing.

**Solution:**
- Ensure you're using a Linux-compatible Assetto Corsa dedicated server pack
- If you only have Windows binaries, consider using Wine or Proton (advanced)
- Verify the pack was exported correctly from Content Manager

#### S3 Permission Denied

**Error:** "Failed to download pack from S3"

**Cause:** The EC2 instance doesn't have permission to access the S3 bucket.

**Solutions:**
1. **Use automatic IAM creation (recommended):**
   ```bash
   ac-server-manager deploy server-pack.tar.gz --create-iam
   ```

2. **Provide an existing IAM instance profile:**
   ```bash
   ac-server-manager deploy server-pack.tar.gz --iam-instance-profile my-profile
   ```

3. **Make the S3 object public (not recommended for production):**
   ```bash
   aws s3api put-object-acl --bucket <bucket> --key <key> --acl public-read
   ```

The instance profile must have these permissions:
- `s3:GetObject` on `arn:aws:s3:::<bucket>/*`
- `s3:ListBucket` on `arn:aws:s3:::<bucket>`

#### Missing Libraries

**Error:** "error while loading shared libraries" in logs

**Cause:** Required 32-bit libraries are missing.

**Solution:** The deployment script automatically installs `lib32gcc-s1` and `lib32stdc++6`. If issues persist, SSH into the instance and manually install additional libraries:
```bash
sudo apt-get install -y lib32gcc-s1 lib32stdc++6 libc6-i386
```

#### Port Binding Errors

**Error:** "failed to bind" or "address already in use"

**Cause:** Another process is using the required ports.

**Solution:**
1. Check what's using the ports:
   ```bash
   sudo ss -tlnp | grep 9600
   sudo ss -ulnp | grep 9600
   ```

2. Stop conflicting services or redeploy with a fresh instance.

#### Server Process Not Running

**Error:** "acServer process is not running"

**Causes:**
- Binary crashed on startup
- Missing dependencies
- Configuration errors

**Troubleshooting steps:**
1. Check systemd logs for crash details:
   ```bash
   journalctl -u acserver -n 100
   ```

2. Try running manually to see errors:
   ```bash
   cd /opt/acserver
   sudo -u root ./acServer
   ```

3. Check binary architecture:
   ```bash
   file /opt/acserver/acServer
   ldd /opt/acserver/acServer
   ```

### Server Not Visible in Content Manager

- Verify security group allows UDP/TCP port 9600
- Check EC2 instance is running: `aws ec2 describe-instances`
- Wait 2-3 minutes for server initialization to complete
- Check deployment status using steps above
- Verify server process is running and ports are listening

### Deployment Fails

- Verify AWS credentials are configured correctly
- Check you have necessary AWS permissions
- Ensure the pack file is a valid Content Manager export
- Check AWS service limits haven't been reached
- Review `/var/log/acserver-deploy.log` for detailed error messages
- Check `/opt/acserver/deploy-status.json` for validation results

### High AWS Costs

- Stop instances when not in use
- Delete old server packs from S3
- Use appropriate instance types for player count
- Monitor usage in AWS Cost Explorer

## Security Considerations

- The default security group allows connections from any IP (0.0.0.0/0)
- Consider restricting SSH access (port 22) to known IPs
- Use SSH keys for instance access (specify `--key-name`)
- Regularly update and patch the server instances
- Don't commit AWS credentials to version control

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/k-schu/ac-server-manager-1/issues
- Assetto Corsa Content Manager: https://assettocorsa.club/content-manager.html

## Acknowledgments

- Assetto Corsa and Kunos Simulazioni
- Content Manager by x4fab
