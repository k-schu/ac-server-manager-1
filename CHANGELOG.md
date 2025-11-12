# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **EC2 user-data size limit exceeded** (#ISSUE)
  - Fixed "User data is limited to 16384 bytes" deployment failures
  - Reduced user-data from ~18KB to ~1.2KB (93% reduction) by using S3 bootstrap approach
  - User-data now downloads full installer script from S3 instead of inlining it
  - Supports both IAM instance profiles (aws s3 cp) and presigned URLs (curl) for installer download
  - Added automatic user-data size validation before RunInstances call
  - Created `user_data_templates/s3_bootstrap.sh` minimal bootstrap template
  - Created `user_data_templates/full_installer.sh` for complete installation logic
  - Deployer now uploads installer script to S3 alongside server pack

### Added
- **New `terminate-all` command** for complete infrastructure teardown
  - Terminates EC2 instance and recursively deletes S3 bucket with all contents
  - Interactive confirmation requiring typing "TERMINATE" (case-sensitive) for safety
  - `--force` flag to skip confirmation for automation scripts
  - `--dry-run` flag to preview deletions without performing them
  - `--instance-id` flag to explicitly specify instance to terminate
  - `--s3-bucket` flag to explicitly specify S3 bucket to delete
  - `--skip-bucket` flag to only terminate instance and preserve S3 data
  - Automatic resource discovery using tags and configuration
  - Support for versioned S3 buckets (deletes all versions and delete markers)
  - EC2 termination with waiter to ensure completion
  - Comprehensive logging at INFO and DEBUG levels

- **Enhanced S3Manager** with recursive bucket deletion capabilities
  - `delete_bucket_recursive()` method with versioning support
  - Efficient bulk deletion using S3 batch operations
  - Proper handling of pagination for large buckets
  - Dry-run mode support

- **Enhanced EC2Manager** with improved termination
  - `terminate_instance_and_wait()` method with waiter support
  - Automatic detection of already-terminated instances
  - Dry-run mode support

### Changed
- **README reorganization**
  - Replaced verbose README.md with concise quickstart guide
  - Moved full documentation to `docs/README_FULL.md`
  - Added prominent documentation of `terminate-all` command
  - Improved command reference table
  - Clearer safety feature documentation

### Tests
- Added comprehensive unit tests for user-data size limits
  - Test user-data validation passes for small scripts
  - Test user-data validation raises error for oversized scripts  
  - Test minimal bootstrap generation with IAM instance profile
  - Test minimal bootstrap generation with presigned URLs
  - Test size reduction from old to new approach (>90% reduction verified)
  - Test S3Manager presigned URL generation
  - Test S3Manager file content upload
- Added comprehensive unit tests for `terminate-all` command
  - Test confirmation flow with correct/incorrect input
  - Test all flags: `--force`, `--dry-run`, `--skip-bucket`, `--instance-id`, `--s3-bucket`
  - Test resource discovery logic
  - Test edge cases (no resources found, already terminated)
- Added unit tests for S3 recursive deletion
  - Test non-versioned bucket deletion
  - Test versioned bucket deletion with versions and delete markers
  - Test dry-run mode
  - Test bucket-not-found scenario
- Added unit tests for EC2 enhanced termination
  - Test normal termination with waiter
  - Test already-terminated detection
  - Test instance-not-found scenario
  - Test dry-run mode

### Development
- All code formatted with black (line length 100)
- All code checked with ruff
- Test coverage improved from 73% to 75%
- S3Manager: Added `upload_file_content()` method for uploading string content
- S3Manager: Added `generate_presigned_url()` method for pre-authenticated S3 downloads
- EC2Manager: Added `create_minimal_user_data_script()` for template-based user-data
- EC2Manager: Added `validate_user_data_size()` to enforce AWS 16KB limit

## [0.1.0] - 2024-01-15

### Added
- Initial release with core functionality
- EC2 instance deployment and management
- S3 pack file storage
- IAM role auto-creation
- Server lifecycle commands (deploy, start, stop, terminate, redeploy)
- Status checking with connectivity tests
- Comprehensive test suite
