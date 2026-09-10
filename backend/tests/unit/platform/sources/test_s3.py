"""Unit tests for the AWS S3 source connector.

No real AWS calls — the aiobotocore client is faked at the boundary
(head_bucket / get_bucket_location / get_paginator / get_object), matching
the mocking convention used for sharepoint2019v2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError

from airweave.domains.sources.token_providers.credential import DirectCredentialProvider
from airweave.domains.storage import FileSkippedException
from airweave.platform.configs.auth import S3SourceAuthConfig
from airweave.platform.configs.config import S3SourceConfig
from airweave.platform.entities.s3 import S3BucketEntity, S3FileEntity
from airweave.platform.sources.s3 import S3Source

# ---------------------------------------------------------------------------
# Fakes for the aiobotocore boundary
# ---------------------------------------------------------------------------


class _FakeAsyncCM:
    """Minimal async context manager wrapping a fixed object."""

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    async def __aenter__(self) -> Any:
        return self._obj

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeBody(_FakeAsyncCM):
    """Fakes an S3 object's streaming Body."""

    def __init__(self, data: bytes) -> None:
        super().__init__(self)
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def _aiter(items: List[Any]):
    for item in items:
        yield item


class _FakePaginator:
    def __init__(self, pages: List[Dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **kwargs: Any):
        return _aiter(self._pages)


class _FakeS3Client:
    """Fakes the subset of the aiobotocore S3 client surface S3Source uses."""

    def __init__(
        self,
        *,
        pages: Optional[List[Dict[str, Any]]] = None,
        objects: Optional[Dict[str, Dict[str, Any]]] = None,
        head_bucket_error: Optional[Exception] = None,
        get_bucket_location_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._pages = pages or []
        self._objects = objects or {}
        self.head_bucket_calls: List[str] = []
        self._head_bucket_error = head_bucket_error
        self._get_bucket_location_result = get_bucket_location_result or {
            "LocationConstraint": "us-east-1"
        }

    async def head_bucket(self, Bucket: str) -> None:
        self.head_bucket_calls.append(Bucket)
        if self._head_bucket_error:
            raise self._head_bucket_error

    async def get_bucket_location(self, Bucket: str) -> Dict[str, Any]:
        return self._get_bucket_location_result

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "list_objects_v2"
        return _FakePaginator(self._pages)

    async def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        obj = self._objects[Key]
        return {
            "Body": _FakeBody(obj["content"]),
            "ContentType": obj.get("content_type"),
            "Metadata": obj.get("metadata", {}),
        }


class _FakeSession:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    def create_client(self, service_name: str, **kwargs: Any) -> _FakeAsyncCM:
        assert service_name == "s3"
        return _FakeAsyncCM(self._client)


def _patch_aiobotocore(monkeypatch: pytest.MonkeyPatch, client: _FakeS3Client) -> None:
    monkeypatch.setattr("aiobotocore.session.get_session", lambda: _FakeSession(client))


def _client_error(code: str, status: int, headers: Optional[Dict[str, str]] = None) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": status, "HTTPHeaders": headers or {}},
        },
        "HeadBucket",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_auth(creds: S3SourceAuthConfig) -> DirectCredentialProvider[S3SourceAuthConfig]:
    return DirectCredentialProvider(credentials=creds, source_short_name="s3")


async def _make_source(
    *,
    auth_kwargs: Optional[Dict[str, Any]] = None,
    config_kwargs: Optional[Dict[str, Any]] = None,
) -> S3Source:
    creds = S3SourceAuthConfig(**(auth_kwargs or {}))
    config = S3SourceConfig(**(config_kwargs or {"bucket_name": "my-bucket"}))
    return await S3Source.create(
        auth=_mock_auth(creds),
        logger=MagicMock(),
        http_client=AsyncMock(),
        config=config,
    )


class _FakeFileService:
    """Stands in for FileService.save_bytes — just sets local_path."""

    def __init__(self, *, skip_keys: Optional[set] = None) -> None:
        self.skip_keys = skip_keys or set()
        self.saved: List[str] = []

    async def save_bytes(self, *, entity, content, filename_with_extension, logger):
        if entity.key in self.skip_keys:
            raise FileSkippedException(reason="test skip", filename=filename_with_extension)
        entity.local_path = f"/tmp/{filename_with_extension}"
        self.saved.append(entity.key)
        return entity


# ---------------------------------------------------------------------------
# S3SourceAuthConfig validation
# ---------------------------------------------------------------------------


class TestS3SourceAuthConfig:
    def test_no_credentials_uses_default_chain(self):
        creds = S3SourceAuthConfig()
        assert creds.aws_access_key_id is None
        assert creds.aws_secret_access_key is None

    def test_explicit_credentials_together(self):
        creds = S3SourceAuthConfig(aws_access_key_id="AKIA...", aws_secret_access_key="secret")
        assert creds.aws_access_key_id == "AKIA..."

    def test_partial_credentials_key_only_rejected(self):
        with pytest.raises(ValueError):
            S3SourceAuthConfig(aws_access_key_id="AKIA...")

    def test_partial_credentials_secret_only_rejected(self):
        with pytest.raises(ValueError):
            S3SourceAuthConfig(aws_secret_access_key="secret")


# ---------------------------------------------------------------------------
# create() / config parsing
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_with_explicit_creds(self):
        source = await _make_source(
            auth_kwargs={"aws_access_key_id": "AKIA...", "aws_secret_access_key": "s3cr3t"},
        )
        assert source._access_key_id == "AKIA..."
        assert source._secret_access_key == "s3cr3t"

    @pytest.mark.asyncio
    async def test_create_with_default_chain(self):
        source = await _make_source()
        assert source._access_key_id is None
        assert source._secret_access_key is None

    @pytest.mark.asyncio
    async def test_create_from_bucket_name_and_prefix(self):
        source = await _make_source(config_kwargs={"bucket_name": "my-bucket", "prefix": "docs"})
        assert source._bucket_name == "my-bucket"
        assert source._prefix == "docs/"

    @pytest.mark.asyncio
    async def test_create_from_s3_uri(self):
        source = await _make_source(config_kwargs={"s3_uri": "s3://my-bucket/docs/reports"})
        assert source._bucket_name == "my-bucket"
        assert source._prefix == "docs/reports/"

    @pytest.mark.asyncio
    async def test_create_from_s3_uri_no_prefix(self):
        source = await _make_source(config_kwargs={"s3_uri": "s3://my-bucket"})
        assert source._bucket_name == "my-bucket"
        assert source._prefix == ""

    def test_config_requires_bucket_or_uri(self):
        with pytest.raises(ValueError):
            S3SourceConfig()


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------


class TestValidate:
    @pytest.mark.asyncio
    async def test_validate_success(self, monkeypatch):
        client = _FakeS3Client()
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        await source.validate()
        assert client.head_bucket_calls == ["my-bucket"]

    @pytest.mark.asyncio
    async def test_validate_bucket_not_found(self, monkeypatch):
        client = _FakeS3Client(head_bucket_error=_client_error("404", 404))
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        with pytest.raises(ValueError, match="not found"):
            await source.validate()

    @pytest.mark.asyncio
    async def test_validate_access_denied(self, monkeypatch):
        client = _FakeS3Client(head_bucket_error=_client_error("403", 403))
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        with pytest.raises(ValueError, match="Access denied"):
            await source.validate()

    @pytest.mark.asyncio
    async def test_validate_region_redirect_uses_header(self, monkeypatch):
        client = _FakeS3Client(
            head_bucket_error=_client_error(
                "301", 301, headers={"x-amz-bucket-region": "eu-west-1"}
            )
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        await source.validate()

    @pytest.mark.asyncio
    async def test_validate_region_redirect_falls_back_to_get_bucket_location(self, monkeypatch):
        client = _FakeS3Client(
            head_bucket_error=_client_error("400", 400),
            get_bucket_location_result={"LocationConstraint": "eu-central-1"},
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        await source.validate()

    @pytest.mark.asyncio
    async def test_validate_empty_location_constraint_is_us_east_1(self, monkeypatch):
        client = _FakeS3Client(
            head_bucket_error=_client_error("301", 301),
            get_bucket_location_result={"LocationConstraint": None},
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        await source.validate()


# ---------------------------------------------------------------------------
# generate_entities()
# ---------------------------------------------------------------------------


def _page(keys: List[str]) -> Dict[str, Any]:
    return {
        "Contents": [
            {"Key": k, "Size": 10, "ETag": '"abc"', "StorageClass": "STANDARD"} for k in keys
        ]
    }


class TestGenerateEntities:
    @pytest.mark.asyncio
    async def test_yields_bucket_then_files(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["report.pdf", "notes.md"])],
            objects={
                "report.pdf": {"content": b"pdf-bytes"},
                "notes.md": {"content": b"# notes"},
            },
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]

        bucket_entities = [e for e in entities if isinstance(e, S3BucketEntity)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert len(bucket_entities) == 1
        assert bucket_entities[0].bucket_name == "my-bucket"
        assert {e.key for e in file_entities} == {"report.pdf", "notes.md"}

    @pytest.mark.asyncio
    async def test_skips_folder_markers(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["docs/", "docs/report.pdf"])],
            objects={"docs/report.pdf": {"content": b"pdf-bytes"}},
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert {e.key for e in file_entities} == {"docs/report.pdf"}

    @pytest.mark.asyncio
    async def test_skips_metadata_sidecar_as_entity(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["notes.md", "notes.md.metadata.json"])],
            objects={
                "notes.md": {"content": b"# notes"},
                "notes.md.metadata.json": {"content": b'{"metadataAttributes": {"author": "kb"}}'},
            },
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert {e.key for e in file_entities} == {"notes.md"}

    @pytest.mark.asyncio
    async def test_sidecar_metadata_merged_into_file_entity(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["notes.md", "notes.md.metadata.json"])],
            objects={
                "notes.md": {"content": b"# notes"},
                "notes.md.metadata.json": {
                    "content": (
                        b'{"metadataAttributes": '
                        b'{"author": "kb", "confidential": true, "tags": ["a", "b"]}}'
                    )
                },
            },
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]
        note_entity = next(
            e for e in entities if isinstance(e, S3FileEntity) and e.key == "notes.md"
        )
        assert note_entity.metadata["author"] == "kb"
        assert note_entity.metadata["confidential"] == "true"
        assert note_entity.metadata["tags"] == '["a", "b"]'

    @pytest.mark.asyncio
    async def test_include_patterns_filter_keys(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["report.pdf", "image.png"])],
            objects={
                "report.pdf": {"content": b"pdf-bytes"},
                "image.png": {"content": b"png-bytes"},
            },
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source(
            config_kwargs={"bucket_name": "my-bucket", "include_patterns": ["*.pdf"]}
        )
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert {e.key for e in file_entities} == {"report.pdf"}

    @pytest.mark.asyncio
    async def test_one_download_failure_does_not_abort_sync(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["good.pdf", "bad.pdf"])],
            objects={"good.pdf": {"content": b"pdf-bytes"}},  # "bad.pdf" missing -> KeyError
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService()

        entities = [e async for e in source.generate_entities(files=files)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert {e.key for e in file_entities} == {"good.pdf"}

    @pytest.mark.asyncio
    async def test_file_skipped_exception_does_not_abort_sync(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["good.pdf", "skip.exe"])],
            objects={
                "good.pdf": {"content": b"pdf-bytes"},
                "skip.exe": {"content": b"exe-bytes"},
            },
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source()
        files = _FakeFileService(skip_keys={"skip.exe"})

        entities = [e async for e in source.generate_entities(files=files)]
        file_entities = [e for e in entities if isinstance(e, S3FileEntity)]
        assert {e.key for e in file_entities} == {"good.pdf"}

    @pytest.mark.asyncio
    async def test_no_secrets_in_log_calls(self, monkeypatch):
        client = _FakeS3Client(
            pages=[_page(["report.pdf"])], objects={"report.pdf": {"content": b"x"}}
        )
        _patch_aiobotocore(monkeypatch, client)
        source = await _make_source(
            auth_kwargs={"aws_access_key_id": "AKIASECRET", "aws_secret_access_key": "topsecret"}
        )
        files = _FakeFileService()

        _ = [e async for e in source.generate_entities(files=files)]

        for call in source.logger.mock_calls:
            call_text = str(call)
            assert "topsecret" not in call_text
            assert "AKIASECRET" not in call_text
