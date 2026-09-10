"""AWS S3 entity schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class S3BucketEntity(BaseEntity):
    """Schema for an AWS S3 bucket, anchoring the breadcrumb trail for its files."""

    bucket_name: str = AirweaveField(
        ...,
        description="S3 bucket name",
        is_entity_id=True,
        is_name=True,
        embeddable=True,
    )
    region: Optional[str] = AirweaveField(
        None, description="AWS region the bucket lives in", embeddable=False
    )
    prefix: str = AirweaveField(
        "", description="Key prefix this connection is scoped to", embeddable=False
    )
    endpoint_url: Optional[str] = AirweaveField(
        None,
        description="Custom S3-compatible endpoint, if configured (MinIO, LocalStack, R2)",
        embeddable=False,
    )


class S3FileEntity(FileEntity):
    """Schema for a single AWS S3 object.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_Object.html
    """

    key: str = AirweaveField(
        ...,
        description="Full S3 object key",
        is_entity_id=True,
        is_name=True,
        embeddable=True,
    )
    bucket_name: str = AirweaveField(..., description="S3 bucket this object lives in")
    etag: Optional[str] = AirweaveField(
        None, description="S3 ETag for the object (integrity/change detection)", embeddable=False
    )
    storage_class: Optional[str] = AirweaveField(
        None, description="S3 storage class (STANDARD, GLACIER, etc.)", embeddable=False
    )
    last_modified: Optional[datetime] = AirweaveField(
        None,
        description="When the object was last modified in S3",
        embeddable=False,
        is_updated_at=True,
    )
    metadata: Optional[Dict[str, str]] = AirweaveField(
        None,
        description=(
            "Custom metadata merged from S3 object metadata and companion "
            "*.metadata.json sidecar files, if present"
        ),
        embeddable=True,
    )
