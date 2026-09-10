"""Demand Synthesizer — the core decision agent.

Combines the historical merge output (weight 0.7) with the signal report (weight
0.3) into a per-item forecast and order recommendation. Conflict is preserved,
not averaged: when signal direction contradicts the historical baseline the
forecast range widens to cover both scenarios (§7.4).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..llm import Reasoner
from ..models import (
    EscalationFlag,
    ForecastRange,
    MergedBaseline,
    OrderRecommendation,
    PerItemSignalContext,
)
from .base import Agent
from .order_recommendation import OrderRecommendationAgent

# Fraction of baseline a full-strength net signal swings the implied forecast.
# Calibrated against _HIST_VARIABILITY below: a saturated net pull lands just
# under the 2σ divergence threshold, so agreement — however strong — reads as
# agreement. Conflict has to come from the inputs actually disagreeing.
_SIGNAL_SWING = 0.38
# Assumed historical demand variability, used to normalise the divergence score.
_HIST_VARIABILITY = 0.20

_SYSTEM = """You are the Demand Synthesizer in Cosmic Mart's demand forecasting \
pipeline, covering the North American market.

The forecast numbers have already been computed and are NOT yours to change. \
You are writing the explanation a human reviewer reads before approving, \
modifying, rejecting or escalating the order.

Write two things:
- reasoning: one or two sentences on how the historical baseline (weighted 0.7) \
and the live signals (weighted 0.3) combined into this forecast.
- conflict_summary: when the inputs disagree, name both sides and say what the \
widened range covers. Empty string when there is no conflict.

