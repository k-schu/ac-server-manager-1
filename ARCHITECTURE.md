# Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                          User's Machine                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Content Manager                                           │  │
│  │  - Create Server Pack ZIP                                  │  │
│  │  - Pack contains: acServer.exe, cfg/, content/, system/   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ac-deploy CLI                                             │  │
│  │  $ ac-deploy deploy server-pack.zip                       │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ AWS API Calls
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  S3 Bucket: ac-server-packs                               │  │
│  │  - Stores server pack ZIP files                           │  │
│  │  - Generates presigned URLs for download                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               │                                  │
│                               │ Presigned URL                    │
│                               ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  EC2 Instance (Windows Server 2022)                       │  │
│  │  Instance Type: t3.small (2 vCPU, 2GB RAM)               │  │
│  │                                                            │  │
│  │  Security Group:                                           │  │
│  │  - TCP 9600  (AC Game)                                    │  │
│  │  - UDP 9600  (AC Game)                                    │  │
│  │  - TCP 8081  (AC HTTP)                                    │  │
│  │  - TCP 3389  (RDP)                                        │  │
│  │                                                            │  │
│  │  User Data Script (PowerShell):                           │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ 1. Download pack.zip from S3                       │  │  │
│  │  │ 2. Extract to C:\acserver                          │  │  │
│  │  │ 3. Find acServer.exe                               │  │  │
│  │  │ 4. Create scheduled task                           │  │  │
│  │  │ 5. Start acServer.exe                              │  │  │
│  │  │ 6. Monitor logs for acstuff.ru link                │  │  │
│  │  │ 7. Save to C:\ac-server-info\server-info.txt       │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                            │  │
│  │  Running Process:                                          │  │
│  │  └─ acServer.exe (PID: 1234)                              │  │
│  │     └─ Generates: http://acstuff.ru/s/q/abc123           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               │                                  │
│                               │ SSM Commands                     │
│                               ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  AWS Systems Manager (SSM)                                │  │
│  │  - Reads C:\ac-server-info\server-info.txt               │  │
│  │  - Returns server status and link to CLI                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ Returns Link
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          User's Machine                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Terminal Output                                           │  │
│  │  🎮 Server Connection Link:                                │  │
│  │     http://acstuff.ru/s/q/abc123                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              │ Share with players               │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Players' Content Manager                                  │  │
│  │  - Paste acstuff.ru link                                   │  │
│  │  - Connect to server                                       │  │
│  │  - Play Assetto Corsa                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Deployment Phase

```
[Pack ZIP] → [S3 Upload] → [Presigned URL Generated]
                                      ↓
                              [EC2 Instance Launch]
                                      ↓
                              [User Data Execution]
                                      ↓
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
              [Download Pack]              [Setup Monitoring]
                        ↓                           ↓
              [Extract Files]              [Create Scheduled Task]
                        ↓                           ↓
              [Find acServer.exe]          [Start Server]
                        └─────────────┬─────────────┘
                                      ▼
                              [Monitor Logs]
                                      ↓
                         [Capture acstuff.ru Link]
                                      ↓
                         [Save to server-info.txt]
```

### 2. Link Retrieval Phase

```
[User: ac-deploy status] → [SSM Command] → [Read server-info.txt]
                                                    ↓
                                            [Parse Content]
                                                    ↓
                                            [Return to CLI]
                                                    ↓
                                            [Display to User]
```

## Key Technologies

### Python Side (ac-deploy CLI)
- **boto3**: AWS SDK for Python
- **click**: CLI framework
- **pydantic**: Configuration validation
- **pytest**: Unit testing

### AWS Side
- **EC2**: Virtual servers running Windows
- **S3**: Object storage for pack files
- **SSM**: Remote command execution
- **IAM**: Permissions and roles

### Windows Side (EC2 Instance)
- **PowerShell**: Automation scripting
- **Scheduled Tasks**: Server persistence
- **acServer.exe**: Assetto Corsa dedicated server

