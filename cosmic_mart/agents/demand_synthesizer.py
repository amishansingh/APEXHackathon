"""Demand Synthesizer — the core decision agent.

Combines the historical merge output (weight 0.7) with the signal report (weight
0.3) into a per-item forecast and order recommendation. Conflict is preserved,
not averaged: when signal direction contradicts the historical baseline the
forecast range widens to cover both scenarios (§7.4).
"""

from __future__ import annotations

from ..config import SETTINGS
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
_SIGNAL_SWING = 0.60
# Assumed historical demand variability, used to normalise the divergence score.
_HIST_VARIABILITY = 0.20


class DemandSynthesizer(Agent):
    name = "demand_synthesizer"

    def __init__(self, order_agent: OrderRecommendationAgent | None = None):
        self.order_agent = order_agent or OrderRecommendationAgent()
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
            recommendations.append(self._synthesize(merged, signal_ctx))

        widened = sum(1 for r in recommendations if r.forecast_range.widened)
        escalated = sum(1 for r in recommendations if r.escalation_flags)
        self._log(items=len(recommendations), widened=widened, escalated=escalated)
        return recommendations

    def _synthesize(
        self, merged: MergedBaseline, signal_ctx: PerItemSignalContext | None
    ) -> OrderRecommendation:
        baseline = merged.weighted_baseline

        # Net signal pull in [-1, 1]; signal-implied forecast swings off baseline.
        net_pull = self._net_pull(signal_ctx)
        signal_implied = baseline * (1.0 + net_pull * _SIGNAL_SWING)

        # Divergence normalised by historical variability (§7.4).
        hist_std = max(baseline * _HIST_VARIABILITY, 1.0)
        divergence = abs(signal_implied - baseline) / hist_std

        signal_contradicts = self._contradicts(baseline, signal_implied, signal_ctx)
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
        conflict_summary = self._conflict_summary(
            baseline, signal_implied, signal_ctx, conflict
        )
        reasoning = self._reasoning(baseline, signal_implied, net_pull, conflict, widened)

        return self.order_agent.package(
            sku=merged.sku,
            baseline=baseline,
            forecast_range=forecast_range,
            confidence=confidence,
            divergence=divergence,
            conflict_summary=conflict_summary,
            escalation_flags=flags,
            hist_weight=self.hist_weight,
            sig_weight=self.sig_weight,
            reasoning=reasoning,
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
        # Clamp to [-1, 1] so a pile of signals can't run the forecast away.
        return max(-1.0, min(1.0, score))

    def _contradicts(
        self, baseline: float, signal_implied: float, ctx: PerItemSignalContext | None
    ) -> bool:
        if not ctx or ctx.net_direction == "neutral":
            return False
        # Signals say "up" but implied lands below baseline (or vice versa) — tension.
        if ctx.net_direction == "up" and signal_implied < baseline:
            return True
        if ctx.net_direction == "down" and signal_implied > baseline:
            return True
        # A strong signal that pushes hard away from baseline is itself a divergence.
        return abs(signal_implied - baseline) / max(baseline, 1.0) > 0.25

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
