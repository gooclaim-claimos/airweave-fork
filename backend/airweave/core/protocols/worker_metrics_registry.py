"""WorkerMetricsRegistry protocol for reading worker metrics state.

Captures the read surface of WorkerMetricsRegistry that
WorkerControlServer depends on, so the control server can accept any
implementation (real registry, mock, or fake).
"""

from typing import Any, Protocol, TypedDict, runtime_checkable


class SyncMetricDetail(TypedDict):
    """Per-sync metadata exposed by the metrics registry."""

    sync_id: str
    sync_job_id: str
    org_name: str
    source_type: str


class SyncWorkerCount(TypedDict):
    """Per-sync worker count exposed by the metrics registry."""

    sync_id: str
    active_and_pending_worker_count: int


@runtime_checkable
class WorkerMetricsRegistryProtocol(Protocol):
    """Protocol for the read surface of the worker metrics registry."""

    def get_pod_ordinal(self) -> str:
        """Return the stable ordinal identifying this worker pod."""
        ...

    async def get_metrics_summary(self) -> dict[str, Any]:
        """Return a snapshot of aggregate worker metrics for the pod."""
        ...

    async def get_per_connector_metrics(self) -> dict[str, dict[str, int]]:
        """Return metrics broken down by source connector short_name."""
        ...

    async def get_total_active_and_pending_workers(self) -> int:
        """Return the combined count of active and pending sync workers."""
        ...

    async def get_detailed_sync_metrics(self) -> list[SyncMetricDetail]:
        """Return per-sync metadata for every sync tracked by the registry."""
        ...

    async def get_per_sync_worker_counts(self) -> list[SyncWorkerCount]:
        """Return active+pending worker counts grouped by sync_id."""
        ...
