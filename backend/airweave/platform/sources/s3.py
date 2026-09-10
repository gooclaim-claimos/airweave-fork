"""AWS S3 source implementation.

Reads objects from an S3 (or S3-compatible: MinIO, LocalStack, Cloudflare R2)
bucket/prefix and yields them as searchable file entities.

Companion metadata sidecars (``<key>.metadata.json``, following the AWS
Bedrock Knowledge Base convention of a top-level ``metadataAttributes`` map)
are merged onto the matching file entity's ``metadata`` field.
"""

from __future__ import annotations

import fnmatch
import json
import mimetypes
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from airweave.core.logging import ContextualLogger
from airweave.core.shared_models import RateLimitLevel
from airweave.domains.browse_tree.types import NodeSelectionData
from airweave.domains.sources.token_providers.credential import DirectCredentialProvider
from airweave.domains.storage import FileSkippedException
from airweave.domains.storage.file_service import FileService
from airweave.domains.syncs.cursors.cursor import SyncCursor
from airweave.platform.configs.auth import S3SourceAuthConfig
from airweave.platform.configs.config import S3SourceConfig
from airweave.platform.decorators import source
from airweave.platform.entities._base import BaseEntity, Breadcrumb
from airweave.platform.entities.s3 import S3BucketEntity, S3FileEntity
from airweave.platform.http_client.airweave_client import AirweaveHttpClient
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod

DEFAULT_REGION = "us-east-1"

# Matches AWS Bedrock Knowledge Base-style metadata sidecars: "notes.md.metadata.json"
# or a numbered variant "notes.md.metadata(2).json". Group "base" is the original key.
_SIDECAR_RE = re.compile(r"^(?P<base>.+)\.metadata(?:\(\d+\))?\.json$")


