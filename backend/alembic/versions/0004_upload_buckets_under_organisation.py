"""Upload buckets move under their organisation.

Gooclaim native upload: a bucket was ``STORAGE_PATH/uploads/{bucket}`` for
every organisation, and the source read whatever ``upload_dir`` its source
connection's config named. Buckets now live at
``STORAGE_PATH/uploads/{organization_id}/{bucket}`` and the source refuses any
other directory (``GooclaimUploadSource.check_config``).

This moves each existing gooclaim_upload source connection's bucket under its
organisation and points its config there. It runs where the files are (the
backend, on startup), once: a bucket already in place is left alone, and a
name that already exists at the destination is never overwritten — it stays
behind and is logged.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10 00:00:00.000000

"""

import json
import logging
import shutil
from pathlib import Path

import sqlalchemy as sa

from airweave.platform.sources.gooclaim_upload import BUCKET_PATTERN, uploads_root
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0004")


def _move(old: Path, new: Path) -> None:
    """Move a bucket's files from ``old`` to ``new``, never over an existing name."""
    if not old.is_dir() or old.resolve() == new.resolve():
        return
    new.mkdir(parents=True, exist_ok=True)
    for entry in old.iterdir():
        target = new / entry.name
        if target.exists():
            log.warning("upload bucket move: %s already exists, left at %s", target, entry)
            continue
        shutil.move(str(entry), str(target))
    if not any(old.iterdir()):
        old.rmdir()


def _rebucket(*, under_organisation: bool) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, organization_id, config_fields FROM source_connection "
            "WHERE short_name = 'gooclaim_upload'"
        )
    ).fetchall()
    root = uploads_root()
    for row in rows:
        raw = row.config_fields
        # A raw query's JSON column arrives decoded or as text, by driver.
        config = dict(json.loads(raw) if isinstance(raw, str) else raw or {})
        old = Path(str(config.get("upload_dir") or ""))
        if not BUCKET_PATTERN.match(old.name):
            log.warning("upload bucket move: source connection %s has no bucket name", row.id)
            continue
        new = root / str(row.organization_id) / old.name if under_organisation else root / old.name
        _move(old, new)
        config["upload_dir"] = str(new)
        conn.execute(
            sa.text(
                "UPDATE source_connection SET config_fields = :config WHERE id = :id"
            ).bindparams(sa.bindparam("config", type_=sa.JSON)),
            {"config": config, "id": row.id},
        )


def upgrade():
    """Move every upload bucket under its organisation."""
    _rebucket(under_organisation=True)


def downgrade():
    """Put every upload bucket back in the shared folder."""
    _rebucket(under_organisation=False)
