"""IAM operations for AC Server Manager."""

import json
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class IAMManager:
    """Manages IAM operations for AC server deployment."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize IAM manager.

        Args:
            region: AWS region (IAM is global but region is kept for consistency)
        """
        self.region = region
        self.iam_client = boto3.client("iam", region_name=region)

    def ensure_role_and_instance_profile(
        self, role_name: str, instance_profile_name: str, bucket: str
    ) -> str:
        """Ensure IAM role and instance profile exist with S3 access policy.

        Creates a role with trust policy for EC2 (sts:AssumeRole with ec2.amazonaws.com
        principal) if not exists. Creates instance profile if not exists and adds role to it.
        Attaches/puts an inline policy allowing s3:GetObject and s3:ListBucket for the given bucket.

        Args:
            role_name: Name of the IAM role to create/use
            instance_profile_name: Name of the instance profile to create/use
            bucket: S3 bucket name for which to grant access

        Returns:
            Instance profile name (can be used in EC2 run_instances call)

        Raises:
            Exception: If IAM operations fail due to permissions or other errors
        """
        logger.info(f"Ensuring IAM role '{role_name}' and profile '{instance_profile_name}'")

        try:
            # Step 1: Create or get IAM role
            role_arn = self._ensure_role(role_name)
            logger.debug(f"Role ARN: {role_arn}")

            # Step 2: Create or get instance profile
            profile_arn = self._ensure_instance_profile(instance_profile_name)
            logger.debug(f"Instance profile ARN: {profile_arn}")

            # Step 3: Attach role to instance profile
            self._attach_role_to_profile(instance_profile_name, role_name)

            # Step 4: Attach inline policy for S3 access
            self._attach_s3_policy(role_name, bucket)

            logger.info(
                f"Successfully configured IAM role and profile for S3 bucket '{bucket}'"
            )
            return instance_profile_name

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"IAM operation failed [{error_code}]: {error_message}")
            raise Exception(
                f"Failed to create/configure IAM resources. "
                f"Ensure you have IAM permissions (iam:CreateRole, iam:CreateInstanceProfile, "
                f"iam:AddRoleToInstanceProfile, iam:PutRolePolicy, iam:GetRole, iam:GetInstanceProfile). "
                f"Error: {error_message}"
            ) from e

    def _ensure_role(self, role_name: str) -> str:
        """Create IAM role if it doesn't exist.

        Args:
            role_name: Name of the IAM role

        Returns:
            Role ARN
        """
        # EC2 trust policy document
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        try:
            # Try to get existing role
            response = self.iam_client.get_role(RoleName=role_name)
            logger.debug(f"Role '{role_name}' already exists")
            return response["Role"]["Arn"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                # Role doesn't exist, create it
                logger.info(f"Creating IAM role '{role_name}'")
                response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description="IAM role for AC Server EC2 instance to access S3",
                )
                logger.info(f"Created IAM role '{role_name}'")
                return response["Role"]["Arn"]
            else:
                raise

    def _ensure_instance_profile(self, profile_name: str) -> str:
        """Create instance profile if it doesn't exist.

        Args:
            profile_name: Name of the instance profile

        Returns:
            Instance profile ARN
        """
        try:
            # Try to get existing instance profile
            response = self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
            logger.debug(f"Instance profile '{profile_name}' already exists")
            return response["InstanceProfile"]["Arn"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                # Instance profile doesn't exist, create it
                logger.info(f"Creating instance profile '{profile_name}'")
                response = self.iam_client.create_instance_profile(
                    InstanceProfileName=profile_name
                )
                logger.info(f"Created instance profile '{profile_name}'")
                return response["InstanceProfile"]["Arn"]
            else:
                raise

    def _attach_role_to_profile(self, profile_name: str, role_name: str) -> None:
        """Attach IAM role to instance profile if not already attached.

        Args:
            profile_name: Name of the instance profile
            role_name: Name of the IAM role
        """
        try:
            # Check if role is already attached
            response = self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
            roles = response["InstanceProfile"].get("Roles", [])

            if any(role["RoleName"] == role_name for role in roles):
                logger.debug(f"Role '{role_name}' already attached to profile '{profile_name}'")
                return

            # Attach role to profile
            logger.info(f"Attaching role '{role_name}' to profile '{profile_name}'")
            self.iam_client.add_role_to_instance_profile(
                InstanceProfileName=profile_name, RoleName=role_name
            )
            logger.info(f"Attached role '{role_name}' to profile '{profile_name}'")
        except ClientError as e:
            if e.response["Error"]["Code"] == "LimitExceeded":
                # Profile already has a role (can only have one)
                logger.debug(
                    f"Instance profile '{profile_name}' already has a role attached"
                )
            else:
                raise

    def _attach_s3_policy(self, role_name: str, bucket: str) -> None:
        """Attach inline S3 access policy to the role.

        Args:
            role_name: Name of the IAM role
            bucket: S3 bucket name
        """
        policy_name = f"{role_name}-s3-access"

        # Minimal S3 policy: GetObject and ListBucket
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket}"],
                },
            ],
        }

        try:
            logger.info(f"Attaching S3 access policy to role '{role_name}' for bucket '{bucket}'")
            self.iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document),
            )
            logger.info(f"Attached inline policy '{policy_name}' to role '{role_name}'")
        except ClientError as e:
            logger.error(f"Failed to attach S3 policy: {e}")
            raise
