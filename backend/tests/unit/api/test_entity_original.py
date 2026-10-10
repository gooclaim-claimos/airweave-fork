"""GET /entities/{entity_id}/original — the file a cited passage was read from.

Orion opens a citation at its page in the original upload. The entity is found
only in a collection the caller may read, and the file is read from the
CALLER'S OWN bucket of the name its record gives — never from a path the
index names.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response

from airweave.api.v1.endpoints import entities
from airweave.core.config import settings
from airweave.platform.sources.gooclaim_upload import bucket_dir

ORG = uuid4()
COLLECTION = str(uuid4())
PDF = b"%PDF-1.4 room rent"


@pytest.fixture(autouse=True)
def _storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "STORAGE_PATH", str(tmp_path / "storage"))


def _ctx(org: UUID = ORG) -> MagicMock:
    ctx = MagicMock()
    ctx.organization = SimpleNamespace(id=org)
    ctx.logger = MagicMock()
    return ctx


def _db() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = iter([COLLECTION])
    db.execute.return_value = result
    return db


def _vespa(url: str, mime: str = "application/pdf") -> type:
    fields = {
        "entity_id": "u1__chunk_3",
        "data_sources_system_metadata_collection_id": COLLECTION,
        "url": url,
        "mime_type": mime,
    }

    class _Resp:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"root": {"children": [{"fields": fields}]}}

    class _Client:
        def __init__(self, **_kw: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def post(self, url: str, json: dict[str, object]) -> _Resp:
            return _Resp()

    return _Client


def _stored(org: UUID = ORG) -> Path:
    bucket = bucket_dir(org, "policy-docs")
    bucket.mkdir(parents=True, exist_ok=True)
    path = bucket / "u1__wording.pdf"
    path.write_bytes(PDF)
    return path


async def _open(url: str, ctx: MagicMock | None = None) -> Response:
    with patch.object(entities.httpx, "AsyncClient", _vespa(url)):
        return await entities.get_entity_original("u1__chunk_3", ctx=ctx or _ctx(), db=_db())


async def test_a_cited_passage_opens_its_original_file() -> None:
    _stored()
    resp = await _open("gooclaim-upload://policy-docs/u1__wording.pdf")
    assert resp.body == PDF
    assert resp.media_type == "application/pdf"
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_the_file_is_read_from_the_callers_own_bucket_only() -> None:
    _stored(uuid4())  # the same bucket name, another organisation's
    with pytest.raises(HTTPException) as caught:
        await _open("gooclaim-upload://policy-docs/u1__wording.pdf")
    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/wording.pdf",  # another source keeps no original here
        "gooclaim-upload://policy-docs/../other/u1__wording.pdf",
        "gooclaim-upload://../u1__wording.pdf",
        "gooclaim-upload://policy-docs/..",
        "gooclaim-upload://policy-docs",
        "",
    ],
)
async def test_a_record_naming_anything_but_a_file_in_a_bucket_reads_as_not_found(
    url: str,
) -> None:
    _stored()
    with pytest.raises(HTTPException) as caught:
        await _open(url)
    assert caught.value.status_code == 404


async def test_a_file_no_longer_on_disk_says_so() -> None:
    bucket_dir(ORG, "policy-docs").mkdir(parents=True)
    with pytest.raises(HTTPException) as caught:
        await _open("gooclaim-upload://policy-docs/u1__gone.pdf")
    assert caught.value.status_code == 404
    assert "no longer kept" in str(caught.value.detail)


async def test_an_entity_the_caller_may_not_read_is_not_found() -> None:
    _stored()
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = iter([str(uuid4())])  # not the entity's collection
    db.execute.return_value = result
    with patch.object(
        entities.httpx, "AsyncClient", _vespa("gooclaim-upload://policy-docs/u1__wording.pdf")
    ):
        with pytest.raises(HTTPException) as caught:
            await entities.get_entity_original("u1__chunk_3", ctx=_ctx(), db=db)
    assert caught.value.status_code == 404


def test_the_vespa_app_has_one_schema_in_two_places() -> None:
    """The box's compose and the helm chart deploy the same Vespa app — one copy drifted once."""
    root = Path(__file__).parents[4]
    docker, helm = root / "vespa" / "app", root / "helm" / "datasources-vespa" / "files" / "app"
    names = sorted(p.relative_to(docker) for p in docker.rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(helm) for p in helm.rglob("*") if p.is_file())
    for name in names:
        assert (docker / name).read_bytes() == (helm / name).read_bytes(), name
