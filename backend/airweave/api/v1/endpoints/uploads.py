"""Native upload endpoint for the Gooclaim Data Sources surface.

Receives multipart file uploads from the Console / Data Sources UI and
writes them into a per-connection directory under the platform's
filesystem storage backend. A sidecar JSON next to each file carries the
upload event's metadata (upload_id, uploaded_at, uploaded_by, description)
so the source connector (`GooclaimUploadSource.generate_entities()`) can
reconstruct it on subsequent sync runs.

Phase 2 scope (this file):
  * POST /uploads/{connection_id}  — single-file multipart upload
  * GET  /uploads/{connection_id}  — list uploaded files for diagnostics

Phase 3 will wire this endpoint into the frontend's source connection
creation flow and add auto-triggered syncs on upload completion.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from fastapi import Path as PathParam
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.deps import Inject
from airweave.api.router import TrailingSlashRouter
from airweave.core.config import settings
from airweave.domains.collections.protocols import CollectionServiceProtocol
from airweave.domains.source_connections.protocols import SourceConnectionServiceProtocol
from airweave.schemas.source_connection import DirectAuthentication, SourceConnectionCreate

# Match the source connector's supported file set so what the endpoint
# accepts and what the indexer can read stay in sync.
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".pptx", ".txt", ".md", ".html", ".htm", ".csv", ".json"}
)

# Same sidecar suffix the source connector reads on sync.
_SIDECAR_SUFFIX: str = ".gooclaim.json"

# Per-upload hard cap. Larger files would also need streaming-to-disk
# instead of the read-into-memory pattern below, so we enforce the
# limit at request-edge for now. Tune as the demo dataset grows.
_MAX_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MiB

# Connection IDs are URL path segments — restrict to a safe alphabet so
# a crafted `..` or absolute path can't escape STORAGE_PATH.
_CONNECTION_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


router = TrailingSlashRouter()


# ── Response models ─────────────────────────────────────────────────────


class UploadFileResponse(BaseModel):
    """Returned after a successful upload."""

    upload_id: str = Field(..., description="UUID assigned to this upload")
    connection_id: str = Field(..., description="Source connection bucket the file landed in")
    file_name: str = Field(..., description="Original filename as uploaded")
    file_type: str = Field(..., description="Lower-cased file extension without the dot")
    size: int = Field(..., description="Bytes written to disk")
    uploaded_at: datetime = Field(..., description="When the upload completed")
    uploaded_by: Optional[str] = Field(None, description="Stable user/service identifier")
    description: Optional[str] = Field(None, description="Optional human description")
    stored_path: str = Field(..., description="Server-side path the file was written to")


class UploadListItem(BaseModel):
    """One item in a connection's upload listing."""

    upload_id: str
    file_name: str
    file_type: str
    size: int
    uploaded_at: datetime
    uploaded_by: Optional[str] = None
    description: Optional[str] = None


class UploadListResponse(BaseModel):
    """Listing of uploads under a connection."""

    connection_id: str
    upload_dir: str
    total: int
    items: list[UploadListItem]


class CommitResponse(BaseModel):
    """Returned after committing a bucket to a collection + triggering sync."""

    connection_id: str = Field(..., description="The upload bucket identifier")
    collection_id: str = Field(..., description="Collection UUID")
    collection_readable_id: str = Field(..., description="Collection's readable_id (URL slug)")
    source_connection_id: str = Field(..., description="SourceConnection UUID")
    sync_triggered: bool = Field(
        ...,
        description=("True if sync was triggered (at create time, or on subsequent re-commits)."),
    )
    files_in_bucket: int = Field(..., description="Number of uploaded files visible at commit time")


# ── Helpers ─────────────────────────────────────────────────────────────


def _resolve_upload_dir(connection_id: str) -> Path:
    """Resolve the on-disk directory for a connection's uploads.

    Raises HTTPException(400) if the connection id is unsafe.
    """
    if not _CONNECTION_ID_PATTERN.match(connection_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "connection_id must match [a-zA-Z0-9_-]{1,128}; "
                "path separators and dots are not allowed."
            ),
        )
    return Path(settings.STORAGE_PATH) / "uploads" / connection_id


def _safe_basename(filename: str) -> str:
    """Strip path components and reject unsafe characters."""
    base = os.path.basename(filename or "")
    if not base or base in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename is required and cannot be `.` or `..`",
        )
    # Defence-in-depth — Path.name already strips separators, but explicit
    # blocking surfaces the failure as a 400 instead of a stored slash.
    if any(c in base for c in ("/", "\\", "\x00")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename contains an unsupported character.",
        )
    return base


