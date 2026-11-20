"""Gooclaim (T531): the tenant confirms which product an uploaded document covers.

    PUT /uploads/{connection_id}/{upload_id}/labels   {product_uins, applies_to}

At upload the product UIN printed on the first pages is read as a suggestion
(`detected_uins`); here the tenant confirms it, changes it, or says the document applies to
every member ("general"). Only a confirmed label scopes a search (gooclaim_labels.py).

The labels go into the file's sidecar in the caller's OWN bucket (`bucket_dir`) — a search
reads them from the upload listing, so no re-sync is needed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi import Path as PathParam

from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.router import TrailingSlashRouter
from airweave.api.v1.endpoints.uploads import UploadListItem, _resolve_upload_dir
from airweave.platform.sources.gooclaim_labels import DocumentLabels, labels_of, write_labels
from airweave.platform.sources.gooclaim_upload import SIDECAR_SUFFIX

router = TrailingSlashRouter()

_UPLOAD_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


@router.put(
    "/{connection_id}/{upload_id}/labels",
    response_model=UploadListItem,
    summary="Confirm which insurance product an uploaded document covers",
)
async def set_labels(
    *,
    connection_id: str = PathParam(..., description="Source connection identifier"),
    upload_id: str = PathParam(..., description="The upload's id, as the listing returns it"),
    labels: DocumentLabels,
    ctx: ApiContext = Depends(deps.get_context),
) -> UploadListItem:
    if not _UPLOAD_ID.match(upload_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bad upload id")
    upload_dir = _resolve_upload_dir(ctx, connection_id)
    stored = next(
        (
            entry
            for entry in (upload_dir.iterdir() if upload_dir.is_dir() else [])
            if entry.is_file()
            and entry.name.startswith(f"{upload_id}__")
            and not entry.name.endswith(SIDECAR_SUFFIX)
        ),
        None,
    )
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")
    sidecar_path = stored.with_suffix(stored.suffix + SIDECAR_SUFFIX)
    sidecar = write_labels(sidecar_path, labels)
    stat = stored.stat()
    return UploadListItem.model_validate(
        {
            "upload_id": sidecar.get("upload_id", upload_id),
            "file_name": sidecar.get("file_name", stored.name.split("__", 1)[-1]),
            "file_type": stored.suffix.lower().lstrip("."),
            "size": stat.st_size,
            "uploaded_at": sidecar.get("uploaded_at")
            or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "uploaded_by": sidecar.get("uploaded_by"),
            "description": sidecar.get("description"),
            **labels_of(sidecar),
        }
    )


__all__ = ["router"]
