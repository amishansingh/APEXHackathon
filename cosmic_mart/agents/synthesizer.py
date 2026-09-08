"""Demand synthesizer: reconciles six signals into one probabilistic range."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..llm import Reasoner
from ..models import (
    AttributedSignal,
    DemandForecast,
    SKUMarket,
    SignalKind,
    SynthesizedDemand,
)

_SYSTEM = (
    "You are the DEMAND SYNTHESIZER for Cosmic Mart, a retailer across 10 Earth markets "
    "carrying a $7.84B pre-tax loss driven by inventory misalignment.\n\n"
    "Six specialist agents each report a demand impact for their own domain. Reconcile them "
    "into ONE probabilistic demand range for the period, in units.\n\n"
    "Rules you must follow:\n"
    "- Output a range, never a point estimate. The width of the range IS the information.\n"
    "- Signals conflict often: weather says demand is rising while macro says consumer "
    "confidence is falling. Do not average conflicts away. Widen the range and name the "
    "conflicting agents.\n"
    "- Weight each agent by the provided trust weight and by its own stated confidence. "
    "The seasonality agent is the baseline authority; when the social agent disagrees with "
    "it on a known recurring peak, prefer seasonality.\n"
    "- Your confidence must fall as signals disagree or as their individual confidences fall.\n"
    "- units_low <= units_expected <= units_high, all non-negative."
)


class _SynthOut(BaseModel):
    units_low: int = Field(ge=0)
    units_expected: int = Field(ge=0)
    units_high: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    conflicting_signals: list[str] = Field(
        description="Agent names whose readings pull in opposite directions. Empty if aligned."
    )
    reasoning: str = Field(description="Two or three sentences on how you reconciled them.")


class SignalAccuracyLedger:
    """Tracks how well each signal agent has predicted, and re-weights accordingly.

    This is what makes the model proprietary over time: the weights encode which
    signal actually moves demand in which market.
    """

    def __init__(self, initial: dict[SignalKind, float] | None = None):
        self._weights = dict(initial or SETTINGS.signal_weights)
        self._observations: dict[SignalKind, list[float]] = {k: [] for k in self._weights}

    def weight(self, kind: SignalKind) -> float:
        return self._weights[kind]

    def record(self, kind: SignalKind, predicted_pct: float, actual_pct: float) -> None:
        """Log one realized outcome and nudge the agent's weight toward its accuracy."""
        error = abs(predicted_pct - actual_pct)
        accuracy = max(0.0, 1.0 - error / 100.0)
        self._observations[kind].append(accuracy)
        history = self._observations[kind]
        mean_accuracy = sum(history) / len(history)
        # Ease toward the observed accuracy rather than snapping, so one bad
        # week cannot silence an agent.
        self._weights[kind] = round(0.7 * self._weights[kind] + 0.6 * mean_accuracy, 3)

    def snapshot(self) -> dict[str, float]:
        return {k.value: round(v, 3) for k, v in self._weights.items()}


class DemandSynthesizer:
    def __init__(self, reasoner: Reasoner, ledger: SignalAccuracyLedger | None = None):
        self.reasoner = reasoner
        self.ledger = ledger or SignalAccuracyLedger()

    def _blend(self, signals: list[AttributedSignal], baseline: int) -> DemandForecast:
        """Weighted blend used offline and as the fallback for the LLM call."""
        total_weight = sum(s.weight * s.reading.confidence for s in signals) or 1.0
        weighted_impact = (
            sum(s.weight * s.reading.confidence * s.reading.demand_impact_pct for s in signals)
            / total_weight
        )
        expected = max(0, int(baseline * (1 + weighted_impact / 100.0)))

        # Disagreement between signals widens the band.
        impacts = [s.reading.demand_impact_pct for s in signals]
        spread = (max(impacts) - min(impacts)) if impacts else 0.0
        band = max(0.08, min(0.6, spread / 200.0))

        mean_confidence = sum(s.reading.confidence for s in signals) / max(1, len(signals))
        # Independent agents corroborating each other beats any single reading, so a
        # full six-signal panel earns more confidence than its average member.
        corroboration = min(1.0, 0.6 + 0.08 * len(signals))
        confidence = round(
            max(0.1, min(0.95, mean_confidence * corroboration * (1 - band * 0.5))), 2
        )

        positives = {s.agent for s in signals if s.reading.demand_impact_pct > 5}
        negatives = {s.agent for s in signals if s.reading.demand_impact_pct < -5}
        conflicts = sorted(positives | negatives) if positives and negatives else []

        return DemandForecast(
            units_low=int(expected * (1 - band)),
            units_expected=expected,
            units_high=int(expected * (1 + band)),
            confidence=confidence,
            conflicting_signals=conflicts,
            reasoning=(
                f"Weighted blend of {len(signals)} signals gives {weighted_impact:+.1f}% "
                f"versus a {baseline}-unit baseline, with a +/-{band:.0%} band from a "
                f"{spread:.0f}pt spread between the most bullish and most bearish agent."
            ),
        )

    async def run(
        self, target: SKUMarket, signals: list[AttributedSignal], baseline_units: int
    ) -> SynthesizedDemand:
        # Apply the current learned trust before reasoning over the signals.
        for signal in signals:
            signal.weight = self.ledger.weight(signal.reading.kind)

        fallback = self._blend(signals, baseline_units)
        payload = {
            "sku": target.sku.name,
            "category": target.sku.category,
            "market": target.market.name,
            "baseline_units_for_period": baseline_units,
            "signals": [
                {
                    "agent": s.agent,
                    "domain": s.reading.kind.value,
                    "cadence": s.cadence.value,
                    "trust_weight": s.weight,
                    "demand_impact_pct": s.reading.demand_impact_pct,
                    "confidence": s.reading.confidence,
                    "horizon_days": s.reading.horizon_days,
                    "rationale": s.reading.rationale,
                    "drivers": s.reading.drivers,
                }
                for s in signals
            ],
        }

        out = await self.reasoner.think(
            system=_SYSTEM,
            payload=payload,
            instruction=(
                f"Reconcile these six signals into one demand range for {target.sku.name} "
                f"in {target.market.name} over the next 30 days."
            ),
            schema=_SynthOut,
            fallback=_SynthOut(**fallback.model_dump()),
        )

        low, expected, high = sorted((out.units_low, out.units_expected, out.units_high))
        forecast = DemandForecast(
            units_low=low,
            units_expected=expected,
            units_high=high,
            confidence=out.confidence,
            conflicting_signals=out.conflicting_signals,
            reasoning=out.reasoning,
        )

        return SynthesizedDemand(
            target=target,
            baseline_units=baseline_units,
            forecast=forecast,
            inputs=signals,
            escalate_to_human=forecast.confidence < SETTINGS.escalation_confidence_floor,
        )