@source(
    name="AWS S3",
    short_name="s3",
    auth_methods=[AuthenticationMethod.DIRECT],
    oauth_type=None,
    auth_config_class=S3SourceAuthConfig,
    config_class=S3SourceConfig,
    labels=["File Storage", "Cloud Storage"],
    supports_continuous=False,
    rate_limit_level=RateLimitLevel.ORG,
)
class S3Source(BaseSource):
    """AWS S3 source connector.

    Lists objects under a bucket/prefix, downloads each one, and yields it
    as a searchable file entity. Supports explicit credentials or the
    default AWS credential chain, and S3-compatible endpoints.
    """

    # Instance attributes set inside `create()` from credentials/config.
    # Declared at class level so pyright recognises the typed assignments below.
    _access_key_id: Optional[str]
    _secret_access_key: Optional[str]
    _session_token: Optional[str]
    _region_name: Optional[str]
    _endpoint_url: Optional[str]
    _bucket_name: str
    _prefix: str
    _include_patterns: List[str]
    _download_concurrency: int
    _max_pool_connections: int
    _connect_timeout: float
    _read_timeout: float
    _max_retries: int
    _metadata_preload_max_files: int
    _metadata_cache: Dict[str, Dict[str, str]]

    @classmethod
    async def create(
        cls,
        *,
        auth: DirectCredentialProvider[S3SourceAuthConfig],
        logger: ContextualLogger,
        http_client: AirweaveHttpClient,
        config: S3SourceConfig,
    ) -> S3Source:
        """Create a new S3 source instance from credentials and config."""
        instance = cls(auth=auth, logger=logger, http_client=http_client)

        creds: S3SourceAuthConfig = auth.credentials
        instance._access_key_id = creds.aws_access_key_id
        instance._secret_access_key = creds.aws_secret_access_key
        instance._session_token = creds.aws_session_token
        instance._region_name = creds.region_name
        instance._endpoint_url = creds.endpoint_url

        bucket_name, prefix = cls._parse_bucket_target(config)
        instance._bucket_name = bucket_name
        instance._prefix = prefix
        instance._include_patterns = list(config.include_patterns or [])

        instance._download_concurrency = config.s3_download_concurrency
        instance._max_pool_connections = config.s3_max_pool_connections
        instance._connect_timeout = config.s3_connect_timeout
        instance._read_timeout = config.s3_read_timeout
        instance._max_retries = config.s3_max_retries
        instance._metadata_preload_max_files = config.s3_metadata_preload_max_files

        instance._metadata_cache = {}

        return instance

    @staticmethod
    def _parse_bucket_target(config: S3SourceConfig) -> Tuple[str, str]:
        """Resolve (bucket_name, prefix) from ``s3_uri`` or bucket_name/prefix directly."""
        uri = (config.s3_uri or "").strip()
        if uri:
            if not uri.startswith("s3://"):
                raise ValueError(f"Invalid s3_uri (must start with 's3://'): {uri}")
            rest = uri[len("s3://") :]
            bucket, _, key_prefix = rest.partition("/")
            if not bucket:
                raise ValueError(f"Invalid s3_uri (missing bucket name): {uri}")
            if key_prefix and not key_prefix.endswith("/"):
                key_prefix += "/"
            return bucket, key_prefix

        bucket = (config.bucket_name or "").strip()
        if not bucket:
            raise ValueError("S3 source requires either 's3_uri' or 'bucket_name'")
        prefix = (config.prefix or "").strip()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return bucket, prefix

    # -------------------------------------------------------------------------
    # Client construction
    # -------------------------------------------------------------------------

    def _client_kwargs(self, region_name: str) -> Dict[str, Any]:
        """Build aiobotocore create_client() kwargs for the given region."""
        from botocore.config import Config  # noqa: PLC0415

        kwargs: Dict[str, Any] = {
            "region_name": region_name,
            "config": Config(
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                retries={"max_attempts": self._max_retries, "mode": "standard"},
                max_pool_connections=self._max_pool_connections,
            ),
        }
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        if self._access_key_id and self._secret_access_key:
            kwargs["aws_access_key_id"] = self._access_key_id
            kwargs["aws_secret_access_key"] = self._secret_access_key
            if self._session_token:
                kwargs["aws_session_token"] = self._session_token
        return kwargs

    async def _resolve_region(self) -> str:
        """Confirm the bucket is reachable and discover its real region.

        Never logs credential values. On a cross-region redirect
        (301/400/PermanentRedirect), reads ``x-amz-bucket-region`` from the
        error response, falling back to ``get_bucket_location``.
        """
        from aiobotocore.session import get_session  # noqa: PLC0415
        from botocore.exceptions import ClientError  # noqa: PLC0415

        probe_region = self._region_name or DEFAULT_REGION
        session = get_session()

        async with session.create_client("s3", **self._client_kwargs(probe_region)) as client:
            try:
                await client.head_bucket(Bucket=self._bucket_name)
                return probe_region
            except ClientError as e:
                error_code = str(e.response.get("Error", {}).get("Code", ""))
                status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

                if error_code == "404" or status == 404:
                    raise ValueError(f"S3 bucket not found: {self._bucket_name}") from e
                if error_code == "403" or status == 403:
                    raise ValueError(
                        f"Access denied to S3 bucket '{self._bucket_name}' — check IAM "
                        "permissions (s3:HeadBucket, s3:GetBucketLocation, s3:ListBucket, "
                        "s3:GetObject)"
                    ) from e
                if error_code not in ("301", "400", "PermanentRedirect") and status not in (
                    301,
                    400,
                ):
                    raise

                headers = e.response.get("ResponseMetadata", {}).get("HTTPHeaders", {}) or {}
                real_region = headers.get("x-amz-bucket-region")
                if not real_region:
                    location = await client.get_bucket_location(Bucket=self._bucket_name)
                    real_region = location.get("LocationConstraint") or DEFAULT_REGION

                self.logger.info(
                    f"S3 bucket '{self._bucket_name}' is in region '{real_region}', "
                    f"not '{probe_region}' — recreating client for the real region"
                )
                return real_region

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    async def validate(self) -> None:
        """Verify the configured bucket exists and is reachable."""
        if not self._bucket_name:
            raise ValueError("S3 source requires a bucket (s3_uri or bucket_name)")
        region = await self._resolve_region()
        self.logger.info(
            f"S3 bucket validated: s3://{self._bucket_name}/{self._prefix} (region={region})"
        )

    # -------------------------------------------------------------------------
    # Companion metadata sidecars
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_sidecar(key: str) -> bool:
        """Whether this key is a companion metadata file, not a real document."""
        return _SIDECAR_RE.match(key) is not None

    @staticmethod
    def _sidecar_base_key(key: str) -> Optional[str]:
        """Extract the original object key a sidecar's metadata applies to."""
        match = _SIDECAR_RE.match(key)
        return match.group("base") if match else None

    @staticmethod
    def _normalize_metadata(raw: Any) -> Dict[str, str]:
        """Coerce arbitrary JSON values to the Dict[str, str] shape entities expect."""
        normalized: Dict[str, str] = {}
        if not isinstance(raw, dict):
            return normalized
        for k, v in raw.items():
            if v is None:
                continue
            elif isinstance(v, bool):
                normalized[k] = "true" if v else "false"
            elif isinstance(v, (dict, list)):
                normalized[k] = json.dumps(v)
            else:
                normalized[k] = str(v)
        return normalized

    async def _preload_sidecars(self, client: Any, sidecar_keys: List[str]) -> None:
        """Fetch and cache companion metadata sidecars, unless there are too many."""
        if len(sidecar_keys) > self._metadata_preload_max_files:
            self.logger.info(
                f"Skipping metadata sidecar preload: {len(sidecar_keys)} sidecars exceeds "
                f"cap ({self._metadata_preload_max_files})"
            )
            return

        for sidecar_key in sidecar_keys:
            base_key = self._sidecar_base_key(sidecar_key)
            if not base_key:
                continue
            try:
                response = await client.get_object(Bucket=self._bucket_name, Key=sidecar_key)
                async with response["Body"] as stream:
                    raw_bytes = await stream.read()
                data = json.loads(raw_bytes.decode("utf-8"))
            except Exception as e:
                self.logger.warning(
                    f"Failed to load metadata sidecar '{sidecar_key}': {type(e).__name__}"
                )
                continue

            attrs = data.get("metadataAttributes", data) if isinstance(data, dict) else {}
            self._metadata_cache[f"{self._bucket_name}/{base_key}"] = self._normalize_metadata(
                attrs
            )

    def _merged_metadata(
        self, key: str, s3_object_metadata: Optional[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """Merge S3 object user-metadata with any preloaded sidecar metadata."""
        merged: Dict[str, str] = dict(s3_object_metadata or {})
        sidecar = self._metadata_cache.get(f"{self._bucket_name}/{key}")
        if sidecar:
            merged.update(sidecar)
        return merged or None

    # -------------------------------------------------------------------------
    # Listing
    # -------------------------------------------------------------------------

    async def _list_objects(self, client: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
        """List eligible objects and companion sidecar keys under the configured prefix."""
        objects: List[Dict[str, Any]] = []
        sidecar_keys: List[str] = []

        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self._bucket_name, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                if self._is_sidecar(key):
                    sidecar_keys.append(key)
                    continue
                if self._include_patterns:
                    rel_key = key[len(self._prefix) :] if key.startswith(self._prefix) else key
                    if not any(
                        fnmatch.fnmatch(rel_key, pattern) for pattern in self._include_patterns
                    ):
                        continue
                objects.append(obj)

        return objects, sidecar_keys

    # -------------------------------------------------------------------------
    # Download + entity building
    # -------------------------------------------------------------------------

    async def _process_object(
        self,
        client: Any,
        obj: Dict[str, Any],
        files: FileService,
        bucket_breadcrumb: Breadcrumb,
    ) -> AsyncGenerator[BaseEntity, None]:
        """Download one S3 object and yield it as an S3FileEntity."""
        key = obj["Key"]
        file_name = key.rsplit("/", 1)[-1]

        if "." not in file_name:
            self.logger.info(f"Skipping s3://{self._bucket_name}/{key}: no file extension")
            return

        try:
            response = await client.get_object(Bucket=self._bucket_name, Key=key)
            async with response["Body"] as stream:
                content = await stream.read()
        except Exception as e:
            self.logger.warning(
                f"Failed to download s3://{self._bucket_name}/{key}: {type(e).__name__}"
            )
            return

        ext = os.path.splitext(file_name)[1].lstrip(".").lower() or "file"
        mime_type = response.get("ContentType") or mimetypes.guess_type(file_name)[0]

        entity = S3FileEntity(
            key=key,
            bucket_name=self._bucket_name,
            etag=(obj.get("ETag") or "").strip('"') or None,
            storage_class=obj.get("StorageClass"),
            last_modified=obj.get("LastModified"),
            metadata=self._merged_metadata(key, response.get("Metadata")),
            url=f"s3://{self._bucket_name}/{key}",
            size=obj.get("Size", len(content)),
            file_type=ext,
            mime_type=mime_type or "application/octet-stream",
            local_path=None,
            breadcrumbs=[bucket_breadcrumb],
        )

        try:
            await files.save_bytes(
                entity=entity,
                content=content,
                filename_with_extension=file_name,
                logger=self.logger,
            )
        except FileSkippedException as e:
            self.logger.debug(f"Skipping s3://{self._bucket_name}/{key}: {e.reason}")
            return

        if not entity.local_path:
            return

        yield entity

    # -------------------------------------------------------------------------
    # Entity generation
    # -------------------------------------------------------------------------

    async def generate_entities(
        self,
        *,
        cursor: SyncCursor | None = None,
        files: FileService | None = None,
        node_selections: list[NodeSelectionData] | None = None,
    ) -> AsyncGenerator[BaseEntity, None]:
        """Generate the bucket entity followed by every eligible object."""
        assert files is not None, "FileService is required for S3"

        self._metadata_cache.clear()

        region = await self._resolve_region()

        from aiobotocore.session import get_session  # noqa: PLC0415

        session = get_session()
        async with session.create_client("s3", **self._client_kwargs(region)) as client:
            yield S3BucketEntity(
                bucket_name=self._bucket_name,
                region=region,
                prefix=self._prefix,
                endpoint_url=self._endpoint_url,
                breadcrumbs=[],
            )

            bucket_breadcrumb = Breadcrumb(
                entity_id=self._bucket_name,
                name=self._bucket_name,
                entity_type="S3BucketEntity",
            )

            objects, sidecar_keys = await self._list_objects(client)

            if sidecar_keys:
                await self._preload_sidecars(client, sidecar_keys)

            async def _worker(obj: Dict[str, Any]) -> AsyncGenerator[BaseEntity, None]:
                async for entity in self._process_object(client, obj, files, bucket_breadcrumb):
                    yield entity

            async for entity in self.process_entities_concurrent(
                objects,
                _worker,
                batch_size=self._download_concurrency,
            ):
                yield entity
