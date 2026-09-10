"""Unit tests for ApiContext.tracking_email.

Gooclaim: in trusted-header mode every request resolves ctx.user to the
same shared system superuser, so tracking_email must prefer the real
caller's email (X-Gck-User-Email, surfaced via auth_metadata) when present
— otherwise every created_by/modified_by audit field on every action would
show the system account regardless of who really did it.
"""

from datetime import datetime, timezone
from uuid import uuid4

from airweave.api.context import ApiContext
from airweave.schemas.organization import Organization
from airweave.schemas.user import User


def _org() -> Organization:
    now = datetime.now(timezone.utc)
    return Organization(id=uuid4(), name="Test Org", created_at=now, modified_at=now)


def _user(email: str = "system@example.com") -> User:
    return User(id=uuid4(), email=email, full_name="System User")


def test_tracking_email_prefers_bridge_email_over_user_email():
    """auth_metadata['user_email'] wins over ctx.user.email when both present."""
    ctx = ApiContext(
        organization=_org(),
        user=_user(email="admin@example.com"),
        auth_metadata={"user_email": "real.user@tenant.com"},
    )
    assert ctx.tracking_email == "real.user@tenant.com"


def test_tracking_email_falls_back_to_user_email_without_bridge():
    """No auth_metadata (e.g. non-Gooclaim / OSS mode) → falls back to ctx.user.email."""
    ctx = ApiContext(organization=_org(), user=_user(email="admin@example.com"))
    assert ctx.tracking_email == "admin@example.com"


def test_tracking_email_falls_back_when_bridge_email_empty():
    """auth_metadata present but user_email is None/empty → falls back, not None."""
    ctx = ApiContext(
        organization=_org(),
        user=_user(email="admin@example.com"),
        auth_metadata={"user_email": None},
    )
    assert ctx.tracking_email == "admin@example.com"


def test_tracking_email_none_when_no_user_and_no_bridge_email():
    """No user, no bridge email (e.g. API key auth) → None."""
    ctx = ApiContext(organization=_org(), user=None, auth_metadata={"platform_admin": False})
    assert ctx.tracking_email is None
