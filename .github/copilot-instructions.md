# GitHub Copilot Instructions for AC Server Manager

This document provides guidance for GitHub Copilot when working with the AC Server Manager codebase.

## Project Overview

AC Server Manager is a Python-based CLI tool for deploying and managing Assetto Corsa dedicated servers on AWS infrastructure. It provides automated EC2 instance deployment, S3 integration for server packs, and complete server lifecycle management.

## Technology Stack

- **Language**: Python 3.9+
- **Package Manager**: UV (recommended) or pip
- **CLI Framework**: Click
- **AWS SDK**: Boto3
- **Testing**: pytest with pytest-cov
- **Code Quality**: black, ruff, mypy
- **Type Checking**: Full type hints with mypy

## Code Style and Standards

### Python Style Guidelines

1. **Follow PEP 8** with these specific configurations:
   - Maximum line length: 100 characters
   - Use type hints for all function signatures
   - Target Python 3.9 compatibility

2. **Type Hints**: All functions must have complete type annotations
   ```python
   def function_name(arg1: str, arg2: int) -> Optional[bool]:
       """Function docstring."""
       pass
   ```

3. **Docstrings**: Use Google-style docstrings for all public functions and classes
   ```python
   def create_security_group(self, group_name: str, description: str) -> Optional[str]:
       """Create security group with rules for AC server.
       
       Args:
           group_name: Name of the security group
           description: Description of the security group
           
       Returns:
           Security group ID, or None if creation failed
           
       Raises:
           ClientError: If AWS API call fails
       """
   ```

4. **Formatting**: Code is auto-formatted with black (line-length=100)

5. **Linting**: Code must pass ruff checks with no issues

### Project Structure

```
ac-server-manager/
├── src/ac_server_manager/
│   ├── __init__.py       # Package initialization
│   ├── cli.py            # CLI interface using Click
│   ├── config.py         # Configuration dataclasses
│   ├── deployer.py       # Deployment orchestration logic
│   ├── ec2_manager.py    # EC2 operations (instances, security groups)
│   ├── s3_manager.py     # S3 operations (buckets, uploads)
│   └── iam_manager.py    # IAM role and policy management
├── tests/                # All test files with test_*.py pattern
├── docs/                 # Documentation files
├── scripts/              # Helper scripts
└── pyproject.toml        # Project configuration
```

## Architecture Patterns

### Manager Classes

All AWS service interactions are encapsulated in manager classes:
- `EC2Manager`: Handles EC2 instances, security groups, and instance operations
- `S3Manager`: Handles S3 buckets and file operations
- `IAMManager`: Handles IAM roles and policies
- `Deployer`: Orchestrates the deployment process using the managers

### Error Handling

1. Use boto3's `ClientError` for AWS exceptions
2. Log errors with descriptive messages using Python's logging module
3. Return `Optional[T]` for operations that may fail gracefully
4. Raise exceptions for critical failures that should stop execution

Example:
```python
try:
    response = self.ec2_client.create_security_group(...)
    return response['GroupId']
except ClientError as e:
    logger.error(f"Error creating security group: {e}")
    return None
```

### Configuration

Configuration uses dataclasses defined in `config.py`:
- `ServerConfig`: AWS region, instance type, etc.
- Type-safe, validated configuration objects

## Testing Guidelines

### Test Structure

1. **One test file per module**: `test_deployer.py` tests `deployer.py`
2. **Descriptive test names**: `test_deploy_success`, `test_deploy_fails_when_bucket_creation_fails`
3. **AAA Pattern**: Arrange, Act, Assert
4. **Mock external dependencies**: All AWS API calls must be mocked

### Example Test

```python
def test_deploy_success(deployer: Deployer, tmp_path: Path) -> None:
    """Test successful deployment."""
    # Arrange
    pack_file = tmp_path / "test-pack.tar.gz"
    pack_file.write_text("test content")
    deployer.s3_manager.create_bucket = MagicMock(return_value=True)
    
    # Act
    result = deployer.deploy(pack_file)
    
    # Assert
    assert result == "i-12345"
    deployer.s3_manager.create_bucket.assert_called_once()
```

### Test Coverage

- Aim for >80% code coverage overall
- Current coverage: 74% (target: increase to 80%+)
- Test both success and failure paths
- Test edge cases and boundary conditions

## Development Workflow

### Before Making Changes

1. Install dependencies: `pip install -e ".[dev]"`
2. Run existing tests: `pytest`
3. Check current code quality: `black src/ tests/`, `ruff check src/ tests/`, `mypy src/ac_server_manager`

