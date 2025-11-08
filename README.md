# AC Server Manager

Automated AWS deployment for Assetto Corsa dedicated servers.

## Features

- 🚀 **Fully Automated Deployment**: Deploy Assetto Corsa servers to AWS EC2 with a single command
- 📦 **Content Manager Integration**: Uses server packs created with Content Manager's "Server → Pack ZIP" functionality
- ☁️ **AWS Integration**: Leverages EC2 for compute and S3 for pack storage
- 🔗 **Auto-Discovery**: Automatically captures and displays the acstuff.ru connection link
- 💰 **Cost-Optimized**: Uses t3.small instances (optimal for 2-8 players) with easy start/stop controls
- 🎮 **Player-Ready**: Servers are instantly visible and joinable in Content Manager

## Installation

### Using UV (Recommended)

```bash
# Clone the repository
git clone https://github.com/k-schu/ac-server-manager-1.git
cd ac-server-manager-1

# Install with UV
uv pip install -e .

# Or install with dev dependencies
uv pip install -e ".[dev]"
```

### Using pip

```bash
# Install from source
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Prerequisites

1. **AWS Account**: You need an active AWS account with permissions to:
   - Create EC2 instances
   - Create S3 buckets
   - Create security groups
   - Create IAM roles (for SSM access)

2. **AWS Credentials**: Configure your AWS credentials using one of these methods:
   ```bash
   # Option 1: AWS CLI
   aws configure
   
   # Option 2: Environment variables
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1
   
   # Option 3: AWS profiles
   # Edit ~/.aws/credentials and ~/.aws/config
   ```

3. **Server Pack**: Create a server pack using Content Manager:
   - Open Content Manager
   - Go to Server → Pack
   - Create a ZIP that includes:
     - `acServer.exe`
     - `cfg/` directory with server configuration
     - `content/` directory with tracks and cars
     - `system/` directory

## Usage

### Deploy a New Server

```bash
# Basic deployment
ac-deploy deploy /path/to/server-pack.zip

# With custom name and region
ac-deploy deploy /path/to/server-pack.zip --name my-ac-server --region us-west-2

# With custom instance type
ac-deploy deploy /path/to/server-pack.zip --instance-type t3.medium
```

The deployment process will:
1. Upload your server pack to S3
2. Create necessary security groups (if not exists)
3. Launch a Windows EC2 instance
4. Download and extract the pack on the instance
5. Start the Assetto Corsa server
6. Display the **acstuff.ru connection link** for players

### List All Servers

```bash
ac-deploy list
```

### Check Server Status

```bash
ac-deploy status i-1234567890abcdef0
```

This will show:
- Instance state
- Public IP address
- Server information including the **acstuff.ru link**

### Stop a Server (Save Costs)

```bash
ac-deploy stop i-1234567890abcdef0
```

Stopping a server keeps it available but stops billing for compute. Storage costs still apply.

### Start a Stopped Server

```bash
ac-deploy start i-1234567890abcdef0
```

### Terminate a Server (Permanent)

```bash
ac-deploy terminate i-1234567890abcdef0
```

⚠️ **Warning**: This permanently deletes the instance. The pack remains in S3.

### Redeploy with New Pack

```bash
ac-deploy redeploy i-1234567890abcdef0 /path/to/new-pack.zip
```

This terminates the old instance and creates a new one with the updated pack.

## Configuration

### Default Settings

- **Instance Type**: `t3.small` (2 vCPUs, 2 GB RAM) - optimal for 2-8 players
- **Region**: `us-east-1`
- **S3 Bucket**: `ac-server-packs`
- **Ports**:
  - HTTP: 8081
  - TCP: 9600
  - UDP: 9600
  - RDP: 3389 (for management)

### Custom Configuration

You can customize these settings via CLI options:

```bash
ac-deploy deploy pack.zip \
  --region eu-west-1 \
  --instance-type t3.medium \
  --bucket my-custom-bucket
