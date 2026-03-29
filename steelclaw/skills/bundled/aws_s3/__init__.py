"""AWS S3 skill — manage S3 buckets and objects."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("aws_s3")


def _get_env() -> dict:
    """Build environment variables for AWS CLI."""
    import os
    config = _config()
    env = os.environ.copy()
    if config.get("access_key_id"):
        env["AWS_ACCESS_KEY_ID"] = config["access_key_id"]
    if config.get("secret_key"):
        env["AWS_SECRET_ACCESS_KEY"] = config["secret_key"]
    if config.get("region"):
        env["AWS_DEFAULT_REGION"] = config["region"]
    return env


def _try_boto3():
    """Try to import boto3."""
    try:
        import boto3
        return boto3
    except ImportError:
        return None


async def tool_list_buckets() -> str:
    """List all S3 buckets in the account."""
    config = _config()
    if not config.get("access_key_id") or not config.get("secret_key"):
        return "Error: AWS credentials not configured. Run: steelclaw skills configure aws_s3"
    boto3 = _try_boto3()
    if boto3:
        try:
            client = boto3.client(
                "s3",
                aws_access_key_id=config["access_key_id"],
                aws_secret_access_key=config["secret_key"],
                region_name=config.get("region", "us-east-1"),
            )
            resp = client.list_buckets()
            buckets = resp.get("Buckets", [])
            if not buckets:
                return "No buckets found."
            lines = ["S3 Buckets:\n"]
            for i, b in enumerate(buckets, 1):
                lines.append(f"{i}. **{b['Name']}** (created: {b['CreationDate']})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"
    # Fallback to AWS CLI
    try:
        result = subprocess.run(
            ["aws", "s3api", "list-buckets", "--output", "json"],
            capture_output=True, text=True, timeout=30, env=_get_env(),
        )
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        data = json.loads(result.stdout)
        buckets = data.get("Buckets", [])
        if not buckets:
            return "No buckets found."
        lines = ["S3 Buckets:\n"]
        for i, b in enumerate(buckets, 1):
            lines.append(f"{i}. **{b['Name']}** (created: {b['CreationDate']})")
        return "\n".join(lines)
    except FileNotFoundError:
        return "Error: AWS CLI not found and boto3 not installed. Install one to use this skill."
    except Exception as e:
        return f"Error: {e}"


async def tool_list_objects(bucket: str, prefix: str = "", max_keys: int = 50) -> str:
    """List objects in an S3 bucket."""
    config = _config()
    if not config.get("access_key_id") or not config.get("secret_key"):
        return "Error: AWS credentials not configured. Run: steelclaw skills configure aws_s3"
    boto3 = _try_boto3()
    if boto3:
        try:
            client = boto3.client(
                "s3",
                aws_access_key_id=config["access_key_id"],
                aws_secret_access_key=config["secret_key"],
                region_name=config.get("region", "us-east-1"),
            )
            params: dict = {"Bucket": bucket, "MaxKeys": max_keys}
            if prefix:
                params["Prefix"] = prefix
            resp = client.list_objects_v2(**params)
            objects = resp.get("Contents", [])
            if not objects:
                return f"No objects found in {bucket}."
            lines = [f"Objects in **{bucket}**:\n"]
            for i, obj in enumerate(objects, 1):
                lines.append(f"{i}. {obj['Key']} ({obj['Size']} bytes, {obj['LastModified']})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"
    # Fallback to AWS CLI
    try:
        cmd = ["aws", "s3api", "list-objects-v2", "--bucket", bucket,
               "--max-items", str(max_keys), "--output", "json"]
        if prefix:
            cmd.extend(["--prefix", prefix])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=_get_env())
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        data = json.loads(result.stdout)
        objects = data.get("Contents", [])
        if not objects:
            return f"No objects found in {bucket}."
        lines = [f"Objects in **{bucket}**:\n"]
        for i, obj in enumerate(objects, 1):
            lines.append(f"{i}. {obj['Key']} ({obj['Size']} bytes)")
        return "\n".join(lines)
    except FileNotFoundError:
        return "Error: AWS CLI not found and boto3 not installed."
    except Exception as e:
        return f"Error: {e}"


async def tool_upload_file(local_path: str, bucket: str, key: str) -> str:
    """Upload a local file to an S3 bucket."""
    config = _config()
    if not config.get("access_key_id") or not config.get("secret_key"):
        return "Error: AWS credentials not configured. Run: steelclaw skills configure aws_s3"
    p = Path(local_path)
    if not p.exists():
        return f"Error: File not found: {local_path}"
    boto3 = _try_boto3()
    if boto3:
        try:
            client = boto3.client(
                "s3",
                aws_access_key_id=config["access_key_id"],
                aws_secret_access_key=config["secret_key"],
                region_name=config.get("region", "us-east-1"),
            )
            client.upload_file(local_path, bucket, key)
            return f"Uploaded {local_path} to s3://{bucket}/{key}"
        except Exception as e:
            return f"Error: {e}"
    # Fallback to AWS CLI
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", local_path, f"s3://{bucket}/{key}"],
            capture_output=True, text=True, timeout=60, env=_get_env(),
        )
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return f"Uploaded {local_path} to s3://{bucket}/{key}"
    except FileNotFoundError:
        return "Error: AWS CLI not found and boto3 not installed."
    except Exception as e:
        return f"Error: {e}"
