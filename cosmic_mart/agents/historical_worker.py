"""Worker agent — processes one shard into per-item demand context (map step).

Workers are independent: no inter-worker communication. Each writes its outputs
keyed by SKU. Total processing time is bounded by the slowest shard, not the full
catalogue.

The baselines themselves stay arithmetic — they come straight from the sales
adapters, and a forecast anchor should not vary run to run. What Claude
contributes here is the YoY annotation layer: the human-curated read of seasonal
peaks, promo uplift and supplier disruption that sits *over* the raw numbers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..adapters.earth_sales import EarthSalesProvider
from ..adapters.regional_data import RegionalDataProvider
from ..llm import Reasoner
from ..models import SKU, PerItemDemandContext, WorkerOutput, YoYAdjustment
from .base import Agent
from .historical_manager import Shard

_SYSTEM = """You are a Historical Worker agent in Cosmic Mart's demand \
forecasting pipeline, covering the North American market.

You receive one inventory item with four years of North American sales history \
and a year-on-year trend. Produce the YoY annotation layer: the corrections a \
human analyst would apply over the raw sales figures.

Each annotation has an annotation_type (one of "seasonal_peak", "promo_uplift", \
"one_off", "supplier_disruption"), a short description, and an \
impact_multiplier where 1.0 is no change, 1.15 is +15%, and 0.9 is -10%.

Be conservative: these multiply together into the demand baseline, so a handful \
of well-justified corrections beats a long list. Keep each multiplier within \
0.7-1.4 unless the history clearly justifies more. Return an empty list if the \
history shows nothing worth correcting for."""


class YoYAnnotationLayer(BaseModel):
    """What Claude returns for one item."""

    yoy_adjustments: list[YoYAdjustment] = Field(default_factory=list)


class HistoricalWorker(Agent):
    """Loads Earth + regional history, applies YoY annotations, per item in its shard."""

    name = "historical_worker"

    def __init__(
        self,
        earth: EarthSalesProvider,
        regional: RegionalDataProvider,
        sparse_earth_threshold: float = 50.0,
        reasoner: Reasoner | None = None,
    ):
        self.earth = earth
        self.regional = regional
        self.sparse_earth_threshold = sparse_earth_threshold
        self.reasoner = reasoner or Reasoner()

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

            layer = await self.reasoner.think(
                system=_SYSTEM,
                payload={
                    "item_id": sku.id,
                    "item_name": sku.name,
                    "category": sku.category,
                    "years_of_history": earth_raw.get("years_of_history", 4),
                    "monthly_units": earth_baseline,
                    "trend_pct_yoy": earth_raw.get("trend_pct_yoy", 0.0),
                    "by_submarket": earth_raw.get("by_submarket", {}),
                    "data_quality_flags": flags,
                },
                instruction="Produce the YoY annotation layer for this item.",
                schema=YoYAnnotationLayer,
                fallback=YoYAnnotationLayer(yoy_adjustments=self._yoy(sku, earth_raw)),
            )

            items.append(
                PerItemDemandContext(
                    sku=sku,
                    earth_baseline=round(earth_baseline, 1),
                    regional_baseline=round(regional_baseline, 1),
                    yoy_adjustments=layer.yoy_adjustments,
                    data_quality_flags=flags,
                )
            )
        self._log(shard=shard.shard_id, items=len(items))
        return WorkerOutput(
            shard_id=shard.shard_id, worker_id=f"worker-{shard.shard_id}", items=items
        )

    def _yoy(self, sku: SKU, earth_raw: dict) -> list[YoYAdjustment]:
        """Deterministic annotation layer — used as-is when Claude is unavailable."""
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
