"""Agentic search metrics adapters (Prometheus + Fake).

Prometheus implementation uses a caller-supplied CollectorRegistry so
these metrics are served alongside the HTTP metrics on the same
``/metrics`` endpoint.
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram

from airweave.core.protocols.metrics import AgenticSearchMetrics

_ITERATION_BUCKETS = (1, 2, 3, 4, 5, 7, 10)
_STEP_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_RESULTS_BUCKETS = (0, 1, 5, 10, 25, 50, 100, 250)
_DURATION_BUCKETS = (0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 60.0, 120.0)


class PrometheusAgenticSearchMetrics(AgenticSearchMetrics):
    """Prometheus-backed agentic search metrics collection."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Register agentic search metrics on a Prometheus collector registry.

        Args:
            registry: Existing ``CollectorRegistry`` to register metrics against so they
                are exposed on the shared ``/metrics`` endpoint. A new registry is
                created when ``None`` is provided (useful for isolated tests).
        """
        self._registry = registry or CollectorRegistry()

        self._requests_total = Counter(
            "airweave_agentic_search_requests_total",
            "Total agentic search requests",
            ["mode", "streaming"],
            registry=self._registry,
        )

        self._errors_total = Counter(
            "airweave_agentic_search_errors_total",
            "Total agentic search errors",
            ["mode", "streaming"],
            registry=self._registry,
        )

        self._iterations = Histogram(
            "airweave_agentic_search_iterations",
            "Number of iterations per agentic search",
            ["mode"],
            buckets=_ITERATION_BUCKETS,
            registry=self._registry,
        )

        self._step_duration = Histogram(
            "airweave_agentic_search_step_duration_seconds",
            "Duration of individual pipeline steps in seconds",
            ["step"],
            buckets=_STEP_DURATION_BUCKETS,
            registry=self._registry,
        )

        self._results_per_search = Histogram(
            "airweave_agentic_search_results_per_search",
            "Number of results returned per search",
            buckets=_RESULTS_BUCKETS,
            registry=self._registry,
        )

        self._duration = Histogram(
            "airweave_agentic_search_duration_seconds",
            "End-to-end agentic search duration in seconds",
            ["mode"],
            buckets=_DURATION_BUCKETS,
            registry=self._registry,
        )

    # -- AgenticSearchMetrics protocol methods --

    def inc_search_requests(self, mode: str, streaming: bool) -> None:
        """Increment the total agentic search request counter.

        Args:
            mode: Search mode label (e.g. ``"raw"`` or ``"agentic"``).
            streaming: ``True`` when the caller requested a streaming response.
        """
        self._requests_total.labels(mode=mode, streaming=str(streaming).lower()).inc()

    def inc_search_errors(self, mode: str, streaming: bool) -> None:
        """Increment the agentic search error counter.

        Args:
            mode: Search mode label that errored.
            streaming: ``True`` when the failing request was a streaming call.
        """
        self._errors_total.labels(mode=mode, streaming=str(streaming).lower()).inc()

    def observe_iterations(self, mode: str, count: int) -> None:
        """Record the number of agent iterations executed for a search.

        Args:
            mode: Search mode label the iteration count applies to.
            count: Number of iterations executed by the agent loop.
        """
        self._iterations.labels(mode=mode).observe(count)

    def observe_step_duration(self, step: str, duration: float) -> None:
        """Record the wall-clock duration of an individual pipeline step.

        Args:
            step: Pipeline step name (e.g. ``"plan"``, ``"retrieve"``).
            duration: Step duration in seconds.
        """
        self._step_duration.labels(step=step).observe(duration)

    def observe_results_per_search(self, count: int) -> None:
        """Record the number of results returned by a single search.

        Args:
            count: Number of result rows returned to the caller.
        """
        self._results_per_search.observe(count)

    def observe_duration(self, mode: str, duration: float) -> None:
        """Record end-to-end agentic search duration.

        Args:
            mode: Search mode label the duration applies to.
            duration: End-to-end search duration in seconds.
        """
        self._duration.labels(mode=mode).observe(duration)


# ---------------------------------------------------------------------------
# Fake
# ---------------------------------------------------------------------------


@dataclass
class StepDurationRecord:
    """Single observed step duration."""

    step: str
    duration: float


class FakeAgenticSearchMetrics(AgenticSearchMetrics):
    """In-memory spy implementing the AgenticSearchMetrics protocol."""

    def __init__(self) -> None:
        """Initialize empty buffers for every recorded metric stream."""
        self.search_requests: list[tuple[str, bool]] = []
        self.search_errors: list[tuple[str, bool]] = []
        self.iterations: list[tuple[str, int]] = []
        self.step_durations: list[StepDurationRecord] = []
        self.results_counts: list[int] = []
        self.durations: list[tuple[str, float]] = []

    def inc_search_requests(self, mode: str, streaming: bool) -> None:
        """Append a ``(mode, streaming)`` tuple to the request buffer."""
        self.search_requests.append((mode, streaming))

    def inc_search_errors(self, mode: str, streaming: bool) -> None:
        """Append a ``(mode, streaming)`` tuple to the error buffer."""
        self.search_errors.append((mode, streaming))

    def observe_iterations(self, mode: str, count: int) -> None:
        """Append a ``(mode, count)`` tuple to the iterations buffer."""
        self.iterations.append((mode, count))

    def observe_step_duration(self, step: str, duration: float) -> None:
        """Append a ``StepDurationRecord`` to the step durations buffer."""
        self.step_durations.append(StepDurationRecord(step, duration))

    def observe_results_per_search(self, count: int) -> None:
        """Append a per-search result count to the results buffer."""
        self.results_counts.append(count)

    def observe_duration(self, mode: str, duration: float) -> None:
        """Append a ``(mode, duration)`` tuple to the durations buffer."""
        self.durations.append((mode, duration))

    # -- test helpers --

    def clear(self) -> None:
        """Reset all recorded state."""
        self.search_requests.clear()
        self.search_errors.clear()
        self.iterations.clear()
        self.step_durations.clear()
        self.results_counts.clear()
        self.durations.clear()
