"""Root conftest for pytest configuration and shared fixtures.

This conftest is loaded before both testpaths (tests/ and airweave/domains/),
making its fixtures available to centralized tests AND colocated domain tests.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from airweave.adapters.metrics import (
        FakeAgenticSearchMetrics,
        FakeDbPoolMetrics,
        FakeHttpMetrics,
    )
    from airweave.core.fakes.metrics_service import FakeMetricsService
    from airweave.core.health.fakes import FakeHealthService

# Register pytest-asyncio plugin at the root level
pytest_plugins = ("pytest_asyncio",)

# ---------------------------------------------------------------------------
# Environment variables — must be set before any airweave module import
# Uses setdefault so real env vars (CI, e2e) are never overridden.
# ---------------------------------------------------------------------------
os.environ.setdefault("FIRST_SUPERUSER", "test@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "testpassword123")
os.environ.setdefault("ENCRYPTION_KEY", "SpgLrrEEgJ/7QdhSMSvagL1juEY5eoyCG0tZN7OSQV0=")
os.environ.setdefault("STATE_SECRET", "test-state-secret-key-minimum-32-characters-long")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault(
    "SVIX_JWT_SECRET",
    "test-svix-jwt-secret-minimum-32-characters-long",
)
os.environ.setdefault("DENSE_EMBEDDER", "openai_text_embedding_3_small")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1536")
os.environ.setdefault("SPARSE_EMBEDDER", "fastembed_bm25")


# ---------------------------------------------------------------------------
# Shared fake fixtures — individual protocol fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_pubsub():
    """Fake PubSub that records published messages in memory."""
    from airweave.adapters.pubsub.fake import FakePubSub  # noqa: PLC0415

    return FakePubSub()


@pytest.fixture
def fake_event_bus():
    """Fake EventBus that records published events."""
    from airweave.adapters.event_bus.fake import FakeEventBus  # noqa: PLC0415

    return FakeEventBus()


@pytest.fixture
def fake_webhook_publisher():
    """Fake WebhookPublisher that records published events."""
    from airweave.adapters.webhooks.fake import FakeWebhookPublisher  # noqa: PLC0415

    return FakeWebhookPublisher()


@pytest.fixture
def fake_webhook_admin():
    """Fake WebhookAdmin that records all operations."""
    from airweave.adapters.webhooks.fake import FakeWebhookAdmin  # noqa: PLC0415

    return FakeWebhookAdmin()


@pytest.fixture
def fake_endpoint_verifier():
    """Fake EndpointVerifier that records verification calls."""
    from airweave.adapters.webhooks.fake import FakeEndpointVerifier  # noqa: PLC0415

    return FakeEndpointVerifier()


@pytest.fixture
def fake_webhook_service():
    """Fake WebhookService with in-memory state for assertions."""
    from airweave.adapters.webhooks.fake import FakeWebhookService  # noqa: PLC0415

    return FakeWebhookService()


@pytest.fixture
def fake_circuit_breaker():
    """Fake CircuitBreaker that tracks provider state."""
    from airweave.adapters.circuit_breaker.fake import FakeCircuitBreaker  # noqa: PLC0415

    return FakeCircuitBreaker()


@pytest.fixture
def fake_ocr_provider():
    """Fake OcrProvider that returns canned markdown."""
    from airweave.domains.ocr.fakes.provider import FakeOcrProvider  # noqa: PLC0415

    return FakeOcrProvider()


@pytest.fixture
def fake_http_metrics() -> FakeHttpMetrics:
    """Fake HttpMetrics that records calls in memory."""
    from airweave.adapters.metrics import FakeHttpMetrics  # noqa: PLC0415

    return FakeHttpMetrics()


@pytest.fixture
def fake_agentic_search_metrics() -> FakeAgenticSearchMetrics:
    """Fake AgenticSearchMetrics that records calls in memory."""
    from airweave.adapters.metrics import FakeAgenticSearchMetrics  # noqa: PLC0415

    return FakeAgenticSearchMetrics()


@pytest.fixture
def fake_db_pool_metrics() -> FakeDbPoolMetrics:
    """Fake DbPoolMetrics that records the latest update in memory."""
    from airweave.adapters.metrics import FakeDbPoolMetrics  # noqa: PLC0415

    return FakeDbPoolMetrics()


@pytest.fixture
def fake_source_service():
    """Fake SourceService that returns canned source schemas."""
    from airweave.domains.sources.fakes.service import FakeSourceService  # noqa: PLC0415

    return FakeSourceService()


@pytest.fixture
def fake_source_registry():
    """Fake SourceRegistry for testing registry consumers."""
    from airweave.domains.sources.fakes.registry import FakeSourceRegistry  # noqa: PLC0415

    return FakeSourceRegistry()


@pytest.fixture
def fake_auth_provider_registry():
    """Fake AuthProviderRegistry for testing registry consumers."""
    from airweave.domains.auth_provider.fake import FakeAuthProviderRegistry  # noqa: PLC0415

    return FakeAuthProviderRegistry()


@pytest.fixture
def fake_auth_provider_service():
    """Fake AuthProviderService for testing endpoint DI."""
    from airweave.domains.auth_provider.fake import FakeAuthProviderService  # noqa: PLC0415

    return FakeAuthProviderService()


@pytest.fixture
def fake_entity_definition_registry():
    """Fake EntityDefinitionRegistry for testing registry consumers."""
    from airweave.domains.entities.fakes.registry import (  # noqa: PLC0415
        FakeEntityDefinitionRegistry,  # noqa: PLC0415
    )

    return FakeEntityDefinitionRegistry()


@pytest.fixture
def fake_metrics_service(
    fake_http_metrics,
    fake_agentic_search_metrics,
    fake_db_pool_metrics,
) -> FakeMetricsService:
    """FakeMetricsService wrapping individual metric fakes."""
    from airweave.core.fakes.metrics_service import FakeMetricsService  # noqa: PLC0415

    return FakeMetricsService(
        http=fake_http_metrics,
        agentic_search=fake_agentic_search_metrics,
        db_pool=fake_db_pool_metrics,
    )


# ---------------------------------------------------------------------------
# Test container — fully faked Container for injection
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_health_service() -> FakeHealthService:
    """Fake HealthService with canned responses."""
    from airweave.core.health.fakes import FakeHealthService  # noqa: PLC0415

    return FakeHealthService()


@pytest.fixture
def fake_source_connection_service(fake_sync_service):
    """Fake SourceConnectionService."""
    from airweave.domains.source_connections.fakes.service import (  # noqa: PLC0415
        FakeSourceConnectionService,  # noqa: PLC0415
    )

    return FakeSourceConnectionService(sync_service=fake_sync_service)


@pytest.fixture
def fake_source_lifecycle_service():
    """Fake SourceLifecycleService for testing lifecycle consumers."""
    from airweave.domains.sources.fakes.lifecycle import FakeSourceLifecycleService  # noqa: PLC0415

    return FakeSourceLifecycleService()


@pytest.fixture
def fake_sc_repo():
    """Fake SourceConnectionRepository."""
    from airweave.domains.source_connections.fakes.repository import (  # noqa: PLC0415
        FakeSourceConnectionRepository,  # noqa: PLC0415
    )

    return FakeSourceConnectionRepository()


@pytest.fixture
def fake_conn_repo():
    """Fake ConnectionRepository."""
    from airweave.domains.connections.fakes.repository import (  # noqa: PLC0415
        FakeConnectionRepository,  # noqa: PLC0415
    )

    return FakeConnectionRepository()


@pytest.fixture
def fake_collection_repo():
    """Fake CollectionRepository."""
    from airweave.domains.collections.fakes.repository import (  # noqa: PLC0415
        FakeCollectionRepository,  # noqa: PLC0415
    )

    return FakeCollectionRepository()


@pytest.fixture
def fake_cred_repo():
    """Fake IntegrationCredentialRepository."""
    from airweave.domains.credentials.fakes.repository import (  # noqa: PLC0415
        FakeIntegrationCredentialRepository,  # noqa: PLC0415
    )

    return FakeIntegrationCredentialRepository()


@pytest.fixture
def fake_credential_service():
    """Fake IntegrationCredentialService."""
    from airweave.domains.credentials.fakes.service import (  # noqa: PLC0415
        FakeIntegrationCredentialService,  # noqa: PLC0415
    )

    return FakeIntegrationCredentialService()


@pytest.fixture
def fake_user_org_repo():
    """Fake UserOrganizationRepository."""
    from airweave.domains.organizations.fakes.repository import (  # noqa: PLC0415
        FakeUserOrganizationRepository,  # noqa: PLC0415
    )

    return FakeUserOrganizationRepository()


@pytest.fixture
def fake_oauth2_service():
    """Fake OAuth2Service."""
    from airweave.domains.oauth.fakes.oauth2_service import FakeOAuth2Service  # noqa: PLC0415

    return FakeOAuth2Service()


@pytest.fixture
def fake_oauth1_service():
    """Real OAuth1Service (no injected deps, safe for unit tests)."""
    from airweave.domains.oauth.oauth1_service import OAuth1Service  # noqa: PLC0415

    return OAuth1Service()


@pytest.fixture
def fake_redirect_session_repo():
    """Fake OAuthRedirectSessionRepository."""
    from airweave.domains.oauth.fakes.repository import (  # noqa: PLC0415
        FakeOAuthRedirectSessionRepository,  # noqa: PLC0415
    )

    return FakeOAuthRedirectSessionRepository()


@pytest.fixture
def fake_response_builder():
    """Fake ResponseBuilder."""
    from airweave.domains.source_connections.fakes.response import (  # noqa: PLC0415
        FakeResponseBuilder,  # noqa: PLC0415
    )

    return FakeResponseBuilder()


@pytest.fixture
def fake_temporal_workflow_service():
    """Fake TemporalWorkflowService."""
    from airweave.domains.temporal.fakes.service import FakeTemporalWorkflowService  # noqa: PLC0415

    return FakeTemporalWorkflowService()


@pytest.fixture
def fake_temporal_schedule_service():
    """Fake TemporalScheduleService."""
    from airweave.domains.temporal.fakes.schedule_service import (  # noqa: PLC0415
        FakeTemporalScheduleService,  # noqa: PLC0415
    )

    return FakeTemporalScheduleService()


@pytest.fixture
def fake_sync_repo():
    """Fake SyncRepository."""
    from airweave.domains.syncs.fakes.repository import FakeSyncRepository  # noqa: PLC0415

    return FakeSyncRepository()


@pytest.fixture
def fake_sync_cursor_repo():
    """Fake SyncCursorRepository."""
    from airweave.domains.syncs.fakes.cursor_repository import (  # noqa: PLC0415
        FakeSyncCursorRepository,  # noqa: PLC0415
    )

    return FakeSyncCursorRepository()


@pytest.fixture
def fake_sync_cursor_service():
    """SyncCursorService instance (no constructor deps)."""
    from airweave.domains.syncs.cursors.service import SyncCursorService  # noqa: PLC0415

    return SyncCursorService()


@pytest.fixture
def fake_sync_job_repo():
    """Fake SyncJobRepository."""
    from airweave.domains.syncs.jobs.fakes.repository import FakeSyncJobRepository  # noqa: PLC0415

    return FakeSyncJobRepository()


@pytest.fixture
def fake_billing_service():
    """Fake BillingService."""
    from airweave.adapters.payment.fake import FakePaymentGateway  # noqa: PLC0415
    from airweave.domains.billing.fakes.operations import FakeBillingOperations  # noqa: PLC0415
    from airweave.domains.billing.fakes.repository import (  # noqa: PLC0415
        FakeBillingPeriodRepository,
        FakeOrganizationBillingRepository,
    )
    from airweave.domains.billing.service import BillingService  # noqa: PLC0415
    from airweave.domains.organizations.fakes.repository import (  # noqa: PLC0415
        FakeOrganizationRepository,  # noqa: PLC0415
    )

    return BillingService(
        payment_gateway=FakePaymentGateway(),
        billing_repo=FakeOrganizationBillingRepository(),
        period_repo=FakeBillingPeriodRepository(),
        billing_ops=FakeBillingOperations(),
        org_repo=FakeOrganizationRepository(),
    )


@pytest.fixture
def fake_sync_record_service(fake_sync_service):
    """Legacy fixture — returns the unified FakeSyncService for backward compatibility."""
    return fake_sync_service


@pytest.fixture
def fake_sync_job_service():
    """Fake SyncJobService."""
    from airweave.domains.syncs.jobs.fakes.service import FakeSyncJobService  # noqa: PLC0415

    return FakeSyncJobService()


@pytest.fixture
def fake_sync_job_state_machine() -> MagicMock:
    """Fake SyncJobStateMachine (AsyncMock)."""
    sm = MagicMock()
    sm.transition = AsyncMock()
    return sm


@pytest.fixture
def fake_sync_service():
    """Fake SyncService."""
    from airweave.domains.syncs.fakes.service import FakeSyncService  # noqa: PLC0415

    return FakeSyncService()


@pytest.fixture
def fake_sync_lifecycle(fake_sync_service):
    """Legacy fixture — returns the unified FakeSyncService for backward compatibility."""
    return fake_sync_service


@pytest.fixture
def fake_sync_state_machine():
    """Fake SyncStateMachine."""
    from airweave.domains.syncs.fakes.state_machine import FakeSyncStateMachine  # noqa: PLC0415

    return FakeSyncStateMachine()


@pytest.fixture
def fake_sync_factory():
    """Fake SyncFactory."""
    from airweave.domains.sync_pipeline.fakes.factory import FakeSyncFactory  # noqa: PLC0415

    return FakeSyncFactory()


@pytest.fixture
def fake_entity_repo():
    """Fake EntityRepository."""
    from airweave.domains.sync_pipeline.fakes.entity_repository import (  # noqa: PLC0415
        FakeEntityRepository,  # noqa: PLC0415
    )

    return FakeEntityRepository()


@pytest.fixture
def fake_access_broker():
    """Fake AccessBroker."""
    from airweave.domains.access_control.fakes.broker import FakeAccessBroker  # noqa: PLC0415

    return FakeAccessBroker()


@pytest.fixture
def fake_converter_registry():
    """Fake ConverterRegistry."""
    from airweave.domains.converters.fakes.registry import FakeConverterRegistry  # noqa: PLC0415

    return FakeConverterRegistry()


@pytest.fixture
def fake_billing_webhook():
    """Fake BillingWebhookProcessor."""
    from airweave.adapters.payment.fake import FakePaymentGateway  # noqa: PLC0415
    from airweave.domains.billing.fakes.operations import FakeBillingOperations  # noqa: PLC0415
    from airweave.domains.billing.fakes.repository import (  # noqa: PLC0415
        FakeBillingPeriodRepository,
        FakeOrganizationBillingRepository,
    )
    from airweave.domains.billing.webhook_processor import BillingWebhookProcessor  # noqa: PLC0415
    from airweave.domains.organizations.fakes.repository import (  # noqa: PLC0415
        FakeOrganizationRepository,  # noqa: PLC0415
    )

    return BillingWebhookProcessor(
        payment_gateway=FakePaymentGateway(),
        billing_repo=FakeOrganizationBillingRepository(),
        period_repo=FakeBillingPeriodRepository(),
        billing_ops=FakeBillingOperations(),
        org_repo=FakeOrganizationRepository(),
    )


@pytest.fixture
def fake_payment_gateway():
    """Fake PaymentGateway."""
    from airweave.adapters.payment.fake import FakePaymentGateway  # noqa: PLC0415

    return FakePaymentGateway()


@pytest.fixture
def fake_collection_service():
    """Fake CollectionService."""
    from airweave.domains.collections.fakes.service import FakeCollectionService  # noqa: PLC0415

    return FakeCollectionService()


@pytest.fixture
def fake_dense_embedder_registry():
    """Fake DenseEmbedderRegistry for testing registry consumers."""
    from airweave.domains.embedders.fakes.registry import FakeDenseEmbedderRegistry  # noqa: PLC0415

    return FakeDenseEmbedderRegistry()


@pytest.fixture
def fake_sparse_embedder_registry():
    """Fake SparseEmbedderRegistry for testing registry consumers."""
    from airweave.domains.embedders.fakes.registry import (  # noqa: PLC0415
        FakeSparseEmbedderRegistry,  # noqa: PLC0415
    )

    return FakeSparseEmbedderRegistry()


@pytest.fixture
def fake_dense_embedder():
    """Fake DenseEmbedder that returns zero-vectors."""
    from airweave.domains.embedders.fakes.embedder import FakeDenseEmbedder  # noqa: PLC0415

    return FakeDenseEmbedder()


@pytest.fixture
def fake_sparse_embedder():
    """Fake SparseEmbedder that returns empty sparse vectors."""
    from airweave.domains.embedders.fakes.embedder import FakeSparseEmbedder  # noqa: PLC0415

    return FakeSparseEmbedder()


@pytest.fixture
def fake_usage_checker():
    """Fake UsageLimitChecker that allows all actions by default."""
    from airweave.domains.usage.fakes.limit_checker import FakeUsageLimitChecker  # noqa: PLC0415

    return FakeUsageLimitChecker()


@pytest.fixture
def fake_usage_ledger():
    """Fake UsageLedger that records calls in memory."""
    from airweave.domains.usage.fakes.ledger import FakeUsageLedger  # noqa: PLC0415

    return FakeUsageLedger()


@pytest.fixture
def fake_context_cache():
    """Fake ContextCache backed by in-memory dicts."""
    from airweave.adapters.cache.fake import FakeContextCache  # noqa: PLC0415

    return FakeContextCache()


@pytest.fixture
def fake_rate_limiter():
    """Fake RateLimiter that records calls and never rejects by default."""
    from airweave.adapters.rate_limiter.fake import FakeRateLimiter  # noqa: PLC0415

    return FakeRateLimiter()


@pytest.fixture
def fake_identity_provider():
    """Fake IdentityProvider with in-memory state."""
    from airweave.adapters.identity.fake import FakeIdentityProvider  # noqa: PLC0415

    return FakeIdentityProvider()


@pytest.fixture
def fake_organization_service():
    """Fake OrganizationService that records calls."""
    from airweave.domains.organizations.fakes.service import (  # noqa: PLC0415
        FakeOrganizationService,  # noqa: PLC0415
    )

    return FakeOrganizationService()


@pytest.fixture
def fake_email_service():
    """Fake EmailService that records calls."""
    from airweave.adapters.email.fake import FakeEmailService  # noqa: PLC0415

    return FakeEmailService()


@pytest.fixture
def fake_user_service():
    """Fake UserService that records calls."""
    from airweave.domains.users.fakes.service import FakeUserService  # noqa: PLC0415

    return FakeUserService()


@pytest.fixture
def fake_oauth_flow_service():
    """Fake OAuthFlowService."""
    from airweave.domains.oauth.fakes.flow_service import FakeOAuthFlowService  # noqa: PLC0415

    return FakeOAuthFlowService()


@pytest.fixture
def fake_oauth_callback_service():
    """Fake OAuthCallbackService."""
    from airweave.domains.oauth.fakes.callback_service import (  # noqa: PLC0415
        FakeOAuthCallbackService,  # noqa: PLC0415
    )

    return FakeOAuthCallbackService()


@pytest.fixture
def fake_init_session_repo():
    """Fake OAuthInitSessionRepository."""
    from airweave.domains.oauth.fakes.repository import (  # noqa: PLC0415
        FakeOAuthInitSessionRepository,  # noqa: PLC0415
    )

    return FakeOAuthInitSessionRepository()


@pytest.fixture
def fake_connect_service():
    """Fake ConnectService for testing."""
    from airweave.domains.connect.fakes.service import FakeConnectService  # noqa: PLC0415

    return FakeConnectService()


@pytest.fixture
def fake_browse_tree_service():
    """Fake BrowseTreeService (MagicMock)."""
    from unittest.mock import MagicMock  # noqa: PLC0415

    return MagicMock()


@pytest.fixture
def fake_selection_repo():
    """Fake NodeSelectionRepository (MagicMock)."""
    from unittest.mock import MagicMock  # noqa: PLC0415

    return MagicMock()


@pytest.fixture
def fake_instant_search():
    """Fake InstantSearchService."""
    from airweave.domains.search.fakes.instant import FakeInstantSearchService  # noqa: PLC0415

    return FakeInstantSearchService()


@pytest.fixture
def fake_classic_search():
    """Fake ClassicSearchService."""
    from airweave.domains.search.fakes.classic import FakeClassicSearchService  # noqa: PLC0415

    return FakeClassicSearchService()


@pytest.fixture
def fake_agentic_search_v2():
    """Fake AgenticSearchService (v2)."""
    from airweave.domains.search.fakes.agentic import FakeAgenticSearchService  # noqa: PLC0415

    return FakeAgenticSearchService()


@pytest.fixture
def fake_browse_service():
    """Fake BrowseService."""
    from airweave.domains.search.fakes.browse import FakeBrowseService  # noqa: PLC0415

    return FakeBrowseService()


@pytest.fixture
def fake_storage_backend():
    """Fake StorageBackend for testing storage consumers."""
    from airweave.domains.storage.fakes import FakeStorageBackend  # noqa: PLC0415

    return FakeStorageBackend()


@pytest.fixture
def fake_arf_service():
    """Fake ArfService for testing ARF consumers."""
    from airweave.domains.arf.fakes.service import FakeArfService  # noqa: PLC0415

    return FakeArfService()


@pytest.fixture
def test_container(
    tmp_path,
    fake_storage_backend,
    fake_arf_service,
    fake_context_cache,
    fake_rate_limiter,
    fake_health_service,
    fake_event_bus,
    fake_pubsub,
    fake_webhook_publisher,
    fake_webhook_admin,
    fake_circuit_breaker,
    fake_ocr_provider,
    fake_metrics_service,
    fake_source_service,
    fake_endpoint_verifier,
    fake_webhook_service,
    fake_source_registry,
    fake_auth_provider_registry,
    fake_auth_provider_service,
    fake_entity_definition_registry,
    fake_sc_repo,
    fake_collection_repo,
    fake_conn_repo,
    fake_cred_repo,
    fake_credential_service,
    fake_oauth1_service,
    fake_oauth2_service,
    fake_redirect_session_repo,
    fake_oauth_flow_service,
    fake_oauth_callback_service,
    fake_init_session_repo,
    fake_source_connection_service,
    fake_source_lifecycle_service,
    fake_response_builder,
    fake_temporal_workflow_service,
    fake_temporal_schedule_service,
    fake_sync_repo,
    fake_sync_cursor_repo,
    fake_sync_cursor_service,
    fake_sync_job_repo,
    fake_sync_job_service,
    fake_sync_job_state_machine,
    fake_sync_service,
    fake_billing_service,
    fake_billing_webhook,
    fake_payment_gateway,
    fake_collection_service,
    fake_user_org_repo,
    fake_dense_embedder_registry,
    fake_sparse_embedder_registry,
    fake_dense_embedder,
    fake_sparse_embedder,
    fake_usage_checker,
    fake_usage_ledger,
    fake_identity_provider,
    fake_organization_service,
    fake_email_service,
    fake_user_service,
    fake_connect_service,
    fake_browse_tree_service,
    fake_selection_repo,
    fake_instant_search,
    fake_classic_search,
    fake_agentic_search_v2,
    fake_browse_service,
    fake_sync_factory,
    fake_entity_repo,
    fake_access_broker,
    fake_converter_registry,
):
    """A Container with all dependencies replaced by fakes.

    Use this when testing code that receives a Container or individual
    protocols via dependency injection.

    For partial overrides, use container.replace():
        real_bus_container = test_container.replace(event_bus=InMemoryEventBus())
    """
    from airweave.core.container import Container  # noqa: PLC0415
    from airweave.domains.storage.sync_file_manager import SyncFileManager  # noqa: PLC0415

    return Container(
        storage_backend=fake_storage_backend,
        sync_file_manager=SyncFileManager(
            backend=fake_storage_backend,
            temp_cache_dir=tmp_path / "cache",
        ),
        arf_service=fake_arf_service,
        context_cache=fake_context_cache,
        rate_limiter=fake_rate_limiter,
        health=fake_health_service,
        event_bus=fake_event_bus,
        pubsub=fake_pubsub,
        webhook_publisher=fake_webhook_publisher,
        webhook_admin=fake_webhook_admin,
        endpoint_verifier=fake_endpoint_verifier,
        webhook_service=fake_webhook_service,
        circuit_breaker=fake_circuit_breaker,
        ocr_provider=fake_ocr_provider,
        metrics=fake_metrics_service,
        source_service=fake_source_service,
        source_registry=fake_source_registry,
        auth_provider_registry=fake_auth_provider_registry,
        auth_provider_service=fake_auth_provider_service,
        entity_definition_registry=fake_entity_definition_registry,
        collection_service=fake_collection_service,
        browse_tree_service=fake_browse_tree_service,
        selection_repo=fake_selection_repo,
        sc_repo=fake_sc_repo,
        collection_repo=fake_collection_repo,
        conn_repo=fake_conn_repo,
        cred_repo=fake_cred_repo,
        credential_service=fake_credential_service,
        user_org_repo=fake_user_org_repo,
        oauth1_service=fake_oauth1_service,
        oauth2_service=fake_oauth2_service,
        redirect_session_repo=fake_redirect_session_repo,
        oauth_flow_service=fake_oauth_flow_service,
        oauth_callback_service=fake_oauth_callback_service,
        init_session_repo=fake_init_session_repo,
        source_connection_service=fake_source_connection_service,
        connect_service=fake_connect_service,
        source_lifecycle_service=fake_source_lifecycle_service,
        response_builder=fake_response_builder,
        temporal_workflow_service=fake_temporal_workflow_service,
        temporal_schedule_service=fake_temporal_schedule_service,
        sync_repo=fake_sync_repo,
        sync_cursor_repo=fake_sync_cursor_repo,
        sync_cursor_service=fake_sync_cursor_service,
        sync_job_repo=fake_sync_job_repo,
        sync_job_service=fake_sync_job_service,
        sync_job_state_machine=fake_sync_job_state_machine,
        sync_service=fake_sync_service,
        billing_service=fake_billing_service,
        billing_webhook=fake_billing_webhook,
        payment_gateway=fake_payment_gateway,
        dense_embedder_registry=fake_dense_embedder_registry,
        sparse_embedder_registry=fake_sparse_embedder_registry,
        dense_embedder=fake_dense_embedder,
        sparse_embedder=fake_sparse_embedder,
        usage_checker=fake_usage_checker,
        usage_ledger=fake_usage_ledger,
        identity_provider=fake_identity_provider,
        organization_service=fake_organization_service,
        email_service=fake_email_service,
        user_service=fake_user_service,
        instant_search=fake_instant_search,
        classic_search=fake_classic_search,
        agentic_search=fake_agentic_search_v2,
        browse_service=fake_browse_service,
        sync_factory=fake_sync_factory,
        entity_repo=fake_entity_repo,
        access_broker=fake_access_broker,
        converter_registry=fake_converter_registry,
    )
