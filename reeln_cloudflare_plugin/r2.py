"""Cloudflare R2 storage operations via boto3 S3-compatible API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


class R2Error(Exception):
    """Raised on R2 operation failures."""


@dataclass(frozen=True)
class R2Config:
    """Configuration for Cloudflare R2 access."""

    endpoint: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    public_url_base: str
    region: str = "auto"
    upload_max_kbps: int = 0


def _create_client(config: R2Config) -> Any:
    """Create a boto3 S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=config.region,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def upload_file(config: R2Config, source: Path, key: str) -> str:
    """Upload a file to R2 and return its public URL.

    Args:
        config: R2 connection configuration.
        source: Local file path to upload.
        key: Object key (path) in the bucket.

    Returns:
        The public URL of the uploaded object.

    Raises:
        R2Error: If the source file is missing or the upload fails.
    """
    if not source.exists():
        raise R2Error(f"R2 upload source not found: {source}")

    try:
        s3 = _create_client(config)
    except Exception as exc:
        raise R2Error(f"Failed to create R2 client: {exc}") from exc

    transfer_config = None
    max_kbps = config.upload_max_kbps
    if max_kbps > 0:
        from boto3.s3.transfer import TransferConfig

        transfer_config = TransferConfig(max_bandwidth=max_kbps * 1024)

    try:
        if transfer_config:
            s3.upload_file(str(source), config.bucket, key, Config=transfer_config)
        else:
            s3.upload_file(str(source), config.bucket, key)
    except Exception as exc:
        raise R2Error(f"R2 upload failed: {exc}") from exc

    base = config.public_url_base.rstrip("/")
    return f"{base}/{key}"


def object_exists(config: R2Config, key: str) -> bool:
    """Check whether an object exists in the R2 bucket.

    Args:
        config: R2 connection configuration.
        key: Object key to check.

    Returns:
        True if the object exists, False if not found.

    Raises:
        R2Error: On unexpected API errors.
    """
    try:
        s3 = _create_client(config)
    except Exception as exc:
        raise R2Error(f"Failed to create R2 client: {exc}") from exc

    try:
        s3.head_object(Bucket=config.bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise R2Error(f"R2 head_object failed: {exc}") from exc
