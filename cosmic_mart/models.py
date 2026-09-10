"""Typed contracts exchanged between agents.

Data contracts mirror §7.2 of the pipeline spec: per-item demand context
(worker output), merged baseline (merge output), signal context (signal report
output), and order recommendation (synthesizer output).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Core identifiers -------------------------------------------------------


class Market(BaseModel):
    code: str
    name: str
    region: str
    currency: str


class SKU(BaseModel):
    id: str
    name: str
    category: str
    unit_cost_usd: float
    unit_price_usd: float
    # Fraction of value lost per day held, driving the depreciation clock.
    depreciation_rate_daily: float


class SKUMarket(BaseModel):
    """A SKU scoped to one sub-market."""

    sku: SKU
    market: Market

    @property
    def key(self) -> str:
        return f"{self.sku.id}@{self.market.code}"


# --- Current inventory (the SKU catalogue source) ---------------------------


class InventoryRecord(BaseModel):
    """One row of the current-inventory database.

    The Signal Processing Agent reads the catalogue from here rather than being
    handed a hardcoded list: `item_id` and `item_name` are the fields it needs to
    scope signal matching to active inventory. `InventorySource.catalogue()`
    projects these rows back into `SKU` objects for the rest of the pipeline.
    """

    item_id: str = Field(description="Item identification number, e.g. GAD-1001")
    item_name: str = Field(description="Human-readable item name")
    category: str
    sub_market: str
    warehouse: str
    on_hand_units: int = Field(ge=0)
    inbound_units: int = Field(ge=0)


# --- Trigger ----------------------------------------------------------------


class TriggerContext(BaseModel):
    """Fires the pipeline.

    All pipeline runs are schedule-driven (spec §2). `reason` is a single-member
    Literal on purpose: there is no anomaly-event trigger, and the type makes
    reintroducing one a deliberate change rather than a passing string.
    """

    run_id: str
    triggered_at: datetime = Field(default_factory=_now)
    sku_catalogue: list[SKU] = Field(default_factory=list)
    reason: Literal["daily_schedule"] = "daily_schedule"
    scheduled_local_time: str = "02:00"


# --- Historical branch (§7.2 data contracts) --------------------------------


class YoYAdjustment(BaseModel):
    """One human-curated annotation applied as a correction layer over raw sales."""

    year: int
    annotation_type: str  # "seasonal_peak", "promo_uplift", "one_off", "supplier_disruption"
    description: str
    impact_multiplier: float  # e.g. 1.15 = +15% correction


class PerItemDemandContext(BaseModel):
    """Worker output: { sku, earth_baseline, regional_baseline, yoy_adjustments, data_quality_flags }."""

    sku: SKU
    earth_baseline: float = Field(ge=0.0, description="Units / 30d from 4yr Earth history")
    regional_baseline: float = Field(ge=0.0, description="Units / 30d from 25yr regional analogues")
    yoy_adjustments: list[YoYAdjustment] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)


class WorkerOutput(BaseModel):
    """One worker's processed shard of the SKU catalogue."""

    shard_id: int
    worker_id: str
    items: list[PerItemDemandContext] = Field(default_factory=list)


class MergedBaseline(BaseModel):
    """Merge output: { sku, weighted_baseline, earth_weight, regional_weight, data_quality_flags }."""

    sku: SKU
    weighted_baseline: float = Field(ge=0.0, description="earth*0.9 + regional*0.1, per item")
    earth_baseline: float = Field(ge=0.0)
    regional_baseline: float = Field(ge=0.0)
    earth_weight: float = 0.9
    regional_weight: float = 0.1
    yoy_adjustments: list[YoYAdjustment] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)


# --- Signals branch ---------------------------------------------------------


class SignalItem(BaseModel):
    """One detected signal mapped to a SKU."""

    type: Literal["promo", "large_event", "news"]
    source: str
    strength: float = Field(ge=0.0, le=1.0)
    direction: Literal["up", "down", "neutral"]
    description: str = ""
    # §7.2 contract field: set by the synthesizer, which is the only stage that
    # holds the historical baseline to compare against.
    conflict_with_baseline: bool = False
    # Set by the Signal Report Agent: this signal pulls against the net signal
    # direction for its item. Intra-signal tension, not baseline tension — the
    # two are different things and were previously conflated in one field.
    opposes_net_pull: bool = False


class PerItemSignalContext(BaseModel):
    """Signal report output: { sku, signals: [...] }. Conflict is recorded, never averaged."""

    sku: SKU
    signals: list[SignalItem] = Field(default_factory=list)
    has_conflict: bool = False
    # Net signal pull, +ve raises demand vs baseline. Preserved even under conflict.
    net_direction: Literal["up", "down", "neutral"] = "neutral"
    # One sentence naming the drivers on each side; surfaced to the reviewer.
    rationale: str = ""


# --- Demand synthesizer + outputs -------------------------------------------


class ForecastRange(BaseModel):
    units_low: int = Field(ge=0)
    units_expected: int = Field(ge=0)
    units_high: int = Field(ge=0)
    widened: bool = False  # True when conflict forced the range to cover both scenarios


class EscalationFlag(BaseModel):
    flag_type: Literal["high_value", "low_confidence", "high_divergence"]
    reason: str


class OrderRecommendation(BaseModel):
    """Synthesizer output: { sku, action, quantity, supplier, warehouse, forecast_range,
    confidence, escalation_flags }."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    sku: SKU
    action: Literal["reorder", "rebalance", "hold"]
    quantity: int = Field(ge=0)
    supplier: str | None = None
    warehouse: str | None = None
    forecast_range: ForecastRange
    confidence: float = Field(ge=0.0, le=1.0)
    escalation_flags: list[EscalationFlag] = Field(default_factory=list)
    # Carried through from the merged baseline so the reviewer sees the caveat
    # on the recommendation itself, not only by opening the reasoning panel.
    data_quality_flags: list[str] = Field(default_factory=list)
    conflict_summary: str | None = None
    divergence_score: float = 0.0
    hist_weight: float = 0.7
    sig_weight: float = 0.3
    reasoning: str = ""

    @property
    def needs_review(self) -> bool:
        return bool(self.escalation_flags)


# --- Human in the loop ------------------------------------------------------


class HumanReviewDecision(BaseModel):
    recommendation_id: str
    sku_id: str
    action: Literal["approve", "modify", "reject", "escalate"]
    modifier_notes: str | None = None
    reviewer: str | None = None
    decided_at: datetime = Field(default_factory=_now)


# --- Run output -------------------------------------------------------------


class PipelineRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    started_at: datetime = Field(default_factory=_now)
    trigger: TriggerContext | None = None
    worker_outputs: list[WorkerOutput] = Field(default_factory=list)
    merged_baselines: list[MergedBaseline] = Field(default_factory=list)
    signal_contexts: list[PerItemSignalContext] = Field(default_factory=list)
    order_recommendations: list[OrderRecommendation] = Field(default_factory=list)
    human_decisions: list[HumanReviewDecision] = Field(default_factory=list)
