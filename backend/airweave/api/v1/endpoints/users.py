"""API endpoints for users.

Thin HTTP layer — delegates business logic to ``UserServiceProtocol``.
"""

from typing import List, Optional

from fastapi import Depends, HTTPException
from fastapi_auth0 import Auth0User
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api import deps
from airweave.api.auth import auth0
from airweave.api.context import ApiContext
from airweave.api.deps import Inject
from airweave.api.router import TrailingSlashRouter
from airweave.core.config import settings
from airweave.core.logging import logger
from airweave.domains.users.protocols import UserServiceProtocol
from airweave.domains.users.types import is_email_authorized
from airweave.schemas import OrganizationWithRole, User

router = TrailingSlashRouter()


@router.get("/", response_model=User)
async def read_user(
    *,
    current_user: schemas.User = Depends(deps.get_user),
    ctx: ApiContext = Depends(deps.get_context),
) -> schemas.User:
    """Get current user with all organization relationships.

    Gooclaim: surface the per-request platform-admin flag (from the trusted
    X-Gck-Platform-Admin header, set only for a verified SUPER_ADMIN) so the
    Sources UI can gate the Admin Dashboard on it. Also surface return_url
    (from X-Gck-Return-Url) so the UI's "Back" control knows where to send
    the browser without hardcoding Portal/Console URLs itself.

    ``current_user`` here is always the shared system superuser in trusted-
    header mode (no real per-tenant User row exists) — its email would
    otherwise show as a generic placeholder in the UI regardless of who is
    really logged in. Override it with the real caller's email (X-Gck-User-
    Email, resolved once by gooclaim-auth at bridge-mint time) when present,
    same source ApiContext.tracking_email already uses for audit fields.
    """
    current_user.is_platform_admin = bool((ctx.auth_metadata or {}).get("platform_admin"))
    current_user.return_url = (ctx.auth_metadata or {}).get("return_url")
    bridge_email = (ctx.auth_metadata or {}).get("user_email")
    if bridge_email:
        current_user.email = bridge_email
    return current_user


@router.get("/me/organizations", response_model=List[OrganizationWithRole])
async def read_user_organizations(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: schemas.User = Depends(deps.get_user),
    ctx: ApiContext = Depends(deps.get_context),
    user_service: UserServiceProtocol = Inject(UserServiceProtocol),
) -> List[OrganizationWithRole]:
    """Get all organizations that the current user is a member of.

    Gooclaim: in trusted-header mode (EXTERNAL_ORG_ID_PROVISIONING) each request
    is scoped to a single tenant org via X-Organization-Id, and the system
    superuser owns every auto-provisioned org. Returning all its memberships
    would leak other tenants' org names in the UI switcher, so restrict the
    list to the current context org — each tenant only sees its own.
    """
    organizations = await user_service.get_user_organizations(db, user_id=current_user.id)
    if settings.EXTERNAL_ORG_ID_PROVISIONING:
        organizations = [
            org for org in organizations if str(org.id) == str(ctx.organization.id)
        ]
    return organizations


@router.post("/create_or_update", response_model=User)
async def create_or_update_user(
    user_data: schemas.UserCreate,
    db: AsyncSession = Depends(deps.get_db),
    auth0_user: Optional[Auth0User] = Depends(auth0.get_user),
    user_service: UserServiceProtocol = Inject(UserServiceProtocol),
) -> schemas.User:
    """Create new user or sync existing user's Auth0 organizations.

    Can only create user with the same email as the authenticated user.
    """
    auth0_email = auth0_user.email if auth0_user else None
    if not auth0_email or not is_email_authorized(user_data.email, auth0_email):
        logger.error(f"User {user_data.email} is not authorized to create user {auth0_email}")
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to create this user.",
        )

    result = await user_service.create_or_update(db, user_data, auth0_user)
    return result.user
