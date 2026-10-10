"""Alembic 0004 moves each existing upload bucket under its organisation.

It runs once, on the backend, where the files are; it never overwrites a file
already at the destination, and its downgrade puts things back.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from airweave.core.config import settings
from airweave.platform.sources.gooclaim_upload import bucket_dir, uploads_root

_PATH = (
    Path(__file__).parents[4] / "alembic" / "versions" / "0004_upload_buckets_under_organisation.py"
)
_spec = importlib.util.spec_from_file_location("migration_0004", _PATH)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

ORG = uuid4()


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "STORAGE_PATH", str(tmp_path / "storage"))
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE source_connection "
                "(id TEXT, organization_id TEXT, short_name TEXT, config_fields JSON)"
            )
        )
        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        yield conn


def _add(conn: sa.Connection, sc_id: str, short_name: str, upload_dir: str) -> None:
    conn.execute(
        sa.text("INSERT INTO source_connection VALUES (:id, :org, :short, :cfg)"),
        {
            "id": sc_id,
            "org": str(ORG),
            "short": short_name,
            "cfg": json.dumps({"upload_dir": upload_dir, "scope": "tenant"}),
        },
    )


def _config(conn: sa.Connection, sc_id: str) -> dict[str, object]:
    raw = conn.execute(
        sa.text("SELECT config_fields FROM source_connection WHERE id = :id"), {"id": sc_id}
    ).scalar_one()
    return json.loads(raw) if isinstance(raw, str) else raw


def test_a_bucket_moves_under_its_organisation_and_back(db: sa.Connection) -> None:
    old = uploads_root() / "policy-docs"
    old.mkdir(parents=True)
    (old / "u1__wording.pdf").write_bytes(b"pdf")
    (old / "u1__wording.pdf.gooclaim.json").write_text("{}")
    _add(db, "sc-1", "gooclaim_upload", str(old))
    _add(db, "sc-2", "github", "/somewhere")

    migration.upgrade()
    new = bucket_dir(ORG, "policy-docs")
    assert (new / "u1__wording.pdf").read_bytes() == b"pdf"
    assert (new / "u1__wording.pdf.gooclaim.json").exists()
    assert not old.exists()
    assert _config(db, "sc-1") == {"upload_dir": str(new), "scope": "tenant"}
    assert _config(db, "sc-2")["upload_dir"] == "/somewhere"  # other sources untouched

    migration.upgrade()  # twice is once
    assert (new / "u1__wording.pdf").exists()

    migration.downgrade()
    assert (old / "u1__wording.pdf").read_bytes() == b"pdf"
    assert _config(db, "sc-1")["upload_dir"] == str(old)


def test_a_file_already_at_the_destination_is_never_overwritten(db: sa.Connection) -> None:
    old = uploads_root() / "policy-docs"
    old.mkdir(parents=True)
    (old / "same.pdf").write_bytes(b"old")
    (old / "only-old.pdf").write_bytes(b"moved")
    new = bucket_dir(ORG, "policy-docs")
    new.mkdir(parents=True)
    (new / "same.pdf").write_bytes(b"new")
    _add(db, "sc-1", "gooclaim_upload", str(old))

    migration.upgrade()
    assert (new / "same.pdf").read_bytes() == b"new"
    assert (old / "same.pdf").read_bytes() == b"old"  # left behind, logged
    assert (new / "only-old.pdf").read_bytes() == b"moved"


def test_a_config_with_no_bucket_name_is_left_alone(db: sa.Connection) -> None:
    _add(db, "sc-1", "gooclaim_upload", "")
    migration.upgrade()
    assert _config(db, "sc-1")["upload_dir"] == ""
