"""Worker agent — processes one shard into per-item demand context (map step).

Workers are independent: no inter-worker communication. Each writes its outputs
keyed by SKU. Total processing time is bounded by the slowest shard, not the full
catalogue.
"""

from __future__ import annotations

from ..adapters.earth_sales import EarthSalesProvider
from ..adapters.regional_data import RegionalDataProvider
from ..models import PerItemDemandContext, WorkerOutput, YoYAdjustment
from .base import Agent
from .historical_manager import Shard


class HistoricalWorker(Agent):
    """Loads Earth + regional history, applies YoY annotations, per item in its shard."""

    name = "historical_worker"

    def __init__(
        self,
        earth: EarthSalesProvider,
        regional: RegionalDataProvider,
        sparse_earth_threshold: float = 50.0,
    ):
        self.earth = earth
        self.regional = regional
        self.sparse_earth_threshold = sparse_earth_threshold

    async def process(self, shard: Shard) -> WorkerOutput:
        items: list[PerItemDemandContext] = []
        for sku in shard.skus:
            earth_raw = await self.earth.observe(sku)
            regional_raw = await self.regional.observe(sku)

            earth_baseline = float(earth_raw["monthly_units"])
            regional_baseline = float(regional_raw["monthly_units"])

            flags: list[str] = []
            if earth_baseline < self.sparse_earth_threshold:
                flags.append("sparse_earth_data")
            if regional_raw.get("structural_similarity", 1.0) < 0.6:
                flags.append("weak_analogue")

            items.append(
                PerItemDemandContext(
                    sku=sku,
                    earth_baseline=round(earth_baseline, 1),
                    regional_baseline=round(regional_baseline, 1),
                    yoy_adjustments=self._yoy(sku, earth_raw),
                    data_quality_flags=flags,
                )
            )
        self._log(shard=shard.shard_id, items=len(items))
        return WorkerOutput(shard_id=shard.shard_id, worker_id=f"worker-{shard.shard_id}", items=items)

    def _yoy(self, sku, earth_raw: dict) -> list[YoYAdjustment]:
        """Human-curated annotation layer over raw sales (seasonal peaks, promos, etc.)."""
        trend = float(earth_raw.get("trend_pct_yoy", 0.0))
        adjustments = [
            YoYAdjustment(
                year=2025,
                annotation_type="seasonal_peak",
                description=f"{sku.category} peak window",
                impact_multiplier=round(1.0 + max(trend, 0.0) / 100.0, 3),
            )
        ]
        if trend < 0:
            adjustments.append(
                YoYAdjustment(
                    year=2025,
                    annotation_type="supplier_disruption",
                    description="Trailing softness from supply constraint",
                    impact_multiplier=round(1.0 + trend / 100.0, 3),
                )
            )
        return adjustments
