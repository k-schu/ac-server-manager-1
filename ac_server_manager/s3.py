"""S3 operations for managing Assetto Corsa server pack files."""

import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Manager:
    """Manages S3 operations for AC server pack files."""

    def __init__(
        self,
        bucket_name: str,
        region: str = "us-east-1",
        profile: Optional[str] = None
    ):
        """Initialize S3 manager.

        Args:
            bucket_name: Name of the S3 bucket
            region: AWS region
            profile: AWS profile name (optional)
        """
        session = boto3.Session(profile_name=profile, region_name=region)
        self.s3_client = session.client("s3")
        self.bucket_name = bucket_name
        self.region = region

    def create_bucket(self) -> bool:
        """Create the S3 bucket if it doesn't exist.

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
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.region}
                        )
                    logger.info(f"Created bucket {self.bucket_name}")
                    return True
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    return False
            else:
                logger.error(f"Error checking bucket: {e}")
                return False

    def upload_pack(self, pack_path: Path, pack_name: Optional[str] = None) -> str:
        """Upload AC server pack ZIP to S3.

        Args:
            pack_path: Path to the pack ZIP file
            pack_name: Optional custom name for the pack in S3

        Returns:
            S3 key of the uploaded file

        Raises:
            FileNotFoundError: If pack file doesn't exist
            ClientError: If upload fails
        """
        if not pack_path.exists():
            raise FileNotFoundError(f"Pack file not found: {pack_path}")

        key = pack_name or pack_path.name
        
        logger.info(f"Uploading {pack_path} to s3://{self.bucket_name}/{key}")
        
        try:
            self.s3_client.upload_file(
                str(pack_path),
                self.bucket_name,
                key,
                ExtraArgs={"ContentType": "application/zip"}
            )
            logger.info(f"Successfully uploaded pack to {key}")
            return key
        except ClientError as e:
            logger.error(f"Failed to upload pack: {e}")
            raise

    def get_pack_url(self, pack_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading the pack.

        Args:
            pack_key: S3 key of the pack file
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL for downloading the pack
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": pack_key},
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned URL for {pack_key}")
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def delete_pack(self, pack_key: str) -> bool:
        """Delete a pack from S3.

        Args:
            pack_key: S3 key of the pack to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=pack_key)
            logger.info(f"Deleted pack {pack_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete pack: {e}")
            return False

    def list_packs(self) -> list[str]:
        """List all pack files in the bucket.

        Returns:
            List of pack file keys
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            if "Contents" in response:
                return [obj["Key"] for obj in response["Contents"]]
            return []
        except ClientError as e:
            logger.error(f"Failed to list packs: {e}")
            return []
