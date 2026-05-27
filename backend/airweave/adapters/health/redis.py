"""Redis health probe adapter."""

import time

from redis.asyncio import Redis

from airweave.core.health.protocols import HealthProbe
from airweave.schemas.health import CheckStatus, DependencyCheck


class RedisHealthProbe(HealthProbe):
    """Probes Redis by sending a ``PING`` command."""

    def __init__(self, client: Redis) -> None:
        """Initialize the probe with an async Redis client.

        Args:
            client: Async Redis client used to issue the ``PING`` command.
        """
        self._client = client

    @property
    def name(self) -> str:
        """Return the probe identifier used in health reports."""
        return "redis"

    async def check(self) -> DependencyCheck:
        """Send ``PING`` to Redis and measure round-trip latency.

        Returns:
            A ``DependencyCheck`` reporting status ``up`` and measured latency in ms.
        """
        start = time.perf_counter()
        await self._client.ping()
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(status=CheckStatus.up, latency_ms=round(latency, 2))
