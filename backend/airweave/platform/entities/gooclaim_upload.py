"""Entity schemas for the Gooclaim native upload source.

A `GooclaimUploadConnectionEntity` represents one source connection (and
the upload directory backing it). Each uploaded document under that
directory yields one `GooclaimUploadFileEntity` per sync run, which
flows through the standard converter → chunker → embedder → vector-DB
pipeline that all FileEntity-typed entities use.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import computed_field

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class GooclaimUploadConnectionEntity(BaseEntity):
    """Container entity for one Gooclaim native upload source connection.

    Emitted once per sync run so the connection itself shows up in the
    browse tree alongside the files under it.
    """

    connection_id: str = AirweaveField(
        ...,
        description="Unique identifier for this upload connection",
        is_entity_id=True,
    )
    connection_name: str = AirweaveField(
        ...,
        description="Display name for the upload connection",
        is_name=True,
        embeddable=True,
    )
    upload_dir: str = AirweaveField(
        ...,
        description="Storage-relative directory holding the uploaded files",
        embeddable=False,
    )
    scope: Literal["global", "tenant"] = AirweaveField(
        default="tenant",
        description="Visibility scope — 'global' (all tenants) or 'tenant' (single org)",
        embeddable=False,
    )
    created_at: Optional[datetime] = AirweaveField(
        None,
        description="When the connection was created",
        is_created_at=True,
    )

    @computed_field(return_type=str)
    def web_url(self) -> str:
        """Stable URL identifier for the connection entity."""
        return f"gooclaim-upload://connection/{self.connection_id}"


class GooclaimUploadFileEntity(FileEntity):
    """A single uploaded file under a Gooclaim upload connection.

    Inherits the standard FileEntity fields (`url`, `size`, `file_type`,
    `mime_type`, `local_path`) which the downstream document converter
    chain (`pdf.py` / `docx.py` / `pptx.py` / `txt.py` / `html.py`) reads
    to extract text and pass it on to the embedder.
    """

    upload_id: str = AirweaveField(
        ...,
        description="Stable upload identifier (uuid set by the upload endpoint)",
        is_entity_id=True,
    )
    file_name: str = AirweaveField(
        ...,
        description="Original filename as uploaded",
        is_name=True,
        embeddable=True,
    )
    description: Optional[str] = AirweaveField(
        default=None,
        description="Optional human-written description provided at upload time",
        embeddable=True,
    )
    uploaded_at: Optional[datetime] = AirweaveField(
        None,
        description="When the file was uploaded",
        is_created_at=True,
    )
    uploaded_by: Optional[str] = AirweaveField(
        default=None,
        description="Stable identifier of the user (or service account) that uploaded the file",
        embeddable=False,
    )
    scope: Literal["global", "tenant"] = AirweaveField(
        default="tenant",
        description="Visibility scope inherited from the parent connection",
        embeddable=False,
    )
