"""Gooclaim native upload: the original stays, and a bucket is one organisation's.

Found 2026-10-10, both in code:
- the pipeline deletes every FileEntity's ``local_path`` after the batch, and
  ``local_path`` WAS the uploaded original — a document left the disk after
  its first sync;
- every organisation's buckets sat in one ``uploads/`` folder and the source
  read whatever directory its config named.
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile

from airweave import schemas
from airweave.api.v1.endpoints import uploads
from airweave.core.config import settings
from airweave.domains.storage.file_service import FileService
from airweave.domains.storage.paths import StoragePaths
from airweave.platform.configs.config import GooclaimUploadConfig
from airweave.platform.entities.gooclaim_upload import GooclaimUploadFileEntity
from airweave.platform.sources.gooclaim_upload import (
    GooclaimUploadSource,
    bucket_dir,
    uploads_root,
)

ORG = uuid4()
OTHER = uuid4()
PDF = b"%PDF-1.4 room rent is capped at 1% of the sum insured"


@pytest.fixture(autouse=True)
def _storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setattr(StoragePaths, "TEMP_PROCESSING", str(tmp_path / "processing"))
    return tmp_path


def _ctx(org: UUID = ORG) -> MagicMock:
    ctx = MagicMock()
    ctx.organization = SimpleNamespace(id=org)
    ctx.user = None
    return ctx


# ─── a bucket is one organisation's ────────────────────────────────


def test_a_bucket_lives_under_its_organisation() -> None:
    assert bucket_dir(ORG, "policy-docs") == uploads_root() / str(ORG) / "policy-docs"
    for unsafe in ("..", "a/b", "", "x" * 129, "../../etc"):
        with pytest.raises(ValueError):
            bucket_dir(ORG, unsafe)


@pytest.mark.parametrize(
    "upload_dir",
    [
        lambda: str(bucket_dir(OTHER, "policy-docs")),  # another organisation's
        lambda: str(uploads_root() / "policy-docs"),  # the old, shared layout
        lambda: str(uploads_root() / str(ORG) / ".." / str(OTHER) / "policy-docs"),
        lambda: "/etc",
        lambda: str(uploads_root() / str(ORG)),  # the organisation's root, not a bucket
        lambda: "",
    ],
)
def test_a_config_naming_anything_but_this_organisations_bucket_is_refused(
    upload_dir: Callable[[], str],
) -> None:
    with pytest.raises(ValueError):
        GooclaimUploadSource.check_config(
            GooclaimUploadConfig(upload_dir=upload_dir()), organization_id=ORG
        )


def test_this_organisations_own_bucket_is_accepted() -> None:
    GooclaimUploadSource.check_config(
        GooclaimUploadConfig(upload_dir=str(bucket_dir(ORG, "policy-docs"))), organization_id=ORG
    )


async def test_an_upload_lands_in_the_callers_own_bucket_and_others_cannot_list_it() -> None:
    stored = await uploads.upload_file(
        connection_id="policy-docs",
        file=UploadFile(file=io.BytesIO(PDF), filename="wording.pdf"),
        description=None,
        ctx=_ctx(ORG),
    )
    assert Path(stored.stored_path).parent == bucket_dir(ORG, "policy-docs")

    mine = await uploads.list_uploads(connection_id="policy-docs", ctx=_ctx(ORG))
    theirs = await uploads.list_uploads(connection_id="policy-docs", ctx=_ctx(OTHER))
    assert [i.file_name for i in mine.items] == ["wording.pdf"]
    assert theirs.items == []


async def test_an_unsafe_bucket_name_is_a_400() -> None:
    with pytest.raises(HTTPException) as caught:
        await uploads.list_uploads(connection_id="..", ctx=_ctx())
    assert caught.value.status_code == 400


# ─── the original stays ────────────────────────────────────────────


async def _sync(upload_dir: Path, files: FileService | None) -> list[object]:
    source = await GooclaimUploadSource.create(
        auth=MagicMock(),
        logger=MagicMock(),
        http_client=MagicMock(),
        config=GooclaimUploadConfig(upload_dir=str(upload_dir)),
    )
    return [e async for e in source.generate_entities(files=files)]


async def test_the_pipeline_is_given_a_copy_and_the_original_survives_its_cleanup() -> None:
    bucket = bucket_dir(ORG, "policy-docs")
    bucket.mkdir(parents=True)
    original = bucket / "u1__wording.pdf"
    original.write_bytes(PDF)
    (bucket / "notes.exe").write_bytes(b"skip me")  # not a supported type

    files = FileService(sync_job_id=uuid4(), storage_backend=MagicMock())
    entities = await _sync(bucket, files)
    docs = [e for e in entities if isinstance(e, GooclaimUploadFileEntity)]
    assert len(docs) == 1
    assert docs[0].local_path is not None
    copy = Path(docs[0].local_path)
    assert copy != original and copy.read_bytes() == PDF

    os.remove(copy)  # what CleanupService does after the batch
    assert original.read_bytes() == PDF

    # and the next sync still finds it
    again = await _sync(bucket, FileService(sync_job_id=uuid4(), storage_backend=MagicMock()))
    assert len([e for e in again if isinstance(e, GooclaimUploadFileEntity)]) == 1


async def test_without_the_syncs_file_service_no_original_is_handed_out() -> None:
    bucket = bucket_dir(ORG, "policy-docs")
    bucket.mkdir(parents=True)
    (bucket / "u1__wording.pdf").write_bytes(PDF)
    with pytest.raises(RuntimeError):
        await _sync(bucket, None)


# ─── a library says who it answers ─────────────────────────────────


class _Collections:
    """The collection service: one existing library, or none."""

    def __init__(self, existing: object | None) -> None:
        self.existing = existing
        self.created: list[object] = []

    async def get(self, db: object, *, readable_id: str, ctx: object) -> object:
        if self.existing is None:
            raise LookupError(readable_id)
        return self.existing

    async def create(self, db: object, *, collection_in: object, ctx: object) -> object:
        self.created.append(collection_in)
        return collection_in


async def _commit_to(service: _Collections, audience: str | None) -> object:
    return await uploads._find_or_create_collection(
        MagicMock(), _ctx(), service, readable_id="sops", name="Claims SOPs", audience=audience
    )


async def test_a_new_library_is_made_only_when_the_uploader_chose_who_it_answers() -> None:
    nobody_chose = _Collections(None)
    with pytest.raises(HTTPException) as caught:
        await _commit_to(nobody_chose, None)
    assert caught.value.status_code == 400 and nobody_chose.created == []
    assert "Choose who these documents may answer" in str(caught.value.detail)

    staff = _Collections(None)
    made = await _commit_to(staff, "staff")
    assert isinstance(made, schemas.CollectionCreate) and made.audience == "staff"


async def test_files_never_land_in_a_library_made_for_the_other_audience() -> None:
    members = _Collections(SimpleNamespace(audience="members"))
    with pytest.raises(HTTPException) as caught:
        await _commit_to(members, "staff")
    assert caught.value.status_code == 409
    assert await _commit_to(members, "members") is members.existing
    assert await _commit_to(members, None) is members.existing  # re-sync, nothing chosen