def _ctx_user_identifier(ctx: ApiContext) -> Optional[str]:
    """Best-effort stable identifier for the uploader from the auth context.

    Uses the authenticated user id when present, otherwise the organization
    id. Returns None in dev where AUTH_ENABLED=false leaves the context bare.
    """
    user = getattr(ctx, "user", None)
    if user is not None:
        uid = getattr(user, "id", None)
        if uid:
            return str(uid)
    org = getattr(ctx, "organization", None)
    if org is not None:
        oid = getattr(org, "id", None)
        if oid:
            return f"org:{oid}"
    return None


async def _find_or_create_collection(
    db: AsyncSession,
    ctx: ApiContext,
    cc_service: CollectionServiceProtocol,
    readable_id: str,
    name: str,
) -> "schemas.Collection":
    """Idempotently locate (or auto-create) a Collection by readable_id."""
    try:
        return await cc_service.get(db, readable_id=readable_id, ctx=ctx)
    except Exception:  # noqa: BLE001 — service raises CollectionNotFoundError on miss
        pass
    try:
        return await cc_service.create(
            db,
            collection_in=schemas.CollectionCreate(
                name=name,
                readable_id=readable_id,
                sync_config=None,
            ),
            ctx=ctx,
        )
    except Exception as e:  # noqa: BLE001 — surface upstream validation as 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create Collection: {e}",
        ) from e


async def _find_existing_upload_sc(
    db: AsyncSession,
    ctx: ApiContext,
    sc_service: SourceConnectionServiceProtocol,
    collection_readable_id: str,
):
    """Return the gooclaim_upload SourceConnection in a collection, or None.

    Untyped return on purpose: the service protocol returns the schemas
    SourceConnection, which is a different class than the models one;
    pinning a forward ref here would make pyright disagree with the
    runtime types service implementations actually hand back.
    """
    existing = await sc_service.list(
        db,
        ctx=ctx,
        readable_collection_id=collection_readable_id,
        skip=0,
        limit=100,
    )
    sc_id = next(
        (sc.id for sc in existing if sc.short_name == "gooclaim_upload"),
        None,
    )
    if sc_id is None:
        return None
    return await sc_service.get(db, id=sc_id, ctx=ctx)


def _count_bucket_files(upload_dir: Path) -> int:
    """Count uploaded files visible in a bucket (sidecars and unsupported skipped)."""
    if not upload_dir.is_dir():
        return 0
    count = 0
    for entry in upload_dir.iterdir():
        if not entry.is_file() or entry.name.endswith(_SIDECAR_SUFFIX):
            continue
        if entry.suffix.lower() in _SUPPORTED_EXTENSIONS:
            count += 1
    return count


# ── Routes ──────────────────────────────────────────────────────────────


@router.post(
    "/{connection_id}",
    response_model=UploadFileResponse,
    summary="Upload a file to a Gooclaim native-upload source connection",
)
async def upload_file(
    *,
    connection_id: str = PathParam(
        ...,
        description="Source connection identifier this upload belongs to",
        examples=["pilot-tpa-mediassist"],
    ),
    file: UploadFile = File(..., description="The file to upload"),
    description: Optional[str] = Form(
        None,
        description="Optional human description preserved in the sidecar",
    ),
    ctx: ApiContext = Depends(deps.get_context),
) -> UploadFileResponse:
    """Store an uploaded file and emit a sidecar with upload metadata."""
    upload_dir = _resolve_upload_dir(connection_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = _safe_basename(file.filename or "")
    ext = Path(original_name).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File extension '{ext or '(none)'}' is not in the supported set: "
                f"{sorted(_SUPPORTED_EXTENSIONS)}"
            ),
        )

    body = await file.read()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(body) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File exceeds {_MAX_FILE_BYTES // (1024 * 1024)} MiB limit "
                f"(got {len(body)} bytes)."
            ),
        )

    upload_id = str(uuid.uuid4())
    stored_name = f"{upload_id}__{original_name}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(body)

    uploaded_at = datetime.now(tz=timezone.utc)
    uploaded_by = _ctx_user_identifier(ctx)

    sidecar = {
        "upload_id": upload_id,
        "file_name": original_name,
        "file_type": ext.lstrip("."),
        "size": len(body),
        "uploaded_at": uploaded_at.isoformat(),
        "uploaded_by": uploaded_by,
        "description": description,
    }
    sidecar_path = stored_path.with_suffix(stored_path.suffix + _SIDECAR_SUFFIX)
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")

    return UploadFileResponse(
        upload_id=upload_id,
        connection_id=connection_id,
        file_name=original_name,
        file_type=ext.lstrip("."),
        size=len(body),
        uploaded_at=uploaded_at,
        uploaded_by=uploaded_by,
        description=description,
        stored_path=str(stored_path),
    )


