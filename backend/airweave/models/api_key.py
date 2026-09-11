"""Api key model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from airweave.models._base import OrganizationBase, UserMixin

if TYPE_CHECKING:
    pass


class APIKey(OrganizationBase, UserMixin):
    """SQLAlchemy model for the APIKey table."""

    __tablename__ = "api_key"

    encrypted_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expiration_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    # Gooclaim: a Master key may act on behalf of ANY organization — see
    # migration 0002 for the full rationale. Never settable via any API
    # endpoint; only ever set directly in the database.
    is_master: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
