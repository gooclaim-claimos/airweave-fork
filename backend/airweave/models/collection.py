"""Collection model."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airweave.models._base import OrganizationBase, UserMixin

if TYPE_CHECKING:
    from airweave.models.search_query import SearchQuery
    from airweave.models.source_connection import SourceConnection
    from airweave.models.vector_db_deployment_metadata import VectorDbDeploymentMetadata


class Collection(OrganizationBase, UserMixin):
    """Collection model."""

    __tablename__ = "collection"

    name: Mapped[str] = mapped_column(String, nullable=False)
    readable_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    vector_db_deployment_metadata_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("vector_db_deployment_metadata.id"), nullable=False
    )
    sync_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Gooclaim: a Public collection is readable by every org (e.g. Console-
    # curated regulations/compliance knowledge all tenants should search
    # against), never just its owning org. Write access is still gated
    # elsewhere (only a platform admin may set this) — this column alone
    # does not change who can WRITE to the collection, only who can READ it.
    #
    # Both default= (Python-side, applied immediately on construction) AND
    # server_default= (DB-side, for raw SQL / existing rows) are needed —
    # server_default alone leaves is_public as None on a freshly-constructed
    # ORM object until a real DB round-trip refreshes it. A create() call
    # that flushes but never refreshes (see CollectionService.create's
    # UnitOfWork) would otherwise hand back None here, and CollectionRecord
    # (bool, not Optional) fails validation — confirmed by
    # test_callback_service.py's oauth flow, which builds a Collection this
    # way and immediately serializes it.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Relationships
    vector_db_deployment_metadata: Mapped["VectorDbDeploymentMetadata"] = relationship(
        "VectorDbDeploymentMetadata", lazy="joined"
    )

    source_connections: Mapped[list["SourceConnection"]] = relationship(
        "SourceConnection",
        back_populates="collection",
        lazy="noload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    search_queries: Mapped[list["SearchQuery"]] = relationship(
        "SearchQuery",
        back_populates="collection",
        lazy="noload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("idx_collection_vdb_metadata_id", "vector_db_deployment_metadata_id"),)
