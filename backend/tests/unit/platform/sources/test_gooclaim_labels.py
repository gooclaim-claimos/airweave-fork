"""Gooclaim (T531): which insurance product an uploaded document covers.

The UIN printed on the first pages is read at upload as a SUGGESTION; the tenant confirms
it (or says the document is general); only a confirmed label scopes a member's search.
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import fitz  # PyMuPDF
import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from airweave.api.v1.endpoints import upload_labels, uploads
from airweave.core.config import settings
from airweave.domains.storage.paths import StoragePaths
from airweave.platform.sources.gooclaim_labels import DocumentLabels, detect_uins

ORG = uuid4()
OTHER = uuid4()
UIN = "GODHLIP24179V022324"


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


def _pdf(first_page: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), first_page)
    doc.new_page().insert_text((72, 72), "Section 4. Room rent up to 2% of the sum insured.")
    data = doc.tobytes()
    doc.close()
    return data


def test_a_uin_is_found_in_the_words_around_it() -> None:
    text = (
        "Go Digit General Insurance Limited Arogya Sanjeevani Policy - "
        "Policy Wording (GODHLIP24179V022324)"
    )
    assert detect_uins(text) == [UIN]
    assert detect_uins("UIN: unihlgp25038v042425 and UIN: UNIHLGP25038V042425") == [
        "UNIHLGP25038V042425"
    ]
    assert detect_uins("Policy No MAG/HI/4529381, claim 26-0001") == []


async def _upload(org: UUID = ORG, first_page: str = f"Arogya Sanjeevani Policy UIN: {UIN}") -> str:
    stored = await uploads.upload_file(
        connection_id="policy-docs",
        file=UploadFile(file=io.BytesIO(_pdf(first_page)), filename="wording.pdf"),
        description=None,
        ctx=_ctx(org),
    )
    assert stored.detected_uins == ([UIN] if UIN in first_page else [])
    return stored.upload_id


async def test_the_uin_on_page_one_is_a_suggestion_until_the_tenant_confirms() -> None:
    upload_id = await _upload()
    listed = (await uploads.list_uploads(connection_id="policy-docs", ctx=_ctx())).items[0]
    assert (listed.detected_uins, listed.product_uins, listed.applies_to) == ([UIN], [], None)

    confirmed = await upload_labels.set_labels(
        connection_id="policy-docs",
        upload_id=upload_id,
        labels=DocumentLabels(product_uins=[UIN.lower()]),
        ctx=_ctx(),
    )
    assert (confirmed.product_uins, confirmed.applies_to) == ([UIN], "products")
    listed = (await uploads.list_uploads(connection_id="policy-docs", ctx=_ctx())).items[0]
    assert (listed.product_uins, listed.applies_to, listed.file_name) == (
        [UIN],
        "products",
        "wording.pdf",
    )


async def test_a_general_document_applies_to_every_member_and_carries_no_product() -> None:
    upload_id = await _upload(first_page="Claims process for all members")
    got = await upload_labels.set_labels(
        connection_id="policy-docs",
        upload_id=upload_id,
        labels=DocumentLabels(product_uins=[UIN], applies_to="general"),
        ctx=_ctx(),
    )
    assert (got.product_uins, got.applies_to) == ([], "general")


def test_only_an_irdai_uin_is_a_product_label() -> None:
    with pytest.raises(ValidationError):
        DocumentLabels(product_uins=["MAG/HI/4529381"])


async def test_another_organisations_upload_cannot_be_labelled() -> None:
    upload_id = await _upload(org=ORG)
    with pytest.raises(HTTPException) as caught:
        await upload_labels.set_labels(
            connection_id="policy-docs",
            upload_id=upload_id,
            labels=DocumentLabels(product_uins=[UIN]),
            ctx=_ctx(OTHER),
        )
    assert caught.value.status_code == 404


async def test_a_bad_upload_id_is_refused() -> None:
    with pytest.raises(HTTPException) as caught:
        await upload_labels.set_labels(
            connection_id="policy-docs", upload_id="../x", labels=DocumentLabels(), ctx=_ctx()
        )
    assert caught.value.status_code == 400
