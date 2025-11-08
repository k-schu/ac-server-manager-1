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

### Server Not Visible in Content Manager

- Verify security group allows UDP/TCP port 9600
- Check EC2 instance is running: `aws ec2 describe-instances`
- Wait 2-3 minutes for server initialization to complete
- Check server logs by SSH'ing into the instance

### Deployment Fails

- Verify AWS credentials are configured correctly
- Check you have necessary AWS permissions
- Ensure the pack file is a valid Content Manager export
- Check AWS service limits haven't been reached
- **Check validation logs**: SSH into the instance and review `/var/log/acserver-deployment.log` for detailed validation results
- **Check systemd status**: Run `systemctl status acserver` to see service status
- **Review server logs**: Check `/opt/acserver/log/log.txt` for AC server errors

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