@router.get(
    "/{connection_id}",
    response_model=UploadListResponse,
    summary="List files uploaded to a Gooclaim native-upload source connection",
)
async def list_uploads(
    *,
    connection_id: str = PathParam(..., description="Source connection identifier"),
    ctx: ApiContext = Depends(deps.get_context),  # noqa: ARG001 — reserved for RBAC
) -> UploadListResponse:
    """Return all uploads under a connection (read from sidecars + filesystem stats)."""
    upload_dir = _resolve_upload_dir(connection_id)

    items: list[UploadListItem] = []
    if upload_dir.is_dir():
        for entry in sorted(upload_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.name.endswith(_SIDECAR_SUFFIX):
                continue
            ext = entry.suffix.lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                continue

            sidecar_path = entry.with_suffix(entry.suffix + _SIDECAR_SUFFIX)
            sidecar: dict = {}
            if sidecar_path.is_file():
                try:
                    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    sidecar = {}

            stat = entry.stat()
            try:
                uploaded_at = datetime.fromisoformat(sidecar.get("uploaded_at", ""))
            except ValueError:
                uploaded_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

            items.append(
                UploadListItem(
                    upload_id=sidecar.get("upload_id", entry.stem),
                    file_name=sidecar.get("file_name", entry.name),
                    file_type=ext.lstrip("."),
                    size=stat.st_size,
                    uploaded_at=uploaded_at,
                    uploaded_by=sidecar.get("uploaded_by"),
                    description=sidecar.get("description"),
                )
            )

    return UploadListResponse(
        connection_id=connection_id,
        upload_dir=str(upload_dir),
        total=len(items),
        items=items,
    )


@router.post(
    "/{connection_id}/commit",
    response_model=CommitResponse,
    summary="Commit a Native Upload bucket to a Collection and trigger sync",
    description=(
        "Idempotently ensures the named Collection exists, that a "
        "gooclaim_upload SourceConnection is bound to this upload bucket, "
        "and triggers a sync run so the uploaded files flow through the "
        "converter → embedder → Vespa pipeline. Subsequent calls re-use the "
        "existing Collection + SourceConnection and just re-run the sync."
    ),
)
async def commit_uploads(
    *,
    connection_id: str = PathParam(
        ...,
        description="Source connection identifier that scopes the upload bucket",
        examples=["pilot-tpa-mediassist"],
    ),
    collection_name: str = Form(
        ...,
        min_length=4,
        max_length=64,
        description="Human-readable Collection name (4–64 chars)",
    ),
    description: Optional[str] = Form(
        None,
        max_length=255,
        description="Optional description stored on the SourceConnection",
    ),
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
    cc_service: CollectionServiceProtocol = Inject(CollectionServiceProtocol),
    sc_service: SourceConnectionServiceProtocol = Inject(SourceConnectionServiceProtocol),
) -> CommitResponse:
    """Bind an upload bucket to a Collection + SourceConnection and run sync."""
    upload_dir = _resolve_upload_dir(connection_id)

    # 1) Find or create the Collection — connection_id IS the readable_id
    #    so the collection ↔ bucket mapping stays predictable.
    collection = await _find_or_create_collection(
        db, ctx, cc_service, readable_id=connection_id, name=collection_name
    )

    # 2) Find or create the SourceConnection for this bucket.
    sc_for_bucket = await _find_existing_upload_sc(
        db, ctx, sc_service, collection_readable_id=collection.readable_id
    )

    sync_triggered = False
    if sc_for_bucket is None:
        # Trim to schema's 4..42 char range for the SC display name.
        sc_name = f"Native Upload — {collection_name}"[:42]
        if len(sc_name) < 4:
            sc_name = "Native Upload"

        sc_for_bucket = await sc_service.create(
            db,
            obj_in=SourceConnectionCreate(
                name=sc_name,
                short_name="gooclaim_upload",
                readable_collection_id=collection.readable_id,
                description=description,
                config={
                    "upload_dir": str(upload_dir),
                    "scope": "tenant",
                },
                schedule=None,
                sync_immediately=True,
                authentication=DirectAuthentication(
                    credentials={"upload_tenant": "gooclaim"},
                ),
                redirect_url=None,
            ),
            ctx=ctx,
        )
        sync_triggered = True
    else:
        # SC already exists — kick a fresh sync run so any newly-uploaded
        # files since the last commit get indexed.
        sc_id: uuid.UUID = sc_for_bucket.id  # type: ignore[assignment]
        try:
            await sc_service.run(db, id=sc_id, ctx=ctx)
            sync_triggered = True
        except Exception as e:  # noqa: BLE001 — best effort on re-sync
            ctx.logger.warning(
                f"Could not re-trigger sync on existing source connection {sc_id}: {e}"
            )

    # 3) Count files currently on disk for the response.
    files_in_bucket = _count_bucket_files(upload_dir)

    return CommitResponse(
        connection_id=connection_id,
        collection_id=str(collection.id),
        collection_readable_id=collection.readable_id,
        source_connection_id=str(sc_for_bucket.id),
        sync_triggered=sync_triggered,
        files_in_bucket=files_in_bucket,
    )
