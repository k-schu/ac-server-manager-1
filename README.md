# AC Server Manager

Purely vibecoded automated deployment tool for Assetto Corsa dedicated servers on AWS. Deploy, manage, and tear down Assetto Corsa servers with a single command. This was a learning exercise, a way to connect with friends, and prepare for upcoming events.

## Features

- 🚀 **One-command deployment** from Content Manager server packs
- ☁️ **AWS-powered** using EC2 and S3
- 💰 **Cost-optimized** with t3.small instances (~$15/month)
- 🔄 **Complete lifecycle** management (deploy, start, stop, terminate)
- 🧹 **Safe teardown** with `terminate-all` command
- 🐳 **AssettoServer support** - Deploy using AssettoServer Docker container

## Deployment Options

This tool supports two deployment approaches:

1. **Traditional Assetto Corsa Server** (default) - Uses the standard AC dedicated server with optional ac-server-wrapper
2. **AssettoServer** - Uses the modern [AssettoServer](https://assettoserver.org/) Docker-based solution with enhanced features

### AssettoServer Benefits

- Built-in CSP (Custom Shaders Patch) support
- Enhanced security and stability
- Active development and community support
- Plugin system for extensibility
- Better freeroam experience

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/k-schu/ac-server-manager.git
cd ac-server-manager

# Install with pip
uv pip install -e .
```

### AWS Credentials

Configure your AWS credentials with appropriate permissions:

```bash
aws configure
```

**Required AWS Permissions:**
- EC2: `DescribeInstances`, `RunInstances`, `TerminateInstances`, `StopInstances`, `StartInstances`
- S3: `CreateBucket`, `PutObject`, `GetObject`, `ListBucket`, `DeleteObject`, `DeleteBucket`
- IAM (optional, for `--create-iam`): `CreateRole`, `CreateInstanceProfile`, `PutRolePolicy`

### Basic Usage

**Deploy a traditional AC server:**
```bash
uv run ac-server-manager deploy server-pack.tar.gz --create-iam
```

**Deploy with AssettoServer:**
```bash
uv run ac-server-manager deploy server-pack.tar.gz --create-iam --use-assettoserver
```

**Check server status:**
```bash
ac-server-manager status
```

**Stop the server:**
```bash
ac-server-manager stop
```

**Start the server:**
```bash
ac-server-manager start
```

**Redeploy with a new pack:**
```bash
ac-server-manager redeploy new-server-pack.tar.gz
```

**Terminate instance only:**
```bash
ac-server-manager terminate
```

**Complete teardown (instance + S3 bucket):**
```bash
ac-server-manager terminate-all
```

### terminate-all Command

The `terminate-all` command safely tears down all infrastructure:

```bash
# Interactive confirmation (requires typing "TERMINATE")
ac-server-manager terminate-all

# Skip confirmation
ac-server-manager terminate-all --force

# Preview what would be deleted
ac-server-manager terminate-all --dry-run

# Specify resources explicitly
ac-server-manager terminate-all --instance-id i-1234567890abcdef0 --s3-bucket my-bucket

# Terminate instance only, keep S3 bucket
ac-server-manager terminate-all --skip-bucket
```

**Safety features:**
- Interactive confirmation requiring the literal word "TERMINATE" (case-sensitive)
- `--force` flag to skip confirmation for automation
- `--dry-run` flag to preview actions without deleting
- `--skip-bucket` to preserve S3 data
- Detailed logging of all operations

## Command Reference

| Command | Description |
|---------|-------------|
| `deploy <pack>` | Deploy AC server from Content Manager pack |
| `status` | Check server status and connectivity |
| `start` | Start a stopped server |
| `stop` | Stop a running server |
| `terminate` | Terminate the EC2 instance |
| `terminate-all` | **Terminate instance AND delete S3 bucket** |
| `redeploy <pack>` | Terminate and redeploy with new pack |

### Common Options

- `--region TEXT` - AWS region (default: us-east-1)
- `--instance-name TEXT` - Instance name tag (default: ac-server-instance)
- `--instance-id TEXT` - Explicit instance ID
- `--bucket TEXT` - S3 bucket name (default: ac-server-packs)
- `--create-iam` - Auto-create IAM role for S3 access
- `--key-name TEXT` - SSH key pair name

### AssettoServer Options

- `--use-assettoserver` - Deploy using AssettoServer instead of traditional AC server
- `--assettoserver-version TEXT` - AssettoServer Docker image version (default: v0.0.54)

**Example:**
```bash
ac-server-manager deploy server-pack.tar.gz --use-assettoserver --assettoserver-version v0.0.54
```

## Documentation

For detailed documentation, troubleshooting, and advanced usage, see:

- **[Full Documentation](docs/README_FULL.md)** - Complete guide with troubleshooting
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute
- **[Examples](EXAMPLES.md)** - Usage examples and recipes

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/ tests/
ruff check src/ tests/

# Type checking
mypy src/
```

## Architecture

- **EC2**: Ubuntu 22.04 LTS instances running Assetto Corsa server
- **S3**: Stores server pack files and bootstrap scripts
- **IAM**: Optional automatic role creation for secure S3 access
- **Security Groups**: Configured for AC server ports (9600 TCP/UDP, 8081 HTTP)

### Bootstrap Process

To handle large server configurations and avoid EC2's 16KB user-data limit, the deployment uses a two-stage bootstrap process:

1. **Bootstrap Upload**: The full deployment script (which can be 18+ KB) is uploaded to S3 at `bootstrap/bootstrap-{timestamp}-{uuid}.sh`
2. **Minimal User-Data**: EC2 instance launches with a minimal ~860 byte script that:
   - Downloads the bootstrap script from S3 using a presigned URL (valid for 1 hour)
   - Executes the full deployment script

This approach ensures reliable deployments regardless of pack size or configuration complexity.

## Cost Estimation

- **t3.small instance**: ~$0.0208/hour (~$15/month if running 24/7)
- **S3 storage**: ~$0.023/GB/month
- **Data transfer**: First 100 GB free per month

Stop instances when not in use to minimize costs!

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Issues**: https://github.com/k-schu/ac-server-manager/issues
- **Full Docs**: [docs/README_FULL.md](docs/README_FULL.md)

## References

This project supports both traditional Content Manager server deployments and modern AssettoServer deployments:

- **Content Manager**: https://assettocorsa.club/content-manager.html
- **AssettoServer**: https://assettoserver.org/
- **AssettoServer GitHub**: https://github.com/compujuckel/AssettoServer
- **AssettoServer Docker**: https://hub.docker.com/r/compujuckel/assettoserver

Please feel free to fork, contribute, and raise feature requests - this will help me learn!