## Security Model

```
┌─────────────────┐
│  IAM Role       │
│  (EC2 Profile)  │
└────────┬────────┘
         │ Allows
         ▼
┌─────────────────┐     ┌──────────────┐
│  EC2 Instance   │────▶│  S3 Bucket   │
│                 │     │  (Download)  │
└────────┬────────┘     └──────────────┘
         │
         │ Reports To
         ▼
┌─────────────────┐
│  SSM Service    │
│  (Command Exec) │
└─────────────────┘
```

### Permissions Required

**User/CLI Permissions:**
- `ec2:*` - Create/manage instances
- `s3:*` - Upload/download packs
- `iam:CreateRole` - Setup SSM access
- `ssm:SendCommand` - Retrieve server info

**Instance Role Permissions:**
- `ssm:*` - Allow SSM agent
- `s3:GetObject` - Download pack files

## Cost Breakdown

### Per Month (12 hours/day usage)

| Component | Cost |
|-----------|------|
| EC2 t3.small (12hrs/day × 30 days × $0.0208/hr) | ~$7.50 |
| S3 Storage (5GB @ $0.023/GB) | ~$0.12 |
| S3 Requests (negligible) | ~$0.01 |
| Data Transfer Out (10GB @ $0.09/GB) | ~$0.90 |
| **Total** | **~$8.53/month** |

### Cost Optimization Tips

1. **Stop when not in use**: `ac-deploy stop <id>`
   - Reduces compute costs to $0
   - Only pay for storage (~$0.50/month)

2. **Use spot instances** (future enhancement):
   - Save up to 70% on compute costs
   - Good for non-critical servers

3. **S3 lifecycle policies**:
   - Auto-delete packs older than 30 days
   - Move to Glacier for long-term storage

## Scalability

### Current Implementation
- One server per EC2 instance
- Optimal for 2-8 players
- Simple management

### Future Scaling Options

**Vertical Scaling:**
```
t3.small (2-8 players)
    ↓
t3.medium (8-16 players)
    ↓
t3.large (16-24 players)
```

**Horizontal Scaling:**
```
Multiple Instances
    ↓
Load Balancer (optional)
    ↓
Auto Scaling Group (optional)
```

## Monitoring and Debugging

### Log Files on Instance

```
C:\ac-deployment.log          # Deployment script output
C:\ac-server-log.txt          # AC server stdout
C:\ac-server-error.txt        # AC server stderr
C:\ac-server-info\
  └─ server-info.txt          # Captured server info
```

### Access Methods

1. **Via CLI**: `ac-deploy status <instance-id>`
2. **Via RDP**: Connect to instance IP:3389
3. **Via SSM**: AWS Console → Systems Manager → Session Manager

### Health Checks

The monitor script checks:
- ✅ Process running
- ✅ Link captured
- ✅ Public IP available
- ✅ Ports open

## Disaster Recovery

### Backup Strategy

1. **Server Packs**: Stored in S3 (highly durable)
2. **Instance State**: Ephemeral (not backed up)
3. **Configuration**: In pack files

### Recovery Process

```
[Instance Failure]
    ↓
[Terminate old instance]
    ↓
[Deploy new instance]
    ↓
[Same pack from S3]
    ↓
[Server running in ~5 minutes]
```

## Future Enhancements

### Planned Features

1. **Auto-restart**: Detect crashes and restart
2. **CloudWatch**: Stream logs to CloudWatch
3. **SNS Notifications**: Alert on server events
4. **Multi-region**: Deploy to closest region
5. **Backup/Restore**: Save server state to EBS
6. **Web Dashboard**: Monitor all servers
7. **Discord Integration**: Post links automatically

### Architecture Evolution

```
Current: CLI → AWS → Server
    ↓
Future: Web UI → API Gateway → Lambda → AWS → Servers
```
