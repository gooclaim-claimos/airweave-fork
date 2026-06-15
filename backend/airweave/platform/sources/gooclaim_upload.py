"""Gooclaim native upload source — files written into a per-connection directory.

Architecturally this is a 'reading' source like Dropbox, except the backing
store is the Gooclaim platform's own filesystem instead of an external API.
Files land in the upload_dir via `POST /api/uploads/{connection_id}` (added
in phase 2) and `generate_entities()` re-reads that directory on every sync.

Each `generate_entities()` call:
  1. Yields one `GooclaimUploadConnectionEntity` to anchor the browse tree.
  2. Walks the upload_dir, building one `GooclaimUploadFileEntity` per
     supported file. The downstream pipeline reads `local_path` via the
     standard FileEntity contract and runs the converter chain
     (pdf.py / docx.py / pptx.py / html.py / txt.py).

Auth: none. The platform's tenant + RBAC chain governs who can write to
the upload directory; once a file is on disk we trust it as in-scope for
the owning source connection.
"""

from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Literal

from airweave.core.logging import ContextualLogger
from airweave.domains.browse_tree.types import NodeSelectionData
from airweave.domains.sources.token_providers.protocol import SourceAuthProvider
from airweave.domains.storage.file_service import FileService
from airweave.domains.syncs.cursors.cursor import SyncCursor
from airweave.platform.configs.auth import GooclaimUploadAuthConfig  # noqa: F401
from airweave.platform.configs.config import GooclaimUploadConfig
from airweave.platform.decorators import source
from airweave.platform.entities._base import BaseEntity, Breadcrumb
from airweave.platform.entities.gooclaim_upload import (
    GooclaimUploadConnectionEntity,
    GooclaimUploadFileEntity,
)
from airweave.platform.http_client.airweave_client import AirweaveHttpClient
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod

# File extensions whose contents the converter chain knows how to extract.
# Anything outside this set is skipped (with a warning) so a stray
# `.DS_Store` or partial upload doesn't propagate into the index.
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".pptx", ".txt", ".md", ".html", ".htm", ".csv", ".json"}
)

# Sidecar file the upload endpoint writes next to every uploaded file —
# carries upload_id + uploaded_at + uploaded_by + description so they
# can be reconstructed on subsequent sync runs (the file itself only
# holds bytes + filename).
_SIDECAR_SUFFIX: str = ".gooclaim.json"


@source(
    name="Native Upload",
    short_name="gooclaim_upload",
    auth_methods=[AuthenticationMethod.DIRECT],
    oauth_type=None,
    auth_config_class=GooclaimUploadAuthConfig,
    config_class=GooclaimUploadConfig,
    labels=["Gooclaim", "File Storage"],
    supports_continuous=False,
)
class GooclaimUploadSource(BaseSource):
    """Read files directly uploaded into a Gooclaim platform storage path."""

    # Instance attributes set inside `create()` from the source connection
    # config. Declared at class level so pyright recognises the typed
    # assignments below.
    _upload_dir: str
    _scope: Literal["global", "tenant"]

    @classmethod
    async def create(
        cls,
        *,
        auth: SourceAuthProvider,
        logger: ContextualLogger,
        http_client: AirweaveHttpClient,
        config: GooclaimUploadConfig,
    ) -> GooclaimUploadSource:
        """Build a configured instance bound to one source connection."""
        instance = cls(auth=auth, logger=logger, http_client=http_client)
        instance._upload_dir = config.upload_dir
        instance._scope = config.scope
        return instance

    async def validate(self) -> None:
        """Cheap reachability check for the source-connection create flow.

        There is no external system to hit — the bucket lives on the
        platform's own filesystem and may not exist yet (first upload
        hasn't landed). We just verify the configured path is non-empty
        and resolvable, and let `generate_entities()` handle the
        "directory not yet created" case at sync time.
        """
        if not self._upload_dir:
            raise ValueError("upload_dir is required for GooclaimUploadSource")
        # Resolve once so a malformed path fails fast (does not require
        # the dir to actually exist — the upload endpoint creates it).
        _ = Path(self._upload_dir).resolve()

    async def generate_entities(
        self,
        *,
        cursor: SyncCursor | None = None,
        files: FileService | None = None,
        node_selections: list[NodeSelectionData] | None = None,
    ) -> AsyncGenerator[BaseEntity, None]:
        """Walk the upload directory and yield the connection + every uploaded file."""
        upload_path = Path(self._upload_dir)
        connection_id = upload_path.name or "default"

        # 1. The connection itself — anchors breadcrumbs and lets the UI
        #    surface the upload bucket as a browsable node.
        connection_entity = GooclaimUploadConnectionEntity(
            connection_id=connection_id,
            connection_name=f"Native Upload — {connection_id}",
            upload_dir=self._upload_dir,
            scope=self._scope,
            created_at=_dir_mtime(upload_path),
            breadcrumbs=[],
        )
        yield connection_entity

        # When the directory does not exist yet (first sync after the
        # source connection was created but before any upload landed),
        # bail out cleanly. The connection entity above still flows so
        # the UI shows the empty bucket instead of a blank tree.
        if not upload_path.is_dir():
            self.logger.warning(
                f"GooclaimUploadSource: upload_dir does not exist yet: {self._upload_dir}"
            )
            return

        breadcrumbs = [
            Breadcrumb(
                entity_id=connection_id,
                name=connection_entity.connection_name,
                entity_type="GooclaimUploadConnectionEntity",
            )
        ]

        # 2. One FileEntity per uploaded file. Sidecars are read alongside
        #    so upload metadata (who, when, description) survives.
        for entry in sorted(upload_path.iterdir()):
            if not entry.is_file():
                continue
            if entry.name.endswith(_SIDECAR_SUFFIX):
                continue

            ext = entry.suffix.lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                self.logger.info(
                    f"GooclaimUploadSource: skipping unsupported file {entry.name} (ext={ext})"
                )
                continue

            sidecar = _read_sidecar(entry)
            stat = entry.stat()

            yield GooclaimUploadFileEntity(
                upload_id=sidecar.get("upload_id", entry.stem),
                file_name=sidecar.get("file_name", entry.name),
                description=sidecar.get("description"),
                uploaded_at=_parse_iso(sidecar.get("uploaded_at"))
                or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                uploaded_by=sidecar.get("uploaded_by"),
                scope=self._scope,
                # FileEntity protocol fields — read by the downstream
                # converter/embedder pipeline.
                url=f"gooclaim-upload://{connection_id}/{entry.name}",
                size=stat.st_size,
                file_type=ext.lstrip("."),
                mime_type=mimetypes.guess_type(entry.name)[0],
                local_path=str(entry),
                breadcrumbs=breadcrumbs,
            )


# ── Helpers ──────────────────────────────────────────────────────────


def _dir_mtime(path: Path) -> datetime | None:
    """Return the directory's mtime as an aware UTC datetime, or None."""
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _read_sidecar(file_path: Path) -> dict:
    """Load the per-file metadata sidecar if present, else empty dict.

    The upload endpoint writes a `{stem}.gooclaim.json` next to every file
    with the upload event's metadata. Older files without a sidecar
    degrade gracefully — `generate_entities()` falls back to filesystem
    stats.
    """
    sidecar_path = file_path.with_suffix(file_path.suffix + _SIDECAR_SUFFIX)
    if not sidecar_path.is_file():
        return {}
    try:
        with sidecar_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp from a sidecar value, tolerant to None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