The house rule is that conflict is preserved, not averaged. When historical and \
signal views disagree the range is widened to span both scenarios rather than \
split down the middle — explain the tension, never smooth it over. Be concrete \
and cite the actual numbers you were given. No hedging, no filler."""


class SynthesisNarrative(BaseModel):
    """The reviewer-facing explanation. Numbers are computed, not modelled."""

    reasoning: str = Field(default="", description="One or two sentences")
    conflict_summary: str = Field(default="", description="Empty when no conflict")


class DemandSynthesizer(Agent):
    name = "demand_synthesizer"

    def __init__(
        self,
        order_agent: OrderRecommendationAgent | None = None,
        reasoner: Reasoner | None = None,
    ):
        self.order_agent = order_agent or OrderRecommendationAgent()
        self.reasoner = reasoner or Reasoner()
        self.hist_weight = SETTINGS.hist_branch_weight
        self.sig_weight = SETTINGS.sig_branch_weight

    async def run(
        self,
        baselines: list[MergedBaseline],
        signals: list[PerItemSignalContext],
    ) -> list[OrderRecommendation]:
        sig_by_sku = {s.sku.id: s for s in signals}
        recommendations: list[OrderRecommendation] = []

        for merged in baselines:
            signal_ctx = sig_by_sku.get(merged.sku.id)
            recommendations.append(await self._synthesize(merged, signal_ctx))

        widened = sum(1 for r in recommendations if r.forecast_range.widened)
        escalated = sum(1 for r in recommendations if r.escalation_flags)
        self._log(items=len(recommendations), widened=widened, escalated=escalated)
        return recommendations

    async def _synthesize(
        self, merged: MergedBaseline, signal_ctx: PerItemSignalContext | None
    ) -> OrderRecommendation:
        baseline = merged.weighted_baseline

        # Net signal pull in [-1, 1]; signal-implied forecast swings off baseline.
        net_pull = self._net_pull(signal_ctx)
        signal_implied = baseline * (1.0 + net_pull * _SIGNAL_SWING)

        # Divergence normalised by historical variability (§7.4).
        hist_std = max(baseline * _HIST_VARIABILITY, 1.0)
        divergence = abs(signal_implied - baseline) / hist_std

        signal_contradicts = self._contradicts(
            baseline, signal_implied, signal_ctx, divergence
        )
        internal_conflict = bool(signal_ctx and signal_ctx.has_conflict)
        conflict = signal_contradicts or internal_conflict

        if conflict:
            # Do NOT average. Anchor on the historical baseline and widen the range
            # to span both the historical and signal-implied scenarios.
            expected = baseline
            low = min(baseline, signal_implied) * 0.9
            high = max(baseline, signal_implied) * 1.1
            widened = True
        else:
            # Weighted blend of the two branches.
            expected = baseline * self.hist_weight + signal_implied * self.sig_weight
            low = expected * 0.85
            high = expected * 1.15
            widened = False

        forecast_range = ForecastRange(
            units_low=max(0, round(low)),
            units_expected=max(0, round(expected)),
            units_high=max(0, round(high)),
            widened=widened,
        )

        confidence = self._confidence(merged, conflict, divergence)
        flags = self._escalation_flags(merged, expected, confidence, divergence)

        # §7.2 contract field. This is the only stage holding both the baseline
        # and the signals, so it is the only stage that can honestly set it.
        if signal_ctx:
            for s in signal_ctx.signals:
                s.conflict_with_baseline = signal_contradicts and s.direction != "neutral"

        narrative = await self.reasoner.think(
            system=_SYSTEM,
            payload={
                "item_id": merged.sku.id,
                "item_name": merged.sku.name,
                "historical_baseline_units": round(baseline, 1),
                "signal_implied_units": round(signal_implied, 1),
                "net_signal_pull": round(net_pull, 3),
                "signal_rationale": signal_ctx.rationale if signal_ctx else "",
                "signals": [s.model_dump() for s in signal_ctx.signals] if signal_ctx else [],
                "forecast_range": forecast_range.model_dump(),
                "range_widened": widened,
                "conflict": conflict,
                "divergence_sigma": round(divergence, 2),
                "confidence": round(confidence, 3),
                "hist_weight": self.hist_weight,
                "sig_weight": self.sig_weight,
                "data_quality_flags": merged.data_quality_flags,
            },
            instruction=(
                "Write the reviewer-facing reasoning and, if the inputs "
                "disagree, the conflict summary."
            ),
            schema=SynthesisNarrative,
            fallback=SynthesisNarrative(
                reasoning=self._reasoning(
                    baseline, signal_implied, net_pull, conflict, widened
                ),
                conflict_summary=self._conflict_summary(
                    baseline, signal_implied, signal_ctx, conflict
                )
                or "",
            ),
        )

        return self.order_agent.package(
            sku=merged.sku,
            baseline=baseline,
            forecast_range=forecast_range,
            confidence=confidence,
            divergence=divergence,
            conflict_summary=narrative.conflict_summary or None,
            escalation_flags=flags,
            hist_weight=self.hist_weight,
            sig_weight=self.sig_weight,
            reasoning=narrative.reasoning,
        )

    def _net_pull(self, ctx: PerItemSignalContext | None) -> float:
        if not ctx or not ctx.signals:
            return 0.0
        score = 0.0
        for s in ctx.signals:
            if s.direction == "up":
                score += s.strength
            elif s.direction == "down":
                score -= s.strength
        # Saturate rather than hard-clamp: agreeing signals reinforce each other
        # with diminishing returns and the result stays inside (-1, 1). A hard
        # clamp made any three same-direction signals indistinguishable from an
        # extreme one, which then read as divergence downstream.
        return score / (1.0 + abs(score))

    def _contradicts(
        self,
        baseline: float,
        signal_implied: float,
        ctx: PerItemSignalContext | None,
        divergence: float,
    ) -> bool:
        """Does the signal view genuinely contradict the historical baseline?

        Strength alone is not contradiction — a strong signal that agrees with
        the baseline is just a confident forecast. Contradiction is either
        incoherence (the net direction and the implied move disagree) or a
        divergence past the configured threshold (§7.4).
        """
        if not ctx or ctx.net_direction == "neutral":
            return False
        # Signals say "up" but implied lands below baseline (or vice versa) — tension.
        if ctx.net_direction == "up" and signal_implied < baseline:
            return True
        if ctx.net_direction == "down" and signal_implied > baseline:
            return True
        return divergence > SETTINGS.divergence_std_threshold

    def _confidence(self, merged: MergedBaseline, conflict: bool, divergence: float) -> float:
        confidence = 0.85
        if "sparse_earth_data" in merged.data_quality_flags:
            confidence -= 0.20
        if "weak_analogue" in merged.data_quality_flags:
            confidence -= 0.10
        if conflict:
            confidence -= 0.15
        if divergence > SETTINGS.divergence_std_threshold:
            confidence -= 0.15
        return max(0.05, min(1.0, confidence))

    def _escalation_flags(
        self, merged: MergedBaseline, expected: float, confidence: float, divergence: float
    ) -> list[EscalationFlag]:
        flags: list[EscalationFlag] = []
        reorder_value = expected * merged.sku.unit_cost_usd
        if reorder_value > SETTINGS.escalation_value_threshold_usd:
            flags.append(
                EscalationFlag(
                    flag_type="high_value",
                    reason=f"Reorder value ${reorder_value:,.0f} exceeds "
                    f"${SETTINGS.escalation_value_threshold_usd:,.0f} threshold",
                )
            )
        if confidence < SETTINGS.escalation_confidence_floor:
            flags.append(
                EscalationFlag(
                    flag_type="low_confidence",
                    reason=f"Confidence {confidence:.0%} below "
                    f"{SETTINGS.escalation_confidence_floor:.0%} floor",
                )
            )
        if divergence > SETTINGS.divergence_std_threshold:
            flags.append(
                EscalationFlag(
                    flag_type="high_divergence",
                    reason=f"Signal diverges {divergence:.1f}σ from historical baseline",
                )
            )
        return flags

    def _conflict_summary(
        self,
        baseline: float,
        signal_implied: float,
        ctx: PerItemSignalContext | None,
        conflict: bool,
    ) -> str | None:
        if not conflict or not ctx:
            return None
        drivers = ", ".join(s.description for s in ctx.signals if s.description) or "live signals"
        return (
            f"Historical baseline {baseline:.0f} units vs signal-implied "
            f"{signal_implied:.0f} units. Range widened to preserve tension. "
            f"Drivers: {drivers}."
        )

    def _reasoning(
        self, baseline: float, signal_implied: float, net_pull: float, conflict: bool, widened: bool
    ) -> str:
        direction = "up" if net_pull > 0 else "down" if net_pull < 0 else "flat"
        if conflict:
            return (
                f"Signals pull {direction} against a {baseline:.0f}-unit baseline; "
                f"range widened rather than averaged."
            )
        return (
            f"Historical {baseline:.0f} blended 0.7 with signal-implied "
            f"{signal_implied:.0f} at 0.3 (net signal {direction})."
        )
