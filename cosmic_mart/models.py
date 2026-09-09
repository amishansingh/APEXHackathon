"""Typed contracts exchanged between agents."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Cadence(str, Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    REAL_TIME = "real-time"
    HOURLY = "hourly"
    EVENT_DRIVEN = "event-driven"


class SignalKind(str, Enum):
    CULTURAL = "cultural"
    WEATHER = "weather"
    SOCIAL = "social"
    MACRO = "macro"
    LOCAL_EVENTS = "local_events"
    SEASONALITY = "seasonality"


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
    """The unit of work flowing through the whole pipeline."""

    sku: SKU
    market: Market

    @property
    def key(self) -> str:
        return f"{self.sku.id}@{self.market.code}"


# --- Signal layer -----------------------------------------------------------


class SignalReading(BaseModel):
    """One signal agent's read on a single SKU/market pair."""

    kind: SignalKind
    demand_impact_pct: float = Field(
        description="Expected percent change in demand vs baseline. -100 to +300.",
        ge=-100,
        le=300,
    )
    confidence: float = Field(description="0.0 to 1.0", ge=0.0, le=1.0)
    horizon_days: int = Field(description="Days over which the impact plays out", ge=1, le=365)
    rationale: str = Field(description="One or two sentences citing the specific driver.")
    drivers: list[str] = Field(default_factory=list, description="Named causes, e.g. 'Diwali'.")


class AttributedSignal(BaseModel):
    """A reading plus the provenance the synthesizer needs to weight it."""

    reading: SignalReading
    agent: str
    cadence: Cadence
    weight: float = 1.0
    observed_at: datetime = Field(default_factory=_now)


# --- Demand synthesis -------------------------------------------------------


class TriggerSignal(BaseModel):
    agent_id: str
    market: str
    event_type: str
    estimated_demand_impact: float  # multiplier, e.g. 1.2 = +20%
    affected_sku_categories: list[str]
    timestamp: datetime = Field(default_factory=_now)
    cadence: Cadence
    first_run: bool = False
    confidence_score: float = Field(ge=0.0, le=1.0)


class AffectedSKU(BaseModel):
    sku_id: str
    market: str
    category: str


class ItemSynthesizerOutput(BaseModel):
    affected_skus: list[AffectedSKU]
    source_trigger: TriggerSignal


class P1ImpactScore(BaseModel):
    importance: float = Field(ge=0.0, le=1.0)
    magnitude: float  # demand multiplier
    longevity: float  # weeks


class P1Output(BaseModel):
    sku_id: str
    market: str
    agent_id: str
    data: dict
    impact_score: P1ImpactScore
    risk_flag: bool = False


class P2Output(BaseModel):
    sku_id: str
    market: str
    agent_id: str
    data: dict
    hard_override: bool = False
    immediate_rerun_trigger: bool = False


class DemandForecast(BaseModel):
    units_low: int = Field(ge=0)
    units_expected: int = Field(ge=0)
    units_high: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    conflicting_signals: list[str] = Field(
        default_factory=list,
        description="Names of signal agents whose readings pull in opposite directions.",
    )
    reasoning: str
    sku_classification: str = "established"
    risk_flag: bool = False
    first_run_signal: bool = False
    route: str = "automated_report"
    recommended_order_quantity: int = 0
    order_trigger_date: str = ""


class SynthesizedDemand(BaseModel):
    target: SKUMarket
    baseline_units: int
    forecast: DemandForecast
    inputs: list[AttributedSignal]
    escalate_to_human: bool = False


# --- Overstock detection ----------------------------------------------------


class LossComponents(BaseModel):
    capital_tied_usd: float
    storage_fees_usd: float
    depreciation_usd: float

    @property
    def total_usd(self) -> float:
        return self.capital_tied_usd + self.storage_fees_usd + self.depreciation_usd


class OverstockAssessment(BaseModel):
    target: SKUMarket
    units_on_hand: int
    units_excess: int
    daily_loss: LossComponents
    days_of_cover: float
    severity: Literal["none", "low", "moderate", "severe"]
    commentary: str


# --- Proposed action --------------------------------------------------------


class ActionType(str, Enum):
    TRANSFER = "transfer"
    DISCOUNT = "discount"
    HOLD = "hold"
    REORDER = "reorder"
    SUPPLIER_SWITCH = "supplier_switch"


class ProposedAction(BaseModel):
    """What the system is considering doing about a SKU/market imbalance."""

    id: str
    action: ActionType
    target: SKUMarket
    units: int
    destination_market: str | None = None
    discount_pct: float | None = None
    description: str


# --- Parallel evaluation ----------------------------------------------------


class CarbonScore(BaseModel):
    score: float = Field(
        description="Normalised 0-100. Higher means a heavier carbon burden.",
        ge=0.0,
        le=100.0,
    )
    emissions_kg_co2e: float = Field(ge=0.0)
    drivers: list[str] = Field(default_factory=list)
    credit_eligible: bool = Field(
        description="True when this action beats the status-quo baseline on emissions."
    )
    reasoning: str


class FinancialBenefit(BaseModel):
    gross_benefit_usd: float
    execution_cost_usd: float = Field(ge=0.0)
    net_benefit_usd: float
    payback_days: float = Field(ge=0.0)
    reasoning: str


# --- Tradeoff ---------------------------------------------------------------


class Verdict(str, Enum):
    APPROVE = "approve"
    FLAG = "flag"
    BLOCK = "block"


class TradeoffDecision(BaseModel):
    verdict: Verdict
    net_score: float
    carbon_penalty_usd: float
    reasoning: str
    escalation_owner: Literal["CFO", "CSO", "none"] = "none"


class EvaluatedAction(BaseModel):
    action: ProposedAction
    carbon: CarbonScore
    financial: FinancialBenefit
    decision: TradeoffDecision


# --- Human gate -------------------------------------------------------------


class GateItem(BaseModel):
    action_id: str
    summary: str
    verdict: Verdict
    owner: Literal["CFO", "CSO", "none"]
    net_benefit_usd: float
    carbon_score: float
    context: str


class BlockRecord(BaseModel):
    """Fed back to the overstock agent so the same proposal stops recurring."""

    action_id: str
    target_key: str
    action: ActionType
    reason: str
    blocked_at: datetime = Field(default_factory=_now)


# --- Run output -------------------------------------------------------------


class PipelineRun(BaseModel):
    started_at: datetime = Field(default_factory=_now)
    demand: list[SynthesizedDemand] = Field(default_factory=list)
    overstock: list[OverstockAssessment] = Field(default_factory=list)
    evaluated: list[EvaluatedAction] = Field(default_factory=list)
    gate_queue: list[GateItem] = Field(default_factory=list)
    blocked: list[BlockRecord] = Field(default_factory=list)
    carbon_credits_kg: float = 0.0
    p3_triggers: list[TriggerSignal] = Field(default_factory=list)
    item_synthesizer_outputs: list[ItemSynthesizerOutput] = Field(default_factory=list)
    p1_outputs: list[P1Output] = Field(default_factory=list)
    p2_outputs: list[P2Output] = Field(default_factory=list)
