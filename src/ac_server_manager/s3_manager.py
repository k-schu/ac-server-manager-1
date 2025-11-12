"""S3 operations for AC Server Manager."""

import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Manager:
    """Manages S3 operations for AC server pack files."""

    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        """Initialize S3 manager.

        Args:
            bucket_name: Name of the S3 bucket
            region: AWS region
        """
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client("s3", region_name=region)

    def create_bucket(self) -> bool:
        """Create S3 bucket if it doesn't exist.

        Returns:
            True if bucket was created or already exists, False otherwise
        """
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} already exists")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    if self.region == "us-east-1":
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        from typing import cast, Any

                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={
                                "LocationConstraint": cast(Any, self.region)
                            },
                        )
                    logger.info(f"Created bucket {self.bucket_name}")
                    return True
                except ClientError as create_error:
                    logger.error(f"Error creating bucket: {create_error}")
                    return False
            else:
                logger.error(f"Error checking bucket: {e}")
                return False

    def upload_pack(self, local_path: Path, s3_key: Optional[str] = None) -> Optional[str]:
        """Upload AC server pack to S3.

        Args:
            local_path: Path to the local pack file
            s3_key: S3 object key (defaults to filename)

        Returns:
            S3 key of uploaded file, or None if upload failed
        """
        if not local_path.exists():
            logger.error(f"Pack file not found: {local_path}")
            return None

        if s3_key is None:
            s3_key = f"packs/{local_path.name}"

        try:
            self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
            logger.info(f"Uploaded {local_path} to s3://{self.bucket_name}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Error uploading pack: {e}")
            return None

    def upload_file_content(self, content: str, s3_key: str) -> bool:
        """Upload file content to S3.

        Args:
            content: File content as string
            s3_key: S3 object key

        Returns:
            True if upload succeeded, False otherwise
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=s3_key, Body=content.encode("utf-8")
            )
            logger.info(f"Uploaded content to s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Error uploading content: {e}")
            return False

    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for downloading an S3 object.

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Presigned URL string, or None if generation failed
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            logger.info(f"Generated presigned URL for s3://{self.bucket_name}/{s3_key}")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def download_pack(self, s3_key: str, local_path: Path) -> bool:
        """Download AC server pack from S3.

        Args:
            s3_key: S3 object key
            local_path: Local path to save the file

        Returns:
            True if download succeeded, False otherwise
        """
        try:
            # Create parent directory if it doesn't exist
            local_path.parent.mkdir(parents=True, exist_ok=True)

            self.s3_client.download_file(self.bucket_name, s3_key, str(local_path))
            logger.info(f"Downloaded s3://{self.bucket_name}/{s3_key} to {local_path}")
            return True
        except ClientError as e:
            logger.error(f"Error downloading pack: {e}")
            return False

    def list_packs(self) -> list[str]:
        """List all pack files in the S3 bucket.

        Returns:
            List of S3 keys for pack files
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix="packs/")

            if "Contents" not in response:
                return []

            return [obj["Key"] for obj in response["Contents"]]
        except ClientError as e:
            logger.error(f"Error listing packs: {e}")
            return []

    def delete_pack(self, s3_key: str) -> bool:
        """Delete a pack file from S3.

        Args:
            s3_key: S3 object key to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Error deleting pack: {e}")
            return False

    def delete_bucket_recursive(self, dry_run: bool = False) -> bool:
        """Recursively delete S3 bucket including all objects and versions.

        This handles versioned buckets by deleting all object versions and delete markers,
        then deleting the bucket itself.

        Args:
            dry_run: If True, only log what would be deleted without performing deletions

        Returns:
            True if deletion succeeded (or would succeed in dry-run), False otherwise
        """
        try:
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "404":
                    logger.info(f"Bucket {self.bucket_name} does not exist, nothing to delete")
                    return True
                else:
                    raise

            logger.info(
                f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} bucket {self.bucket_name} and all contents"
            )

            # Check if bucket has versioning enabled
            try:
                versioning = self.s3_client.get_bucket_versioning(Bucket=self.bucket_name)
                is_versioned = versioning.get("Status") == "Enabled"
                logger.debug(f"Bucket versioning status: {versioning.get('Status', 'Not enabled')}")
            except ClientError:
                is_versioned = False

            # Delete all object versions and delete markers if versioned
            if is_versioned:
                logger.info("Bucket has versioning enabled, deleting all versions...")
                if not self._delete_versioned_objects(dry_run):
                    return False
            else:
                # Delete all objects in non-versioned bucket
                logger.info("Deleting all objects in bucket...")
                if not self._delete_objects(dry_run):
                    return False

            # Delete the bucket itself
            if dry_run:
                logger.info(f"[DRY RUN] Would delete bucket: {self.bucket_name}")
            else:
                self.s3_client.delete_bucket(Bucket=self.bucket_name)
                logger.info(f"Deleted bucket: {self.bucket_name}")

            return True

        except ClientError as e:
            logger.error(f"Error deleting bucket {self.bucket_name}: {e}")
            return False

    def _delete_objects(self, dry_run: bool = False) -> bool:
        """Delete all objects in a non-versioned bucket.

        Args:
            dry_run: If True, only log what would be deleted

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            # Use pagination to handle large buckets
            paginator = self.s3_client.get_paginator("list_objects_v2")
            total_objects = 0

            for page in paginator.paginate(Bucket=self.bucket_name):
                if "Contents" not in page:
                    continue

                objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]
                total_objects += len(objects_to_delete)

                if dry_run:
                    logger.debug(
                        f"[DRY RUN] Would delete {len(objects_to_delete)} objects from page"
                    )
                    for obj in objects_to_delete[:5]:  # Show first 5
                        logger.debug(f"[DRY RUN] Would delete: {obj['Key']}")
                    if len(objects_to_delete) > 5:
                        logger.debug(f"[DRY RUN] ... and {len(objects_to_delete) - 5} more")
                else:
                    # Use bulk delete for efficiency
                    response = self.s3_client.delete_objects(
                        Bucket=self.bucket_name, Delete={"Objects": objects_to_delete}
                    )
                    deleted_count = len(response.get("Deleted", []))
                    logger.debug(f"Deleted {deleted_count} objects from page")

            if dry_run:
                logger.info(f"[DRY RUN] Would delete {total_objects} total objects")
            else:
                logger.info(f"Deleted {total_objects} total objects")

            return True

        except ClientError as e:
            logger.error(f"Error deleting objects: {e}")
            return False

    def _delete_versioned_objects(self, dry_run: bool = False) -> bool:
        """Delete all object versions and delete markers from a versioned bucket.

        Args:
            dry_run: If True, only log what would be deleted

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            # Use pagination to handle large buckets
            paginator = self.s3_client.get_paginator("list_object_versions")
            total_versions = 0

            for page in paginator.paginate(Bucket=self.bucket_name):
                objects_to_delete = []

                # Add all versions
                for version in page.get("Versions", []):
                    objects_to_delete.append(
                        {"Key": version["Key"], "VersionId": version["VersionId"]}
                    )

                # Add all delete markers
                for marker in page.get("DeleteMarkers", []):
                    objects_to_delete.append(
                        {"Key": marker["Key"], "VersionId": marker["VersionId"]}
                    )

                if not objects_to_delete:
                    continue

                total_versions += len(objects_to_delete)

                if dry_run:
                    logger.debug(
                        f"[DRY RUN] Would delete {len(objects_to_delete)} versions/markers from page"
                    )
                    for obj in objects_to_delete[:5]:  # Show first 5
                        logger.debug(
                            f"[DRY RUN] Would delete: {obj['Key']} (version {obj['VersionId']})"
                        )
                    if len(objects_to_delete) > 5:
                        logger.debug(f"[DRY RUN] ... and {len(objects_to_delete) - 5} more")
                else:
                    # Use bulk delete for efficiency
                    response = self.s3_client.delete_objects(
                        Bucket=self.bucket_name, Delete={"Objects": objects_to_delete}
                    )
                    deleted_count = len(response.get("Deleted", []))
                    logger.debug(f"Deleted {deleted_count} versions/markers from page")

            if dry_run:
                logger.info(f"[DRY RUN] Would delete {total_versions} total versions/markers")
            else:
                logger.info(f"Deleted {total_versions} total versions/markers")

            return True

        except ClientError as e:
            logger.error(f"Error deleting versioned objects: {e}")
            return False
