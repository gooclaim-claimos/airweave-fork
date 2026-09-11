"""Tests for ContextResolver authentication dispatch and cache integration.

Verifies:
- Auth method dispatch (system / Auth0 / API key / none)
- Auth0 cache hit returns cached user without DB call
- Auth0 cache miss populates cache after DB call
- API key cache hit returns org_id without DB call
- No auth raises 401
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from airweave.adapters.cache.fake import FakeContextCache
from airweave.adapters.rate_limiter.fake import FakeRateLimiter
from airweave.api.context_resolver import AuthResult, ContextResolver
from airweave.core.shared_models import AuthMethod

ORG_ID = uuid4()


def _make_resolver(cache=None):
    return ContextResolver(
        cache=cache or FakeContextCache(),
        rate_limiter=FakeRateLimiter(),
        user_repo=MagicMock(),
        api_key_repo=MagicMock(),
        org_repo=MagicMock(),
    )


class TestAuthDispatch:
    """Verify _authenticate picks the right path based on inputs."""

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_auth_disabled_uses_system(self, mock_settings):
        mock_settings.AUTH_ENABLED = False
        mock_settings.FIRST_SUPERUSER = "admin@test.com"
        resolver = _make_resolver()

        with patch.object(resolver, "_authenticate_system", new_callable=AsyncMock) as mock_sys:
            mock_sys.return_value = AuthResult(method=AuthMethod.SYSTEM)
            result = await resolver._authenticate(
                db=AsyncMock(), auth0_user=None, x_api_key=None, request=MagicMock(),
            )
            mock_sys.assert_called_once()
            assert result.method == AuthMethod.SYSTEM

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_api_key_takes_priority_over_auth0_user(self, mock_settings):
        """x_api_key must win over auth0_user, not the other way round.

        AUTH_ENABLED=false's MockAuth0 (airweave/api/auth.py) unconditionally
        returns a truthy stub Auth0User — if auth0_user were checked first,
        that stub would always win and a real X-API-Key would never be
        reached. Checking x_api_key first avoids the mock entirely.
        """
        mock_settings.AUTH_ENABLED = True
        resolver = _make_resolver()

        auth0_user = MagicMock(email="user@test.com", id="auth0|123")

        with patch.object(resolver, "_authenticate_api_key", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = AuthResult(
                method=AuthMethod.API_KEY, api_key_org_id=str(ORG_ID),
            )
            result = await resolver._authenticate(
                db=AsyncMock(), auth0_user=auth0_user, x_api_key="some-key", request=MagicMock(),
            )
            mock_api.assert_called_once()
            assert result.method == AuthMethod.API_KEY

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_api_key_used_when_no_auth0_user(self, mock_settings):
        mock_settings.AUTH_ENABLED = True
        resolver = _make_resolver()

        with patch.object(resolver, "_authenticate_api_key", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = AuthResult(
                method=AuthMethod.API_KEY, api_key_org_id=str(ORG_ID),
            )
            result = await resolver._authenticate(
                db=AsyncMock(), auth0_user=None, x_api_key="key-123", request=MagicMock(),
            )
            mock_api.assert_called_once()
            assert result.method == AuthMethod.API_KEY

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_no_auth_raises_401(self, mock_settings):
        mock_settings.AUTH_ENABLED = True
        resolver = _make_resolver()

        with pytest.raises(HTTPException) as exc:
            await resolver._authenticate(
                db=AsyncMock(), auth0_user=None, x_api_key=None, request=MagicMock(),
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_api_key_checked_even_when_auth_disabled(self, mock_settings):
        """A presented X-API-Key is validated for real regardless of AUTH_ENABLED.

        Previously AUTH_ENABLED=false short-circuited straight to SYSTEM
        auth before x_api_key was even looked at, silently trusting any
        caller (real key, wrong key, or none at all).
        """
        mock_settings.AUTH_ENABLED = False
        resolver = _make_resolver()

        with patch.object(resolver, "_authenticate_api_key", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = AuthResult(
                method=AuthMethod.API_KEY, api_key_org_id=str(ORG_ID),
            )
            result = await resolver._authenticate(
                db=AsyncMock(), auth0_user=None, x_api_key="mcp-key", request=MagicMock(),
            )
            mock_api.assert_called_once()
            assert result.method == AuthMethod.API_KEY

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_api_key_used_over_mock_auth0_stub_when_auth_disabled(self, mock_settings):
        """The exact real-world scenario that broke live on the EC2 box.

        AUTH_ENABLED=false's MockAuth0 stub is present (FastAPI always
        calls the auth0_user dependency) alongside a real X-API-Key from a
        trusted caller — the key must win, or the caller is silently
        routed into the stub's dead-end auth0 lookup instead of ever
        having its real credential checked. A first fix put auth0_user
        first "to preserve precedence" and every API-key request 401'd
        this exact way.
        """
        mock_settings.AUTH_ENABLED = False
        resolver = _make_resolver()

        mock_auth0_stub = MagicMock(email="admin@example.com", id="mock-user-id")

        with patch.object(resolver, "_authenticate_api_key", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = AuthResult(
                method=AuthMethod.API_KEY, api_key_org_id=str(ORG_ID),
            )
            result = await resolver._authenticate(
                db=AsyncMock(),
                auth0_user=mock_auth0_stub,
                x_api_key="mcp-key",
                request=MagicMock(),
            )
            mock_api.assert_called_once()
            assert result.method == AuthMethod.API_KEY

    @pytest.mark.asyncio
    @patch("airweave.api.context_resolver.settings")
    async def test_no_api_key_still_falls_back_to_system_when_auth_disabled(self, mock_settings):
        """No credential presented at all — unchanged nginx-trusted-header path."""
        mock_settings.AUTH_ENABLED = False
        mock_settings.FIRST_SUPERUSER = "admin@test.com"
        resolver = _make_resolver()

        with patch.object(resolver, "_authenticate_system", new_callable=AsyncMock) as mock_sys:
            mock_sys.return_value = AuthResult(method=AuthMethod.SYSTEM)
            result = await resolver._authenticate(
                db=AsyncMock(), auth0_user=None, x_api_key=None, request=MagicMock(),
            )
            mock_sys.assert_called_once()
            assert result.method == AuthMethod.SYSTEM


class TestAuth0CacheIntegration:
    """Verify Auth0 auth uses the cache correctly."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        """When user is in cache, DB should not be called."""
        from airweave import schemas

        cache = FakeContextCache()
        user = MagicMock(spec=schemas.User)
        user.email = "cached@test.com"
        cache._users["cached@test.com"] = user

        resolver = _make_resolver(cache=cache)
        auth0_user = MagicMock(email="cached@test.com", id="auth0|456")

        result = await resolver._authenticate_auth0(AsyncMock(), auth0_user)

        assert result.user == user
        assert result.method == AuthMethod.AUTH0
        assert result.metadata["auth0_id"] == "auth0|456"

    @pytest.mark.asyncio
    async def test_cache_miss_populates_cache(self):
        """When user is NOT in cache, should fetch from DB and cache the result."""
        from airweave import schemas

        cache = FakeContextCache()
        resolver = _make_resolver(cache=cache)
        auth0_user = MagicMock(email="new@test.com", id="auth0|789")

        mock_user = MagicMock(spec=schemas.User)
        mock_user.email = "new@test.com"

        with patch.object(resolver, "_fetch_auth0_user", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_user
            result = await resolver._authenticate_auth0(AsyncMock(), auth0_user)

        assert result.user == mock_user
        assert "new@test.com" in cache._users

    @pytest.mark.asyncio
    async def test_cache_miss_db_returns_none(self):
        """When user is not in cache AND not in DB, result.user should be None."""
        cache = FakeContextCache()
        resolver = _make_resolver(cache=cache)
        auth0_user = MagicMock(email="ghost@test.com", id="auth0|000")

        with patch.object(resolver, "_fetch_auth0_user", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            result = await resolver._authenticate_auth0(AsyncMock(), auth0_user)

        assert result.user is None
        assert "ghost@test.com" not in cache._users


class TestApiKeyCacheIntegration:
    """Verify API key auth uses the cache correctly."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_org_id(self):
        cache = FakeContextCache()
        cache._api_keys["my-secret-key"] = ORG_ID

        resolver = _make_resolver(cache=cache)
        result = await resolver._authenticate_api_key(
            db=AsyncMock(), api_key="my-secret-key", request=MagicMock(),
        )

        assert result.method == AuthMethod.API_KEY
        assert result.api_key_org_id == str(ORG_ID)
        assert result.metadata["api_key_id"] == "cached"