### Making Changes

1. Write tests first (TDD approach recommended)
2. Implement changes in small, focused commits
3. Run tests frequently: `pytest -v`
4. Format and lint: `black src/ tests/` and `ruff check src/ tests/ --fix`
5. Type check: `mypy src/ac_server_manager`

### Quality Checks

All code must pass these checks before commit:
```bash
black src/ tests/              # Format code
ruff check src/ tests/ --fix   # Lint and auto-fix
mypy src/ac_server_manager     # Type check
pytest --cov                   # Run tests with coverage
```

## CLI Commands

When adding new CLI commands:
1. Add the command in `cli.py` using Click decorators
2. Implement logic in appropriate manager class or `deployer.py`
3. Add comprehensive tests
4. Update README.md documentation

Example:
```python
@main.command()
@click.option("--instance-id", help="Instance ID")
@click.pass_context
def restart(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Restart an AC server instance."""
    # Implementation
```

## AWS Integration

### Resource Naming

- Instance name tag: `ac-server-instance` (configurable)
- Security group: `ac-server-sg-{unique-id}`
- S3 bucket: `ac-server-packs` (configurable)
- IAM role: `ac-server-s3-role`

### Required AWS Permissions

- EC2: DescribeInstances, RunInstances, TerminateInstances, StopInstances, StartInstances
- S3: CreateBucket, PutObject, GetObject, ListBucket, DeleteObject, DeleteBucket
- IAM: CreateRole, CreateInstanceProfile, PutRolePolicy (for --create-iam)

### Security Best Practices

1. Never hardcode AWS credentials
2. Use environment variables or AWS CLI configuration
3. Implement security groups with minimal necessary ports
4. Use IAM roles for EC2 instances instead of embedding credentials
5. Implement proper error handling for permission errors

## Common Patterns

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Usage
logger.info(f"Creating instance with name: {instance_name}")
logger.error(f"Failed to create bucket: {e}")
```

### Optional Returns

```python
def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
    """Get instance details.
    
    Returns:
        Instance details dict, or None if not found
    """
    try:
        # Implementation
        return instance_details
    except ClientError:
        return None
```

### Click Context

```python
@click.pass_context
def command(ctx: click.Context) -> None:
    """Command that needs access to shared context."""
    config = ctx.obj["config"]
```

## Documentation

When modifying code, update:
1. **Docstrings**: For all public functions/classes
2. **README.md**: For user-facing features
3. **EXAMPLES.md**: For usage examples
4. **CONTRIBUTING.md**: For development workflow changes

## Dependencies

### Core Dependencies
- boto3: AWS SDK
- click: CLI framework
- pyyaml: YAML configuration
- python-dotenv: Environment variables

### Development Dependencies
- pytest, pytest-cov: Testing
- mypy: Type checking
- black: Code formatting
- ruff: Linting
- boto3-stubs: Type hints for boto3

## Security Considerations

1. **No secrets in code**: Use environment variables or AWS credentials file
2. **Input validation**: Validate all user inputs in CLI commands
3. **Safe teardown**: Implement confirmation prompts for destructive operations
4. **Least privilege**: Request minimal necessary AWS permissions

## Performance

1. **Avoid unnecessary API calls**: Cache instance/bucket information when appropriate
2. **Use pagination**: For listing operations that may return many results
3. **Implement timeouts**: For long-running operations
4. **Efficient uploads**: Use boto3's transfer manager for large files

## Known Patterns to Avoid

1. **Don't** use synchronous operations for long-running tasks without progress indication
2. **Don't** catch all exceptions with bare `except:` - be specific
3. **Don't** use mutable default arguments in function signatures
4. **Don't** use `print()` for output - use `click.echo()` or logging
5. **Don't** hardcode AWS regions or resource names - make them configurable

## Current Focus Areas

Based on test coverage, these areas need improvement:
- CLI command testing (currently 65% coverage)
- Error handling paths in deployer.py (84% coverage)
- Edge cases in EC2Manager (76% coverage)
- S3Manager error scenarios (73% coverage)

## References

- [Click Documentation](https://click.palletsprojects.com/)
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [pytest Documentation](https://docs.pytest.org/)
- [PEP 8](https://pep8.org/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

## Questions?

Refer to:
- README.md for user documentation
- CONTRIBUTING.md for development guidelines
- EXAMPLES.md for practical usage examples
- Open an issue on GitHub for clarification
