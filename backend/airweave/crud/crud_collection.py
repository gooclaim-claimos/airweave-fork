# airweave/crud/crud_collection.py

"""CRUD operations for collections."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airweave.core.context import BaseContext
from airweave.core.exceptions import NotFoundException, PermissionException
from airweave.crud._base_organization import CRUDBaseOrganization
from airweave.models.collection import Collection
from airweave.schemas.collection import CollectionCreate, CollectionUpdate


class CRUDCollection(CRUDBaseOrganization[Collection, CollectionCreate, CollectionUpdate]):
    """CRUD operations for collections.

    Gooclaim: a Public collection (``is_public=True``) is readable by every
    organization, not just its owner — used for shared/regulatory knowledge
    curated via Console. The base class's org-scoped ``get``/``get_multi``
    hard-filter to ``ctx.organization.id`` at the SQL level, so a Public
    collection belonging to another org would never even be fetched; every
    read path below is overridden to OR in ``is_public``. Write paths
    (create/update/remove, inherited unchanged) still require owning the
    collection — read visibility here does not grant write access, and
    setting ``is_public`` itself is gated at the API layer to platform
    admins only (see endpoints/collections.py).
    """

    async def get(self, db: AsyncSession, id: UUID, ctx: BaseContext) -> Optional[Collection]:
        """Get a collection by ID — own-org OR public, from any org."""
        query = select(Collection).where(
            Collection.id == id,
            or_(Collection.organization_id == ctx.organization.id, Collection.is_public.is_(True)),
        )
        result = await db.execute(query)
        collection = result.unique().scalar_one_or_none()
        if collection is None:
            raise NotFoundException(f"{self.model.__name__} not found")

        if not collection.is_public:
            await self._validate_organization_access(ctx, collection.organization_id)

        return collection

    async def get_by_readable_id(
        self, db: AsyncSession, readable_id: str, ctx: BaseContext
    ) -> Optional[Collection]:
        """Get a collection by its readable ID — own-org OR public, from any org."""
        result = await db.execute(select(Collection).where(Collection.readable_id == readable_id))
        collection = result.scalar_one_or_none()

        if not collection:
            raise NotFoundException(f"Collection '{readable_id}' not found.")

        if collection.is_public:
            return collection

        try:
            await self._validate_organization_access(ctx, collection.organization_id)
        except PermissionException:
            raise NotFoundException(f"Collection '{readable_id}' not found.")

        return collection

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        ctx: BaseContext,
        search_query: Optional[str] = None,
    ) -> List[Collection]:
        """Get multiple collections with pagination and optional search.

        Includes this org's own collections plus every Public collection
        (from any org).
        """
        query = select(Collection).where(
            or_(Collection.organization_id == ctx.organization.id, Collection.is_public.is_(True))
        )

        if search_query:
            search_pattern = f"%{search_query.lower()}%"
            query = query.where(
                (func.lower(Collection.name).like(search_pattern))
                | (func.lower(Collection.readable_id).like(search_pattern))
            )

        query = query.order_by(Collection.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def count(
        self, db: AsyncSession, ctx: BaseContext, search_query: Optional[str] = None
    ) -> int:
        """Get total count of collections visible to the org (own + Public)."""
        query = (
            select(func.count())
            .select_from(Collection)
            .where(
                or_(
                    Collection.organization_id == ctx.organization.id,
                    Collection.is_public.is_(True),
                )
            )
        )

        if search_query:
            search_pattern = f"%{search_query.lower()}%"
            query = query.where(
                (func.lower(Collection.name).like(search_pattern))
                | (func.lower(Collection.readable_id).like(search_pattern))
            )

        result = await db.execute(query)
        return result.scalar_one()

    async def get_public_ids(self, db: AsyncSession) -> List[UUID]:
        """IDs of every Public collection, across all organizations.

        Used at search time to fold shared/regulatory knowledge into a
        tenant's own search alongside their private collection — see
        VespaVectorDB._build_collection_clause. No org scoping: Public
        means readable by every org by definition.
        """
        result = await db.execute(select(Collection.id).where(Collection.is_public.is_(True)))
        return list(result.scalars().all())


collection = CRUDCollection(Collection)