```

### Environment Variables

Create a `.env` file in your project directory:

```env
AWS_PROFILE=my-profile
AWS_DEFAULT_REGION=us-east-1
```

## Cost Optimization

### Instance Costs (us-east-1)

- **t3.small**: ~$0.0208/hour (~$15/month if running 24/7)
- **t3.medium**: ~$0.0416/hour (~$30/month if running 24/7)

### Recommendations

1. **Stop when not in use**: `ac-deploy stop <instance-id>`
2. **Use t3.small for most cases**: Handles 2-8 players well
3. **Consider Reserved Instances**: For long-term savings if running 24/7
4. **Use S3 lifecycle policies**: Automatically delete old packs

### Estimated Monthly Costs

For a server running 12 hours/day:
- Instance (t3.small): ~$7.50
- Storage (S3): ~$0.50
- Data transfer: ~$1-5 (varies with usage)
- **Total**: ~$9-13/month

## How It Works

### Deployment Process

1. **Pack Upload**: Your server pack is uploaded to S3
2. **Instance Launch**: A Windows Server 2022 EC2 instance is created
3. **Automated Setup**: User data script:
   - Downloads the pack from S3
   - Extracts it to `C:\acserver`
   - Finds and starts `acServer.exe`
   - Monitors logs for the acstuff.ru link
   - Saves server info to `C:\ac-server-info\server-info.txt`
4. **Link Discovery**: The script captures the acstuff.ru link from server output
5. **SSM Access**: Uses AWS Systems Manager for remote command execution

### Server Information

Once deployed, the server info includes:
- **AC_SERVER_LINK**: The acstuff.ru link for Content Manager
- **PUBLIC_IP**: Server's public IP address
- **SERVER_STATUS**: Whether the server is running
- **PROCESS_ID**: The acServer.exe process ID
- **Ports**: HTTP, TCP, and UDP ports

## Development

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=ac_server_manager --cov-report=html

# Run specific test file
pytest tests/test_deployer.py
```

### Code Quality

```bash
# Format code
black ac_server_manager tests

# Lint code
ruff check ac_server_manager tests

# Type checking
mypy ac_server_manager
```

## Troubleshooting

### Server Link Not Showing

If the acstuff.ru link doesn't appear:

1. Wait a few minutes - the server needs time to start
2. Check status: `ac-deploy status <instance-id>`
3. Connect via RDP to check logs:
   - `C:\ac-deployment.log` - deployment script log
   - `C:\ac-server-log.txt` - server output
   - `C:\ac-server-info\server-info.txt` - captured info

### Server Not Starting

Common issues:
- **Missing acServer.exe**: Ensure your pack includes it
- **Configuration errors**: Check your server_cfg.ini
- **Port conflicts**: Ensure ports aren't already in use

### AWS Permission Errors

Ensure your AWS user/role has these permissions:
- `ec2:*` (EC2 full access)
- `s3:*` (S3 full access)
- `iam:CreateRole`, `iam:AttachRolePolicy` (for SSM setup)
- `ssm:SendCommand`, `ssm:GetCommandInvocation` (for status retrieval)

### Can't Connect to Server

1. Check security group allows traffic on ports 8081, 9600 (TCP/UDP)
2. Verify server is running: `ac-deploy status <instance-id>`
3. Use the acstuff.ru link in Content Manager's server browser

## Architecture

```
┌─────────────────┐
│  Content        │
│  Manager        │
│  (Pack ZIP)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│  ac-deploy CLI  │────▶│  S3 Bucket   │
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  EC2 Instance (Windows Server)      │
│  ┌──────────────────────────────┐   │
│  │  1. Download pack from S3    │   │
│  │  2. Extract to C:\acserver   │   │
│  │  3. Start acServer.exe       │   │
│  │  4. Capture acstuff.ru link  │   │
│  └──────────────────────────────┘   │
│                                     │
│  Ports: 8081, 9600 (TCP/UDP)       │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Players        │
│  (via Content   │
│   Manager)      │
└─────────────────┘
```

## License

This project is provided as-is for managing Assetto Corsa dedicated servers.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Open an issue on GitHub
3. Check AWS documentation for service-specific issues