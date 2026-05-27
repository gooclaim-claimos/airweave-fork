"""Metrics renderer adapters (Prometheus + Fake).

Prometheus implementation wraps a CollectorRegistry so the metrics server
can serialize all registered collectors into Prometheus text exposition
format.
"""

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from airweave.core.protocols.metrics import MetricsRenderer


def _parse_content_type(raw: str) -> tuple[str, str]:
    """Split a Content-Type string into (media-type, charset)."""
    parts = [p.strip() for p in raw.split(";")]
    charset = "utf-8"
    non_charset: list[str] = []
    for part in parts:
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip()
        else:
            non_charset.append(part)
    return "; ".join(non_charset), charset


_CONTENT_TYPE, _CHARSET = _parse_content_type(CONTENT_TYPE_LATEST)


class PrometheusMetricsRenderer(MetricsRenderer):
    """Render all metrics in a shared CollectorRegistry."""

    def __init__(self, registry: CollectorRegistry) -> None:
        """Wrap a CollectorRegistry for later text-format serialization.

        Args:
            registry: The Prometheus CollectorRegistry whose metrics will be
                rendered by :meth:`generate`.
        """
        self._registry = registry

    @property
    def content_type(self) -> str:
        """Return the Prometheus exposition-format media type (no charset)."""
        return _CONTENT_TYPE

    @property
    def charset(self) -> str:
        """Return the charset associated with the exposition format."""
        return _CHARSET

    def generate(self) -> bytes:
        """Serialize the wrapped registry to Prometheus text exposition bytes.

        Returns:
            UTF-8 encoded Prometheus text-format payload.
        """
        return generate_latest(self._registry)


# ---------------------------------------------------------------------------
# Fake
# ---------------------------------------------------------------------------


class FakeMetricsRenderer(MetricsRenderer):
    """In-memory spy implementing the MetricsRenderer protocol."""

    def __init__(self) -> None:
        """Initialize the fake renderer with a zeroed call counter."""
        self.generate_calls: int = 0

    @property
    def content_type(self) -> str:
        """Return a fixed ``text/plain`` content type for tests."""
        return "text/plain"

    @property
    def charset(self) -> str:
        """Return a fixed ``utf-8`` charset for tests."""
        return "utf-8"

    def generate(self) -> bytes:
        """Return a stub Prometheus payload and record the invocation.

        Returns:
            A small constant byte string standing in for real metrics.
        """
        self.generate_calls += 1
        return b"# fake metrics\n"
