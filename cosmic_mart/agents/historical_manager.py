"""Historical Manager — shards the SKU catalogue across parallel workers (map step)."""

from __future__ import annotations

from ..models import SKU
from .base import Agent


class Shard:
    """One unit of work assigned to a single worker."""

    def __init__(self, shard_id: int, skus: list[SKU]):
        self.shard_id = shard_id
        self.skus = skus


class HistoricalManager(Agent):
    """Receives the trigger and splits the catalogue into `n` roughly equal shards.

    n is configurable based on catalogue size and available compute. The manager
    owns completion tracking and retries in a real deployment; offline it performs
    a deterministic round-robin split so the same catalogue always shards the same way.
    """

    name = "historical_manager"

    def __init__(self, worker_count: int = 3):
        self.worker_count = max(1, worker_count)

    def assign_shards(self, catalogue: list[SKU]) -> list[Shard]:
        n = min(self.worker_count, len(catalogue)) or 1
        buckets: list[list[SKU]] = [[] for _ in range(n)]
        # Round-robin keeps shard sizes balanced regardless of catalogue length.
        for i, sku in enumerate(catalogue):
            buckets[i % n].append(sku)
        shards = [Shard(shard_id=i, skus=b) for i, b in enumerate(buckets) if b]
        self._log(catalogue_size=len(catalogue), shards=len(shards))
        return shards
